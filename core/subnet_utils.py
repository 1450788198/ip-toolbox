"""子网计算纯函数（UI 与测试共用，无 Qt 依赖）"""
import ipaddress


def fmt_bin(addr) -> str:
    """IPv4 地址转点分二进制（8 位一组）"""
    return ".".join(f"{int(o):08b}" for o in str(addr).split("."))


def wildcard(mask: str) -> str:
    net = ipaddress.IPv4Network(f"0.0.0.0/{mask}")
    w = int(net.hostmask)
    return str(ipaddress.IPv4Address(w))


def addr_type(ip: ipaddress.IPv4Address) -> str:
    if ip.is_loopback:
        return "回环地址 (127.0.0.0/8)"
    if ip.is_link_local:
        return "链路本地 (169.254.0.0/16)"
    if ip.is_multicast:
        return "组播地址"
    if ip.is_private:
        return "私网地址 (RFC1918)"
    if ip.is_unspecified:
        return "未指定地址 (0.0.0.0)"
    if ip.is_reserved:
        return "保留地址"
    return "公网地址"


def calc(ip_text: str, mask_text: str, normalize_mask) -> dict:
    """计算子网信息。输入非法时抛 ValueError（消息可直接展示）"""
    ip_s = (ip_text or "").strip()
    mask_s = (mask_text or "").strip()
    if not ip_s:
        raise ValueError("请输入 IP 地址")
    if not mask_s:
        raise ValueError("请输入子网掩码或前缀")
    ip = ipaddress.IPv4Address(ip_s)
    mask = normalize_mask(mask_s)
    net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    prefix = net.prefixlen
    if prefix == 32:
        first = last = net.network_address
        usable = "1（主机路由）"
    elif prefix == 31:
        first = net.network_address
        last = net.broadcast_address
        usable = "2（点对点）"
    else:
        first = net.network_address + 1
        last = net.broadcast_address - 1
        usable = str(net.num_addresses - 2)
    note = ""
    if prefix <= 30 and ip == net.network_address:
        note = "该 IP 是网络地址，不能分配给主机"
    elif prefix <= 30 and ip == net.broadcast_address:
        note = "该 IP 是广播地址，不能分配给主机"
    return {
        "mask": str(net.netmask),
        "prefix": prefix,
        "wildcard": wildcard(mask),
        "network": str(net.network_address),
        "broadcast": str(net.broadcast_address),
        "first": str(first),
        "last": str(last),
        "range": f"{first} ~ {last}",
        "hosts": usable,
        "type": addr_type(ip),
        "note": note,
        "bin_ip": fmt_bin(ip),
        "bin_mask": fmt_bin(net.netmask),
        "bin_net": fmt_bin(net.network_address),
        "cidr": f"{net.with_prefixlen}",
    }


def split(net_text: str, mode: str, value: int, normalize_mask=None) -> tuple:
    """VLSM 划分。

    mode="count": 按子网数量（取最接近的 2^n，向上）
    mode="hosts": 按每子网可用主机数
    返回 (子网列表[(网络地址, 掩码, 可用范围, 广播, 主机数)], 说明文字, 新前缀)
    """
    text = (net_text or "").strip()
    if not text:
        raise ValueError("请输入要划分的网段，如 192.168.1.0/24")
    if "/" in text and normalize_mask:
        addr, _, suffix = text.partition("/")
        text = f"{addr}/{normalize_mask(suffix)}"
    try:
        base = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise ValueError("网段格式不正确，应为如 192.168.1.0/24")
    if base.version != 4:
        raise ValueError("仅支持 IPv4 网段")
    if value < 1:
        raise ValueError("数量必须大于 0")

    if mode == "count":
        need = 1
        while need < value:
            need <<= 1
        new_prefix = base.prefixlen
        while (1 << (new_prefix - base.prefixlen)) < need:
            new_prefix += 1
        if new_prefix > 32:
            raise ValueError(f"{base} 无法划分出 {value} 个子网")
    else:
        host_bits = 2
        while (1 << host_bits) - 2 < value:
            host_bits += 1
            if host_bits > 30:
                raise ValueError(f"每子网 {value} 台主机超出 IPv4 单网段上限")
        new_prefix = 32 - host_bits

    if new_prefix < base.prefixlen:
        raise ValueError(f"{base} 的地址空间不足，无法按该需求划分")
    total = 1 << (new_prefix - base.prefixlen)
    subnets = list(base.subnets(new_prefix=new_prefix))[:min(total, 4096)]

    rows = []
    for n in subnets:
        if n.prefixlen == 32:
            first = last = n.network_address
            hosts = "1"
        elif n.prefixlen == 31:
            first, last = n.network_address, n.broadcast_address
            hosts = "2"
        else:
            first, last = n.network_address + 1, n.broadcast_address - 1
            hosts = str(n.num_addresses - 2)
        rows.append((str(n.network_address), str(n.netmask),
                     f"{first} ~ {last}", str(n.broadcast_address), hosts))
    desc = f"{base.with_prefixlen} → {total} 个 /{new_prefix} 子网"
    if mode == "count" and total != value:
        desc += f"（按最接近的 2 的幂划分，需求 {value} 个）"
    if mode == "hosts":
        desc += f"，每子网可用 {max((1 << (32 - new_prefix)) - 2, 1)} 台主机（需求 {value} 台）"
    return rows, desc, new_prefix

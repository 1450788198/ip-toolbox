"""只读网络信息补充（菜单栏面板专用）：IPv6 地址、DHCP 租约摘要

不做任何配置修改，仅解析系统命令输出。
"""
import re

from .netbase import run, CmdError


def ipv6_addresses(device: str) -> list:
    """返回设备的 IPv6 地址列表（含 scope），如 fe80::1%en0（链路本地）"""
    if not device:
        return []
    try:
        out = run(["ifconfig", device])
    except CmdError:
        return []
    result = []
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("inet6 "):
            addr = s.split()[1]
            result.append(addr)
    return result


def dhcp_lease(device: str) -> dict:
    """DHCP 租约摘要（仅 DHCP 模式下有效）：{router, server, expires}"""
    if not device:
        return {}
    info = {}
    try:
        out = run(["ipconfig", "getpacket", device])
    except CmdError:
        return info
    for key, field in (("router", "router"), ("server", "server_identifier"),
                       ("expires", "lease")):
        m = re.search(rf"^\s*{field}\s*=\s*(.+)$", out, re.M)
        if m:
            info[key] = m.group(1).strip().strip("'")
    return info


def iface_kind(ifc: dict) -> str:
    """按端口/服务名推断网卡类型：wifi / usb / thunderbolt / bluetooth /
    bridge / vpn / ethernet / other"""
    text = f"{ifc.get('port', '')} {ifc.get('service', '')} {ifc.get('device', '')}".lower()
    if "vpn" in text or "utun" in text:
        return "vpn"
    if "bridge" in text:
        return "bridge"
    if "bluetooth" in text or "bt" == text.strip():
        return "bluetooth"
    if "usb" in text or "ax88179" in text or "rtl81" in text or "lan" in text:
        return "usb"
    if "thunderbolt" in text or "雷雳" in text:
        return "thunderbolt"
    if "wi-fi" in text or "wifi" in text or "airport" in text:
        return "wifi"
    if ifc.get("device", "").startswith("en"):
        return "ethernet"
    return "other"

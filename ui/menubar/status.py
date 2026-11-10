"""总体网络状态判定（纯函数，便于单测）

原则：只描述接口/地址层面**可观测的事实**，不做互联网连通性探测，
因此绝不出现「互联网正常 / 互联网可用」这类未经探测的结论。

网卡状态口径（与 core/net_mac.py 采集字段一致）：
  up        接口 link active
  down      接口存在但未 active
  absent    设备不存在（USB 网卡未插入）
  disabled  系统设置里该服务被关闭（enabled == False）
  unknown   采集失败 / 状态未知

顶部胶囊文案（优先级从高到低）：
  数据已过期 > 未检测到网卡 > 网卡已禁用 > 网卡未插入 > 网卡未连接 >
  地址配置异常 > 部分接口已连接 > 接口已连接（+ 权限不足后缀）
"""

KINDS = ("up", "down", "absent", "disabled", "unknown")

GROUP_TITLE = {
    "up": "已连接",
    "down": "未连接",
    "absent": "未插入",
    "disabled": "已禁用",
    "unknown": "状态未知",
}


def classify_iface(ifc: dict) -> str:
    """单个网卡 → up / down / absent / disabled / unknown"""
    if not ifc:
        return "unknown"
    if ifc.get("enabled") is False:
        return "disabled"
    st = ifc.get("status")
    if st in ("up", "down", "absent"):
        return st
    return "unknown"


def has_ip(ifc: dict) -> bool:
    return bool((ifc or {}).get("ipv4"))


def overall(snap: dict):
    """返回 (文案, 胶囊类型)；类型 ∈ ok / warn / err / info / muted"""
    snap = snap or {}
    ifaces = snap.get("ifaces") or []

    if snap.get("stale"):
        return ("数据已过期", "warn")
    if not ifaces:
        if snap.get("refreshing"):
            return ("正在刷新", "info")
        return ("未检测到网卡", "muted")

    kinds = [classify_iface(i) for i in ifaces]
    up = [i for i, k in zip(ifaces, kinds) if k == "up"]
    if not up:
        if all(k == "disabled" for k in kinds):
            return ("网卡已禁用", "muted")
        if all(k in ("absent", "disabled") for k in kinds):
            return ("网卡未插入", "warn")
        return ("网卡未连接", "warn")

    up_with_ip = [i for i in up if has_ip(i)]
    up_no_ip = [i for i in up if not has_ip(i)]
    if not up_with_ip:
        return ("地址配置异常", "err")

    if snap.get("elevation_ok") is False:
        return ("接口已连接 · 权限不足", "warn")
    if up_no_ip:
        return ("部分接口已连接", "warn")
    return ("接口已连接", "ok")


def summary(snap: dict) -> str:
    """头部副标题：各状态计数（只列非零项；网卡总数在「网卡 N」处展示）"""
    ifaces = (snap or {}).get("ifaces") or []
    if not ifaces:
        return "未检测到网络服务"
    kinds = [classify_iface(i) for i in ifaces]
    parts = []
    for key in ("up", "down", "absent", "disabled"):
        n = kinds.count(key)
        if n:
            parts.append(f"{GROUP_TITLE[key]} {n}")
    aliases = 0
    detail = (snap or {}).get("detail") or {}
    for i in ifaces:
        d = detail.get(i.get("service") or i.get("device") or "") or {}
        aliases += len(d.get("aliases") or [])
    if aliases:
        parts.append(f"附加 IP {aliases}")
    return " · ".join(parts)

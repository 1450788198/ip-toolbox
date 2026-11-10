"""菜单栏状态图标：Network Control 专用

四种显示模式（core/settings.py: menu_bar_icon）：
  icon    网络节点图标（默认）
  status  节点图标 + 连接状态圆点
  ip      当前 IP 网段文字（如 10.200.254）
  iface   当前网卡设备名（如 en5）

全部渲染为 macOS 模板图标（setIsMask），菜单栏明暗自动反色。
"""
import ipaddress

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap

from .. import icons

_STATUS_DPR = 4.0   # 文字/组合图标用 4x 渲染保证清晰


def _svg_pix(paths: str, size: int, dpr: float = 2.0) -> QPixmap:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#000000" stroke-width="1.9" stroke-linecap="round" '
        'stroke-linejoin="round">%s</svg>' % paths
    )
    return icons._pix(svg, size, dpr)


def _primary_iface(snap: dict) -> dict:
    """当前主网卡：设置默认网卡 > 外置有 IP > 任意有 IP > 第一个"""
    ifaces = snap.get("ifaces") or []
    if not ifaces:
        return {}
    preferred = None
    try:
        from core import settings as _settings
        preferred = _settings.get("default_iface")
    except Exception:
        preferred = None
    with_ip = [i for i in ifaces if i.get("ipv4")]
    if preferred:
        for i in with_ip:
            if i.get("service") == preferred or i.get("device") == preferred:
                return i
    # 优先已连接（status up）的网卡；USB 未插入但残留配置的不作为主网卡
    up = [i for i in with_ip if i.get("status") == "up"]
    pool = up or with_ip
    if pool:
        ext = [i for i in pool if _is_ext(i)]
        return (ext or pool)[0]
    return ifaces[0]


def _is_ext(ifc: dict) -> bool:
    try:
        from core.netbase import iface_is_external
        return iface_is_external(ifc)
    except Exception:
        return False


def _network_text(ip: str, mask: str) -> str:
    """IP → 网段缩写：10.200.254.89/24 → 10.200.254"""
    try:
        net = ipaddress.IPv4Network(f"0.0.0.0/{mask}", strict=False).prefixlen if mask else 0
    except Exception:
        net = 0
    parts = (ip or "").split(".")
    if len(parts) != 4:
        return ip or ""
    if net >= 24:
        return ".".join(parts[:3])
    if net >= 16:
        return ".".join(parts[:2])
    return parts[0] if parts else ip


def _text_pix(text: str, size_pt: float = 11.5) -> QPixmap:
    f = QFont()
    f.setFamily("-apple-system")
    f.setPixelSize(int(size_pt * _STATUS_DPR))
    f.setWeight(QFont.DemiBold)
    fm = QFontMetrics(f)
    w = fm.horizontalAdvance(text) + 2
    h = fm.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setFont(f)
    p.setPen(QColor("#000000"))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignVCenter | Qt.AlignLeft, text)
    p.end()
    pm.setDevicePixelRatio(_STATUS_DPR)
    return pm


def _compose(base: QPixmap, dot: QPixmap) -> QPixmap:
    """节点图标 + 右下角状态点"""
    w = max(base.width(), dot.width())
    h = max(base.height(), dot.height())
    pm = QPixmap(w + int(3 * _STATUS_DPR), h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.drawPixmap(0, 0, base)
    p.drawPixmap(pm.width() - dot.width(), h - dot.height(), dot)
    p.end()
    pm.setDevicePixelRatio(_STATUS_DPR)
    return pm


def _dot_pix(kind: str) -> QPixmap:
    d = int(4.5 * _STATUS_DPR)
    pm = QPixmap(d, d)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen_pen = 1.1 * _STATUS_DPR
    if kind == "up":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#000000"))
    else:                                  # down/absent：空心
        p.setPen(QPen(QColor("#000000"), pen_pen))
        p.setBrush(Qt.NoBrush)
    p.drawEllipse(int(pen_pen / 2), int(pen_pen / 2),
                  d - int(pen_pen), d - int(pen_pen))
    p.end()
    pm.setDevicePixelRatio(_STATUS_DPR)
    return pm


def menubar_icon(mode: str, snap: dict) -> QIcon:
    """按模式构建菜单栏模板图标"""
    snap = snap or {}
    ic = QIcon()
    ifc = _primary_iface(snap)
    has_ip = bool(ifc.get("ipv4"))
    status = ifc.get("status")

    if mode == "ip" and has_ip:
        pm = _text_pix(_network_text(ifc.get("ipv4"), ifc.get("mask") or ""))
    elif mode == "iface" and ifc:
        pm = _text_pix(ifc.get("device") or ifc.get("service") or "—")
    elif mode == "status":
        dot_kind = "up" if (has_ip and status == "up") else "down"
        pm = _compose(_svg_pix(icons._ICONS["nodes"], 17, _STATUS_DPR), _dot_pix(dot_kind))
    else:
        pm = _svg_pix(icons._ICONS["nodes"], 18, 2.0)
    ic.addPixmap(pm)
    try:
        ic.setIsMask(True)
    except Exception:
        pass
    return ic


def tooltip_text(snap: dict) -> str:
    snap = snap or {}
    ifc = _primary_iface(snap)
    if not ifc:
        return "IP 工具箱 · Network Control\n未检测到网卡"
    ip = ifc.get("ipv4") or "无 IP"
    n = len(snap.get("ifaces") or [])
    stale = "（数据已过期）" if snap.get("stale") else ""
    return (f"IP 工具箱 · Network Control\n"
            f"{ifc.get('service') or ifc.get('device')}：{ip} · 共 {n} 个网卡{stale}")

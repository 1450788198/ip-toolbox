"""矢量线性图标（Lucide 风格，SVG 内联渲染）

- icon(key, color)          单色图标
- nav_icon(key, dark)       侧边栏两态（未选中灰 / 选中白）
- svg_svg(key, color, size) 空状态大图标
菜单栏模板图标见 ui/menubar/icon.py（menubar_icon）
"""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

_SVG_TPL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
    'stroke-linejoin="round">{paths}</svg>'
)

_ICONS = {
    # 总览：四宫格
    "dashboard": (
        '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/>'
        '<rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/>'
        '<rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/>'
        '<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>'
    ),
    # 网卡：显示器
    "network": (
        '<rect x="2" y="3.5" width="20" height="13" rx="2"/>'
        '<path d="M8 20.5h8"/><path d="M12 16.5v4"/>'
    ),
    # 网卡替代：网口
    "ethernet": (
        '<rect x="2.5" y="7" width="19" height="12" rx="2"/>'
        '<path d="M6 19v2"/><path d="M18 19v2"/>'
        '<path d="M7.5 11h.01"/><path d="M11 11h.01"/><path d="M14.5 11h.01"/><path d="M18 11h.01"/>'
    ),
    # 地球
    "ip": (
        '<circle cx="12" cy="12" r="9.2"/>'
        '<path d="M2.8 12h18.4"/>'
        '<path d="M12 2.8c2.7 2.6 4 5.7 4 9.2s-1.3 6.6-4 9.2'
        'c-2.7-2.6-4-5.7-4-9.2s1.3-6.6 4-9.2z"/>'
    ),
    # 图层
    "presets": (
        '<path d="M12 2.8 2.8 7.5 12 12.2l9.2-4.7z"/>'
        '<path d="m2.8 12.4 9.2 4.7 9.2-4.7"/>'
        '<path d="m2.8 17.3 9.2 4.7 9.2-4.7"/>'
    ),
    # 路径分叉
    "routes": (
        '<circle cx="6" cy="19" r="2.6"/>'
        '<circle cx="18" cy="5" r="2.6"/>'
        '<path d="M8.6 19h7.4a3.6 3.6 0 0 0 0-7.2H8a3.6 3.6 0 0 1 0-7.2h7.4"/>'
    ),
    # 信号波（DHCP）
    "dhcp": (
        '<path d="M12 19.6h.01"/>'
        '<path d="M2.4 8.8a15 15 0 0 1 19.2 0"/>'
        '<path d="M5.3 12.7a10 10 0 0 1 13.4 0"/>'
        '<path d="M8.5 16.3a5 5 0 0 1 7 0"/>'
    ),
    # 计算器
    "calc": (
        '<rect x="4.5" y="2.5" width="15" height="19" rx="2"/>'
        '<rect x="8" y="6" width="8" height="3.4" rx="0.8"/>'
        '<path d="M8.5 13.5h.01"/><path d="M12 13.5h.01"/><path d="M15.5 13.5h.01"/>'
        '<path d="M8.5 17.5h.01"/><path d="M12 17.5h.01"/><path d="M15.5 17.5h.01"/>'
    ),
    # 划分：分栏
    "vlsm": (
        '<rect x="2.5" y="3.5" width="19" height="17" rx="2"/>'
        '<path d="M9 3.5v17"/><path d="M15.5 3.5v17"/>'
    ),
    # 掩码速查：列表网格
    "mask": (
        '<rect x="3" y="3.5" width="18" height="17" rx="2"/>'
        '<path d="M3 9h18"/><path d="M3 14.5h18"/>'
        '<path d="M9 3.5v17"/>'
    ),
    # 服务器
    "dns": (
        '<rect x="2.5" y="3" width="19" height="7.5" rx="2"/>'
        '<rect x="2.5" y="13.5" width="19" height="7.5" rx="2"/>'
        '<path d="M6.5 6.75h.01"/><path d="M10 6.75h.01"/>'
        '<path d="M6.5 17.25h.01"/><path d="M10 17.25h.01"/>'
    ),
    # 时钟（历史）
    "history": (
        '<path d="M3 12a9 9 0 1 0 3-6.7"/>'
        '<path d="M3 3.5V8h4.5"/>'
        '<path d="M12 7.5V12l3.2 2"/>'
    ),
    # 设置：滑杆
    "settings": (
        '<path d="M4 6h9"/><path d="M17 6h3"/><circle cx="15" cy="6" r="2"/>'
        '<path d="M4 12h3"/><path d="M11 12h9"/><circle cx="9" cy="12" r="2"/>'
        '<path d="M4 18h9"/><path d="M17 18h3"/><circle cx="15" cy="18" r="2"/>'
    ),
    # 通用动作
    "plus": ('<path d="M12 5v14"/><path d="M5 12h14"/>'),
    "trash": (
        '<path d="M4 7h16"/><path d="M9.5 7V4.8h5V7"/>'
        '<path d="M6.5 7l1 13h9l1-13"/>'
    ),
    "refresh": (
        '<path d="M20.5 11.5a8.5 8.5 0 1 1-2.6-6"/>'
        '<path d="M20.5 3.5v6h-6"/>'
    ),
    "search": ('<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>'),
    "copy": (
        '<rect x="9" y="9" width="11" height="11" rx="2"/>'
        '<path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/>'
    ),
    "check": ('<path d="m4.5 12.5 5 5 10-11"/>'),
    "x": ('<path d="M6 6l12 12"/><path d="M18 6L6 18"/>'),
    "info": ('<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.6h.01"/>'),
    "shield": (
        '<path d="M12 3 5 6v5.5c0 4.3 2.9 7.7 7 9.5 4.1-1.8 7-5.2 7-9.5V6z"/>'
        '<path d="m9 12 2.2 2.2L15.5 10"/>'
    ),
    "wifi": (
        '<path d="M2.5 8.5a14 14 0 0 1 19 0"/>'
        '<path d="M5.8 12.2a9.4 9.4 0 0 1 12.4 0"/>'
        '<path d="M9 15.8a4.6 4.6 0 0 1 6 0"/><path d="M12 19.4h.01"/>'
    ),
    "chevron": ('<path d="m9 5 7 7-7 7"/>'),
    "chevronDown": ('<path d="m5 9 7 7 7-7"/>'),
    "download": ('<path d="M12 3.5v11"/><path d="m7.5 10 4.5 4.5L16.5 10"/><path d="M4 20.5h16"/>'),
    "folder": ('<path d="M3 6.5A2 2 0 0 1 5 4.5h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
    # ---- 菜单栏 / 面板 ----
    # 网络节点（菜单栏主图标）：中心节点连两侧
    "nodes": (
        '<circle cx="5" cy="6.5" r="2.5"/><circle cx="19" cy="6.5" r="2.5"/>'
        '<circle cx="12" cy="17.5" r="2.5"/>'
        '<path d="M7.2 7.6 10.4 15"/><path d="M16.8 7.6 13.6 15"/>'
    ),
    # USB 网卡：插头
    "usb": (
        '<rect x="7.5" y="9" width="9" height="12" rx="2"/>'
        '<path d="M12 9V3.5"/><path d="m9.5 6 2.5-2.5L14.5 6"/>'
    ),
    # 雷雳：闪电
    "bolt": ('<path d="M13 2.5 5 13.5h6L11 21.5l8-11h-6z"/>'),
    # 蓝牙
    "bt": ('<path d="m7 8 10 8.5L12 21V3l5 4.5L7 16"/>'),
    # 桥接
    "bridge": (
        '<path d="M3 13.5h18"/><path d="M6 13.5V8a6 6 0 0 1 12 0v5.5"/>'
        '<path d="M3 13.5V18"/><path d="M21 13.5V18"/>'
    ),
    # 主窗口
    "window": (
        '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/>'
        '<path d="M3 9h18"/><path d="M6 6.75h.01"/><path d="M8.75 6.75h.01"/>'
    ),
    # 诊断：活动监视器式脉冲
    "diagnose": ('<path d="M3 12h4l2.5-6 4 12 2.5-6h5"/>'),
    # 断电/停止（DHCP）
    "stop": ('<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>'),
    # 播放（DHCP 启动）
    "play": ('<path d="M8 5.5v13l11-6.5z"/>'),
}

_COLOR_NORMAL = "#6E6E73"


def _pix(svg: str, size: int, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def pixmap(key: str, color: str = _COLOR_NORMAL, size: int = 16) -> QPixmap:
    return _pix(_SVG_TPL.format(color=color, paths=_ICONS.get(key, "")), size)


def icon(key: str, color: str = _COLOR_NORMAL, size: int = 16) -> QIcon:
    """单色图标（按钮、工具栏）"""
    return QIcon(pixmap(key, color, size))


def nav_icon(key: str, dark: bool = False, size: int = 16) -> QIcon:
    """侧边栏图标：未选中用次要文字色，选中（accent 底）用白色"""
    t = theme.tokens(dark)
    paths = _ICONS.get(key, "")
    normal = _pix(_SVG_TPL.format(color=t["text2"] if not dark else t["text2"], paths=paths), size)
    active = _pix(_SVG_TPL.format(color=t["on_accent"], paths=paths), size)
    ic = QIcon()
    ic.addPixmap(normal, QIcon.Normal, QIcon.Off)
    ic.addPixmap(normal, QIcon.Active, QIcon.Off)
    ic.addPixmap(active, QIcon.Normal, QIcon.On)
    ic.addPixmap(active, QIcon.Active, QIcon.On)
    return ic


def svg_svg(key: str, color: str = _COLOR_NORMAL, size: int = 64) -> QPixmap:
    """空状态大图"""
    return _pix(_SVG_TPL.format(color=color, paths=_ICONS.get(key, "")), size)

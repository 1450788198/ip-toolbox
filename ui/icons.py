"""矢量线性图标（Lucide 风格，SVG 原生渲染，替代 emoji）

用法：
    from ui.icons import nav_icon
    item.setIcon(nav_icon("network"))
QIcon 内含 Normal（灰）与 Selected（白）两态，
侧边栏选中蓝色胶囊时图标自动变白。
"""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Lucide 风格路径（viewBox 24x24，stroke 线性图标）
_SVG_TPL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
    'stroke-linejoin="round">{paths}</svg>'
)

_ICONS = {
    # 显示器（网卡管理）
    "network": (
        '<rect x="2" y="3" width="20" height="14" rx="2"/>'
        '<path d="M8 21h8"/><path d="M12 17v4"/>'
    ),
    # 地球（IP 配置）
    "ip": (
        '<circle cx="12" cy="12" r="9.2"/>'
        '<path d="M2.8 12h18.4"/>'
        '<path d="M12 2.8c2.7 2.6 4 5.7 4 9.2s-1.3 6.6-4 9.2'
        'c-2.7-2.6-4-5.7-4-9.2s1.3-6.6 4-9.2z"/>'
    ),
    # 图层堆叠（IP 方案）
    "presets": (
        '<path d="M12 2.8 2.8 7.5 12 12.2l9.2-4.7z"/>'
        '<path d="m2.8 12.4 9.2 4.7 9.2-4.7"/>'
        '<path d="m2.8 17.3 9.2 4.7 9.2-4.7"/>'
    ),
    # 路径分叉（路由管理）
    "routes": (
        '<circle cx="6" cy="19" r="2.6"/>'
        '<circle cx="18" cy="5" r="2.6"/>'
        '<path d="M8.6 19h7.4a3.6 3.6 0 0 0 0-7.2H8a3.6 3.6 0 0 1 0-7.2h7.4"/>'
    ),
    # Wi-Fi 波（DHCP 服务）
    "dhcp": (
        '<path d="M12 19.6h.01"/>'
        '<path d="M2.4 8.8a15 15 0 0 1 19.2 0"/>'
        '<path d="M5.3 12.7a10 10 0 0 1 13.4 0"/>'
        '<path d="M8.5 16.3a5 5 0 0 1 7 0"/>'
    ),
    # 计算器（子网计算器）
    "calc": (
        '<rect x="4.5" y="2.5" width="15" height="19" rx="2"/>'
        '<rect x="8" y="6" width="8" height="3.4" rx="0.8"/>'
        '<path d="M8.5 13.5h.01"/><path d="M12 13.5h.01"/><path d="M15.5 13.5h.01"/>'
        '<path d="M8.5 17.5h.01"/><path d="M12 17.5h.01"/><path d="M15.5 17.5h.01"/>'
    ),
    # 服务器机架（DNS 查询）
    "dns": (
        '<rect x="2.5" y="2.5" width="19" height="8" rx="2"/>'
        '<rect x="2.5" y="13.5" width="19" height="8" rx="2"/>'
        '<path d="M6.5 6.5h.01"/><path d="M10 6.5h.01"/>'
        '<path d="M6.5 17.5h.01"/><path d="M10 17.5h.01"/>'
    ),
}

# 空状态大图标（额外粗细度可选）
_COLOR_NORMAL = "#6e6e73"
_COLOR_SELECTED = "#ffffff"


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


def nav_icon(key: str, size: int = 16) -> QIcon:
    """生成两态图标：普通灰色 / 选中白色"""
    paths = _ICONS.get(key, "")
    icon = QIcon()
    for color, mode in ((_COLOR_NORMAL, QIcon.Normal),
                        (_COLOR_NORMAL, QIcon.Active),
                        (_COLOR_SELECTED, QIcon.Selected)):
        icon.addPixmap(_pix(_SVG_TPL.format(color=color, paths=paths), size), mode)
    return icon


def svg_svg(key: str, color: str = _COLOR_NORMAL, size: int = 64) -> QPixmap:
    """生成单个颜色的图标 QPixmap（用于空状态等大图）"""
    return _pix(_SVG_TPL.format(color=color, paths=_ICONS.get(key, "")), size)


def make_tray_icon() -> QIcon:
    """菜单栏托盘图标：透明底黑色线条（模板样式，macOS 深色菜单栏自动反色）"""
    icon = QIcon()
    pm = _pix(_SVG_TPL.format(color="#000000", paths=_ICONS["ip"]), 18, 2.0)
    icon.addPixmap(pm)
    try:
        icon.setIsMask(True)   # macOS 模板图：系统自动适配明暗菜单栏
    except Exception:
        pass
    return icon

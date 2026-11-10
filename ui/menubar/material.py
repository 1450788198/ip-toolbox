"""弹出面板背景：完全自绘的悬浮底色

不再使用 NSVisualEffectView 原生材质——在打包环境下该方案出现过
两次合成错乱（背景全透明穿帮 / 半透明残影小窗），改为纯 QPainter
绘制近不透明圆角底 + 轻渐变 + 描边，外观接近原生 NSPopover，
且任何环境下渲染行为完全确定。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPainterPath, QLinearGradient


def reduce_motion() -> bool:
    """系统"减少动态效果"偏好"""
    try:
        from AppKit import NSWorkspace
        return bool(NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion())
    except Exception:
        return False


def paint_panel_background(widget, dark: bool, radius: float = 13.0,
                           vibrancy_ok: bool = False):
    """面板背景：自绘圆角底（vibrancy_ok 参数保留兼容签名，恒走自绘）

    近不透明（alpha ≈ 252/255）→ 既像系统悬浮面板，又绝不会透出底层窗口文字。
    """
    p = QPainter(widget)
    p.setRenderHint(QPainter.Antialiasing)
    r = widget.rect().adjusted(0, 0, -1, -1)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    grad = QLinearGradient(0, r.top(), 0, r.bottom())
    if dark:
        grad.setColorAt(0.0, QColor(44, 44, 48, 252))
        grad.setColorAt(1.0, QColor(34, 34, 38, 252))
    else:
        grad.setColorAt(0.0, QColor(252, 252, 253, 252))
        grad.setColorAt(1.0, QColor(243, 243, 246, 252))
    p.fillPath(path, grad)
    # 1px 描边：浅色下略重、深色下略轻，保证白底/深底上都有边界
    border = QColor(0, 0, 0, 26) if not dark else QColor(255, 255, 255, 26)
    p.setPen(border)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()

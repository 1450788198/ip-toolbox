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


def paint_panel_background(widget, dark: bool, radius: float = 12.0,
                           vibrancy_ok: bool = False):
    """面板背景：自绘圆角底（vibrancy_ok 参数保留兼容签名，恒走自绘）"""
    p = QPainter(widget)
    p.setRenderHint(QPainter.Antialiasing)
    r = widget.rect().adjusted(0, 0, -1, -1)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    grad = QLinearGradient(0, r.top(), 0, r.bottom())
    if dark:
        grad.setColorAt(0.0, QColor(46, 46, 50, 252))
        grad.setColorAt(1.0, QColor(38, 38, 42, 252))
    else:
        grad.setColorAt(0.0, QColor(249, 249, 251, 253))
        grad.setColorAt(1.0, QColor(241, 241, 245, 253))
    p.fillPath(path, grad)
    border = QColor(0, 0, 0, 36) if not dark else QColor(255, 255, 255, 30)
    p.setPen(border)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()

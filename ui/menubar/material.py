"""弹出面板背景材质：NSVisualEffectView（原生毛玻璃）+ 纯 Q 绘制降级

已实测验证（macOS 27.2 / Apple Silicon / PySide6 6.12 + pyobjc 13）：
- 材质视图挂在 Qt 根视图的父视图（NSNextStepFrame）之下，作为兄弟视图垫底，
  Qt 内容正常绘制在毛玻璃之上；
- NSWindow 设为非不透明 + clearColor，Qt 侧 WA_TranslucentBackground；
- 圆角通过材质视图 layer 的 cornerRadius + masksToBounds 实现；
- 明暗跟随面板自身主题（显式设置 NSAppearance，不依赖系统外观）。
任何一步失败都会静默降级为面板自绘的半透明圆角背景。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPainterPath


def reduce_motion() -> bool:
    """系统"减少动态效果"偏好"""
    try:
        from AppKit import NSWorkspace
        return bool(NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion())
    except Exception:
        return False


def attach_vibrancy(widget, dark: bool, radius: float = 12.0) -> bool:
    """给已显示的无边框窗口挂原生材质。成功返回 True。"""
    try:
        from AppKit import (NSVisualEffectView, NSVisualEffectMaterialPopover,
                            NSVisualEffectBlendingModeBehindWindow,
                            NSVisualEffectStateActive, NSColor, NSWindowBelow,
                            NSAppearance)
        wid = widget.winId()
        if not wid:
            return False
        root = widget._pyobjc_view() if hasattr(widget, "_pyobjc_view") \
            else __import__("objc").objc_object(c_void_p=int(wid))
        win = root.window()
        if win is None or root.superview() is None:
            return False
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        eff = NSVisualEffectView.alloc().initWithFrame_(root.bounds())
        eff.setMaterial_(NSVisualEffectMaterialPopover)
        eff.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        eff.setState_(NSVisualEffectStateActive)
        eff.setAutoresizingMask_(18)                     # 宽高跟随
        eff.setWantsLayer_(True)
        eff.layer().setCornerRadius_(radius)
        eff.layer().setMasksToBounds_(True)
        try:
            name = "NSAppearanceNameDarkAqua" if dark else "NSAppearanceNameAqua"
            eff.setAppearance_(NSAppearance.appearanceNamed_(name))
        except Exception:
            pass
        root.superview().addSubview_positioned_relativeTo_(eff, NSWindowBelow, root)
        widget._effect_view = eff
        return True
    except Exception:
        return False


def detach_vibrancy(widget):
    eff = getattr(widget, "_effect_view", None)
    if eff is not None:
        try:
            eff.removeFromSuperview()
        except Exception:
            pass
        widget._effect_view = None


def paint_panel_background(widget, dark: bool, radius: float = 12.0,
                           vibrancy_ok: bool = False):
    """面板背景绘制：有材质时只画描边，无材质时画半透明圆角底"""
    p = QPainter(widget)
    p.setRenderHint(QPainter.Antialiasing)
    r = widget.rect().adjusted(0, 0, -1, -1)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    if not vibrancy_ok:
        from PySide6.QtWidgets import QApplication
        base = QColor("#F2F2F4") if not dark else QColor("#28282A")
        base.setAlpha(246 if not dark else 242)
        p.fillPath(path, base)
    border = QColor(0, 0, 0, 36) if not dark else QColor(255, 255, 255, 28)
    p.setPen(border)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()

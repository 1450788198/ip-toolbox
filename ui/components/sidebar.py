"""侧边栏导航：分组标题 + 图标条目（右端实时状态徽标），固定 220px"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..icons import nav_icon
from ..common import make_app_icon


class NavButton(QPushButton):
    """导航项：左图标 + 文字，右端可挂实时状态徽标（如 已连接/总数、路由条数）

    徽标样式用 setStyleSheet 令牌直供（全局 QSS 的按钮子控件后代选择器
    在部分平台上不生效，曾导致白字白底），主题切换时由 refresh_badge 重刷。
    """

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._badge = QLabel("", self)
        self._badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._badge.hide()
        self._badge_kind = "muted"
        self._badge_dark = False
        self._badge_text = ""

    def set_badge(self, text: str, kind: str = "muted"):
        self._badge_text = text or ""
        self._badge_kind = kind or "muted"
        if text:
            self._badge.setText(text)
            self._badge.setStyleSheet(self._badge_qss())
            self._badge.adjustSize()
            self._badge.show()
            # 布局可能尚未稳定（首次设置时按钮宽度未定），下一拍再定位
            QTimer.singleShot(0, self._reposition)
        else:
            self._badge.hide()

    def _badge_qss(self) -> str:
        """按当前主题令牌生成徽标样式：深色文字配浅底，保证对比度"""
        from ..theme import current_tokens
        t = current_tokens()
        dark = getattr(theme_current_mgr(), "dark", False) if theme_current_mgr() else False
        self._badge_dark = dark
        if dark:
            colors = {
                "muted": (t["hover"], t["text"]),
                "ok": (t["ok_soft"], t["ok"]),
                "warn": (t["warn_soft"], t["warn"]),
                "accent": (t["accent_soft"], t["accent"]),
            }
        else:
            colors = {
                "muted": (t["sep_soft"], "#48484C"),
                "ok": (t["ok_soft"], "#1E7A45"),
                "warn": (t["warn_soft"], "#8F5600"),
                "accent": (t["accent_soft"], "#0064D2"),
            }
        bg, fg = colors.get(self._badge_kind, colors["muted"])
        if self.isChecked():
            # 选中行是蓝色填充底：徽标用反白样式保证可读
            bg, fg = "rgba(255,255,255,0.26)", "#FFFFFF"
        return (f"QLabel {{ background: {bg}; color: {fg};"
                f" border-radius: 6px; padding: 2px 8px;"
                f" font-size: 11px; font-weight: 600; }}")

    def refresh_badge(self, dark: bool):
        """主题切换后重刷徽标配色（保留文字与显隐）"""
        if self._badge.isVisible() or self._badge_text:
            self._badge.setStyleSheet(self._badge_qss())

    def _reposition(self):
        if self._badge.isVisible() and self.width() > 40:
            self._badge.move(self.width() - self._badge.width() - 11,
                             (self.height() - self._badge.height()) // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition()


def theme_current_mgr():
    from .. import theme
    return theme.current()


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, items, footer_text: str = "", parent=None):
        """items: [{"key","title","icon","group"}]，按顺序渲染，group 变化时插入分组标题"""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        self._items = items
        self.buttons = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 10, 0, 10)
        root.setSpacing(0)

        # 顶部：应用标识
        head = QHBoxLayout()
        head.setContentsMargins(14, 8, 12, 10)
        head.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(26, 26))
        logo.setFixedSize(26, 26)
        head.addWidget(logo)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        name = QLabel("IP 工具箱")
        name.setObjectName("appName")
        sub = QLabel("网络配置与工具")
        sub.setObjectName("appSub")
        title_box.addWidget(name)
        title_box.addWidget(sub)
        head.addLayout(title_box)
        head.addStretch(1)
        root.addLayout(head)

        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        root.addWidget(line)

        # 导航列表（可滚动，避免窗口变矮时截断）
        scroll = QScrollArea()
        scroll.setObjectName("navScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("navBody")
        v = QVBoxLayout(body)
        v.setContentsMargins(10, 6, 10, 10)
        v.setSpacing(3)

        current_group = None
        for it in items:
            if it.get("group") and it["group"] != current_group:
                current_group = it["group"]
                lb = QLabel(current_group)
                lb.setObjectName("navGroup")
                v.addWidget(lb)
            btn = NavButton(f"  {it['title']}")
            btn.setObjectName("navItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setIconSize(QSize(18, 18))
            btn.setProperty("key", it["key"])
            btn.clicked.connect(lambda _=False, k=it["key"]: self.navigate.emit(k))
            self.group.addButton(btn)
            self.buttons[it["key"]] = btn
            v.addWidget(btn)
        v.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # 底部：版本与平台
        foot = QLabel(footer_text or "v1.0")
        foot.setObjectName("hint")
        foot.setContentsMargins(16, 6, 12, 2)
        root.addWidget(foot)

        self.refresh_icons(False)

    def refresh_icons(self, dark: bool):
        for it in self._items:
            btn = self.buttons.get(it["key"])
            if btn:
                btn.setIcon(nav_icon(it["icon"], dark=dark, size=18))
                btn.refresh_badge(dark)

    def set_current(self, key: str):
        prev = self.group.checkedButton()
        btn = self.buttons.get(key)
        if btn:
            btn.setChecked(True)
        if prev is not None:
            prev.refresh_badge(False)
        if btn and btn is not prev:
            btn.refresh_badge(False)

    def set_badges(self, badges: dict):
        """badges: {key: (text, kind)}，kind ∈ muted/ok/warn/accent；text 为空则隐藏"""
        for key, val in (badges or {}).items():
            btn = self.buttons.get(key)
            if not btn:
                continue
            text, kind = val if isinstance(val, tuple) else (val, "muted")
            btn.set_badge(text, kind)

"""侧边栏导航：分组标题 + 图标条目（右端实时状态徽标），固定 220px"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..icons import nav_icon
from ..common import make_app_icon


class NavButton(QPushButton):
    """导航项：左图标 + 文字，右端可挂实时状态徽标（如 已连接/总数、路由条数）"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._badge = QLabel("", self)
        self._badge.setObjectName("navBadge")
        self._badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._badge.hide()

    def set_badge(self, text: str, kind: str = "muted"):
        if text:
            self._badge.setText(text)
            self._badge.setProperty("kind", kind)
            self._badge.style().unpolish(self._badge)
            self._badge.style().polish(self._badge)
            self._badge.adjustSize()
            self._badge.show()
            # 布局可能尚未稳定（首次设置时按钮宽度未定），下一拍再定位
            QTimer.singleShot(0, self._reposition)
        else:
            self._badge.hide()

    def _reposition(self):
        if self._badge.isVisible() and self.width() > 40:
            self._badge.move(self.width() - self._badge.width() - 11,
                             (self.height() - self._badge.height()) // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition()


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

    def set_current(self, key: str):
        btn = self.buttons.get(key)
        if btn:
            btn.setChecked(True)

    def set_badges(self, badges: dict):
        """badges: {key: (text, kind)}，kind ∈ muted/ok/warn/accent；text 为空则隐藏"""
        for key, val in (badges or {}).items():
            btn = self.buttons.get(key)
            if not btn:
                continue
            text, kind = val if isinstance(val, tuple) else (val, "muted")
            btn.set_badge(text, kind)

"""侧边栏导航：分组标题 + 图标条目，固定 220px"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..icons import nav_icon
from ..common import make_app_icon


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
        v.setContentsMargins(9, 4, 9, 8)
        v.setSpacing(2)

        current_group = None
        for it in items:
            if it.get("group") and it["group"] != current_group:
                current_group = it["group"]
                lb = QLabel(current_group)
                lb.setObjectName("navGroup")
                v.addWidget(lb)
            btn = QPushButton(f"  {it['title']}")
            btn.setObjectName("navItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setIconSize(QSize(16, 16))
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
                btn.setIcon(nav_icon(it["icon"], dark=dark, size=16))

    def set_current(self, key: str):
        btn = self.buttons.get(key)
        if btn:
            btn.setChecked(True)

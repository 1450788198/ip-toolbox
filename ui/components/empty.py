"""空数据状态：图标 + 标题 + 说明 + 可选操作"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..icons import svg_svg
from .. import theme


class EmptyState(QWidget):
    def __init__(self, icon_key: str, title: str, subtitle: str = "",
                 action_text: str = "", action=None, parent=None):
        super().__init__(parent)
        self.setObjectName("emptyBox")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 40, 24, 40)
        v.setSpacing(10)
        v.setAlignment(Qt.AlignCenter)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.set_icon(icon_key)
        v.addWidget(self.icon)
        self.title = QLabel(title)
        self.title.setObjectName("emptyTitle")
        self.title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.title)
        self.sub = QLabel(subtitle)
        self.sub.setObjectName("emptySub")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setWordWrap(True)
        if subtitle:
            v.addWidget(self.sub)
        if action_text:
            row = QHBoxLayout()
            row.addStretch(1)
            btn = QPushButton(action_text)
            btn.setProperty("variant", "primary")
            if action:
                btn.clicked.connect(action)
            row.addWidget(btn)
            row.addStretch(1)
            v.addLayout(row)
        self._icon_key = icon_key

    def set_icon(self, icon_key: str):
        self._icon_key = icon_key
        mgr = theme.current()
        color = theme.tokens(mgr.dark if mgr else False)["text3"]
        self.icon.setPixmap(svg_svg(icon_key, color, 44))

    def refresh_theme(self):
        self.set_icon(self._icon_key)

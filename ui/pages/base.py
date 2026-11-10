"""页面基类：统一边距、页头、滚动容器"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QVBoxLayout, QWidget)


class ScrollPage(QWidget):
    """带页头的可滚动页面：内容统一 24px 边距、16px 间距"""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("root")
        v = QVBoxLayout(inner)
        v.setContentsMargins(24, 20, 24, 24)
        v.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(12)
        box = QVBoxLayout()
        box.setSpacing(3)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("pageSub")
        self.subtitle_label.setWordWrap(True)
        box.addWidget(self.title_label)
        if subtitle:
            box.addWidget(self.subtitle_label)
        head.addLayout(box)
        head.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        v.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(16)
        v.addLayout(self.body)
        v.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def add_action(self, widget: QWidget):
        self.actions.addWidget(widget)
        return widget


class Page(QWidget):
    """不可滚动页面（表格需要撑满高度时使用），统一边距与页头"""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(12)
        box = QVBoxLayout()
        box.setSpacing(3)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("pageSub")
        self.subtitle_label.setWordWrap(True)
        box.addWidget(self.title_label)
        if subtitle:
            box.addWidget(self.subtitle_label)
        head.addLayout(box)
        head.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        v.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        v.addLayout(self.body, 1)

    def add_action(self, widget: QWidget):
        self.actions.addWidget(widget)
        return widget

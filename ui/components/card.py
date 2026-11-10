"""卡片、页头、表单网格、指标块"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QSizePolicy, QVBoxLayout, QWidget)


class Card(QFrame):
    """内容卡片：统一 12px 圆角、白底（深色为 #2C2C2E）、18px 内边距"""

    def __init__(self, title: str = "", subtitle: str = "", parent=None, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(spacing)
        self._header = None
        self._actions = None
        if title:
            self._header = QHBoxLayout()
            self._header.setSpacing(8)
            box = QVBoxLayout()
            box.setSpacing(2)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("cardTitle")
            box.addWidget(self.title_label)
            self.subtitle_label = QLabel(subtitle) if subtitle else None
            if self.subtitle_label:
                self.subtitle_label.setObjectName("cardSub")
                box.addWidget(self.subtitle_label)
            self._header.addLayout(box)
            self._header.addStretch(1)
            self._actions = QHBoxLayout()
            self._actions.setSpacing(6)
            self._header.addLayout(self._actions)
            outer.addLayout(self._header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(spacing)
        outer.addLayout(self.body)

    def add_action(self, widget: QWidget):
        """右上角操作按钮"""
        if self._actions is not None:
            self._actions.addWidget(widget)
        return widget

    def add(self, widget: QWidget, stretch: int = 0):
        self.body.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout, stretch: int = 0):
        self.body.addLayout(layout, stretch)
        return layout

    def set_subtitle(self, text: str):
        if getattr(self, "subtitle_label", None):
            self.subtitle_label.setText(text)


class PageHeader(QWidget):
    """页面标题 + 说明 + 右侧操作区"""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        box = QVBoxLayout()
        box.setSpacing(3)
        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")
        box.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("pageSub")
        if subtitle:
            box.addWidget(self.subtitle)
        h.addLayout(box)
        h.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        h.addLayout(self.actions)

    def add_action(self, widget: QWidget):
        self.actions.addWidget(widget)
        return widget


class FormGrid(QWidget):
    """标签 + 控件的表单网格（标签右对齐，控件列自适应拉伸）"""

    def __init__(self, columns: int = 2, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(9)
        self._row = 0
        self._col = 0
        self._columns = max(1, columns)
        for c in range(self._columns):
            self.grid.setColumnStretch(c * 2 + 1, 1)

    def add_row(self, label: str, widget: QWidget = None, tip: str = ""):
        """占一整行：标签在左，控件占满剩余宽度"""
        if label:
            lb = QLabel(label)
            lb.setObjectName("muted")
            lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lb.setMinimumWidth(72)
            self.grid.addWidget(lb, self._row, 0, 1, 1)
        if widget is not None:
            if tip:
                widget.setToolTip(tip)
            self.grid.addWidget(widget, self._row, 1, 1, max(1, self._columns * 2 - 1))
        self._row += 1
        return widget

    def add_pair(self, label1: str, w1: QWidget, label2: str = "", w2: QWidget = None):
        """一行放两组（2 列布局）"""
        if self._columns < 2 or w2 is None:
            return self.add_row(label1, w1)
        lb1 = QLabel(label1)
        lb1.setObjectName("muted")
        lb1.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lb2 = QLabel(label2)
        lb2.setObjectName("muted")
        lb2.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.grid.addWidget(lb1, self._row, 0)
        self.grid.addWidget(w1, self._row, 1)
        self.grid.addWidget(lb2, self._row, 2)
        self.grid.addWidget(w2, self._row, 3)
        self._row += 1

    def add_full(self, widget: QWidget):
        self.grid.addWidget(widget, self._row, 0, 1, self._columns * 2)
        self._row += 1
        return widget

    def add_separator(self):
        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        self.grid.addWidget(line, self._row, 0, 1, self._columns * 2)
        self._row += 1


class StatTile(QFrame):
    """小指标块：上方标签、下方数值（用于总览页）"""

    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("statTile")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(3)
        self.label = QLabel(label)
        self.label.setObjectName("statLabel")
        self.value = QLabel(value)
        self.value.setObjectName("statValue")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        v.addWidget(self.label)
        v.addWidget(self.value)

    def set_value(self, text: str, tooltip: str = ""):
        self.value.setText(text)
        self.value.setToolTip(tooltip or text)

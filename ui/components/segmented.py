"""分段控件（macOS Segmented Control）：DHCP / 手动 切换等"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName("segGroup")
        h = QHBoxLayout(self)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = []
        for i, text in enumerate(options):
            b = QPushButton(text)
            b.setProperty("variant", "seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(26)
            self.group.addButton(b, i)
            h.addWidget(b)
            self.buttons.append(b)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self.changed.emit)

    def index(self) -> int:
        return self.group.checkedId()

    def set_index(self, idx: int):
        if 0 <= idx < len(self.buttons):
            self.buttons[idx].setChecked(True)

    def set_option_text(self, idx: int, text: str):
        if 0 <= idx < len(self.buttons):
            self.buttons[idx].setText(text)

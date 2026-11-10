"""状态徽标：圆点 + 文本，颜色通过动态属性交给 QSS"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    """用法：badge.set_state("已连接", "ok")，state ∈ ok/warn/err/muted"""

    def __init__(self, text: str = "", state: str = "muted", parent=None):
        super().__init__(parent)
        self.setObjectName("badge")
        self._dot = "●"
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.set_state(text, state)

    def set_state(self, text: str, state: str = "muted"):
        self.setText(f"{self._dot} {text}" if text else "")
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)

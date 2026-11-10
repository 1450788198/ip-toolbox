"""轻量状态提示（Toast）：底部居中浮层，避免频繁弹 QMessageBox"""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QWidget)
from PySide6.QtGui import QColor
from PySide6.QtCore import QPropertyAnimation


class Toast(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 16, 9)
        layout.setSpacing(8)
        self.dot = QLabel("●")
        self.dot.setObjectName("toastText")
        self.text = QLabel("")
        self.text.setObjectName("toastText")
        layout.addWidget(self.dot)
        layout.addWidget(self.text)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(24)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(self._shadow)
        self.hide()

    def show_message(self, text: str, kind: str = "ok", msec: int = 2600):
        colors = {"ok": "#30A46C", "err": "#FF453A", "warn": "#E5A000", "info": "#007AFF"}
        self.dot.setStyleSheet(f"color:{colors.get(kind, colors['info'])};")
        self.text.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(msec)

    def reposition(self):
        parent = self.parentWidget()
        if not parent:
            return
        self.adjustSize()
        x = max(12, (parent.width() - self.width()) // 2)
        y = max(12, parent.height() - self.height() - 46)
        self.move(x, y)

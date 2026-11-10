"""UI 通用组件"""
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

# 运行中的 Worker 强引用集合：防止线程仍在跑时被 GC 销毁（QThread: Destroyed 崩溃）
_ACTIVE_WORKERS = set()


class Worker(QThread):
    """在后台线程执行 fn(*args)，完成后在主线程发信号"""
    ok = Signal(object)
    err = Signal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.args = args
        _ACTIVE_WORKERS.add(self)
        self.finished.connect(self._release)

    def _release(self):
        # finished 信号在线程完全结束后发射，此时释放引用是安全的
        _ACTIVE_WORKERS.discard(self)

    def run(self):
        try:
            self.ok.emit(self.fn(*self.args))
        except Exception as e:
            self.err.emit(str(e))


def make_app_icon() -> QIcon:
    """程序托盘图标：蓝色圆角方块 + 白色 IP 字样"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#2f6fd3"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("#ffffff"))
    f = QFont()
    f.setPixelSize(26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "IP")
    p.end()
    return QIcon(pm)

"""设计系统：颜色令牌、排版、QSS（浅色 / 深色 / 跟随系统）

所有页面只使用这里的令牌与组件，保证整体视觉一致。
"""
from string import Template

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#F5F5F7",
    "surface": "#FFFFFF",
    "surface2": "#FAFAFC",
    "sidebar": "#ECECF0",
    "text": "#1D1D1F",
    "text2": "#6E6E73",
    "text3": "#8E8E93",
    "sep": "#D2D2D7",
    "sep_soft": "#E8E8ED",
    "accent": "#007AFF",
    "accent_hover": "#0A6FE0",
    "accent_press": "#0059C7",
    "accent_soft": "#E3F0FF",
    "on_accent": "#FFFFFF",
    "hover": "#E3E3E8",
    "ok": "#30A46C",
    "ok_soft": "#E7F6EE",
    "warn": "#B36B00",
    "warn_soft": "#FFF4E0",
    "err": "#D93A30",
    "err_soft": "#FDECEA",
    "code_bg": "#F6F6F9",
    "sel": "#D9E9FF",
    "shadow": "rgba(0,0,0,0.06)",
}

DARK = {
    "bg": "#1C1C1E",
    "surface": "#2C2C2E",
    "surface2": "#323234",
    "sidebar": "#232325",
    "text": "#F5F5F7",
    "text2": "#A8A8AD",
    "text3": "#8E8E93",
    "sep": "#3A3A3C",
    "sep_soft": "#333335",
    "accent": "#0A84FF",
    "accent_hover": "#339CFF",
    "accent_press": "#0069D9",
    "accent_soft": "#0E3357",
    "on_accent": "#FFFFFF",
    "hover": "#3A3A3C",
    "ok": "#32D74B",
    "ok_soft": "#15351F",
    "warn": "#FFD60A",
    "warn_soft": "#3A2F10",
    "err": "#FF453A",
    "err_soft": "#3C1D1B",
    "code_bg": "#242426",
    "sel": "#0E3357",
    "shadow": "rgba(0,0,0,0.30)",
}

_QSS = Template("""
* { outline: none; }
QWidget {
    font-family: -apple-system, "SF Pro Text", "PingFang SC", "Helvetica Neue", sans-serif;
    font-size: 13px;
    color: $text;
}
QMainWindow, QDialog { background: $bg; }
QWidget#root, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QLabel { background: transparent; }
QLabel#appName { font-size: 15px; font-weight: 700; color: $text; }
QLabel#appSub { font-size: 11px; color: $text3; }
QLabel#pageTitle { font-size: 22px; font-weight: 700; color: $text; }
QLabel#pageSub { font-size: 12px; color: $text2; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; color: $text; }
QLabel#cardSub { font-size: 12px; color: $text2; }
QLabel#sectionTitle { font-size: 11px; font-weight: 600; color: $text2; }
QLabel#muted { color: $text2; font-size: 12px; }
QLabel#hint { color: $text3; font-size: 12px; }
QLabel#value { font-size: 13px; color: $text; }
QLabel#metric { font-size: 20px; font-weight: 600; color: $text; }
QLabel#mono, QLabel#monoSmall { font-family: "SF Mono", Menlo, Consolas, monospace; color: $text; }
QLabel#mono { font-size: 13px; }
QLabel#monoSmall { font-size: 11px; color: $text2; }
QLabel#ipBig {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 26px; font-weight: 600; color: $text;
}
QLabel[state="ok"] { color: $ok; }
QLabel[state="warn"] { color: $warn; }
QLabel[state="err"] { color: $err; }
QLabel[state="muted"] { color: $text2; }
QLabel#badge { font-size: 12px; font-weight: 500; }
QLabel#badge[state="ok"] { color: $ok; }
QLabel#badge[state="warn"] { color: $warn; }
QLabel#badge[state="err"] { color: $err; }
QLabel#badge[state="muted"] { color: $text2; }

/* ---------- 卡片 ---------- */
QFrame#card {
    background: $surface;
    border: 1px solid $sep_soft;
    border-radius: 12px;
}
QFrame#card QFrame#cardInner { background: transparent; border: none; }
QFrame#hline { background: $sep_soft; max-height: 1px; border: none; }
QFrame#vline { background: $sep_soft; max-width: 1px; border: none; }

/* ---------- 侧边栏 ---------- */
QWidget#sidebar { background: $sidebar; }
QScrollArea#navScroll { background: transparent; border: none; }
QWidget#navBody { background: transparent; }
QLabel#navGroup {
    color: $text3; font-size: 11px; font-weight: 600;
    padding: 14px 12px 5px 12px; letter-spacing: 0.4px;
}
QPushButton#navItem {
    text-align: left;
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0 12px;
    color: $text;
    font-size: 14px;
    font-weight: 500;
}
QPushButton#navItem:hover { background: $hover; }
QPushButton#navItem:checked { background: $accent; color: $on_accent; }
QPushButton#navItem:checked:hover { background: $accent_hover; }
/* 徽标样式由 NavButton 用令牌直供（按钮子控件的后代选择器规则不可靠） */

/* ---------- 按钮 ---------- */
QPushButton {
    background: $surface;
    border: 1px solid $sep;
    border-radius: 8px;
    padding: 5px 14px;
    min-height: 22px;
    color: $text;
}
QPushButton:hover { background: $surface2; border-color: $text3; }
QPushButton:pressed { background: $hover; }
QPushButton:disabled { color: $text3; border-color: $sep_soft; background: $surface2; }
QPushButton[variant="primary"]:disabled { background: $sep; border-color: $sep; color: $surface; }
QPushButton[variant="danger"]:disabled { color: $text3; border-color: $sep_soft; background: $surface2; }
QPushButton[variant="ghost"]:disabled { color: $text3; background: transparent; }
QPushButton[variant="primary"] {
    background: $accent; border: 1px solid $accent; color: $on_accent; font-weight: 600;
}
QPushButton[variant="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[variant="primary"]:pressed { background: $accent_press; }
QPushButton[variant="primary"]:disabled { background: $sep; border-color: $sep; color: $surface2; }
QPushButton[variant="danger"] { color: $err; border-color: $sep; }
QPushButton[variant="danger"]:hover { background: $err_soft; border-color: $err; }
QPushButton[variant="ghost"] { background: transparent; border: none; color: $accent; padding: 4px 8px; }
QPushButton[variant="ghost"]:hover { background: $accent_soft; }
QPushButton[variant="seg"] {
    border-radius: 7px; padding: 4px 16px; background: transparent;
    border: 1px solid transparent; color: $text2;
}
QPushButton[variant="seg"]:hover { color: $text; }
QPushButton[variant="seg"]:checked {
    background: $surface; color: $text; border: 1px solid $sep_soft; font-weight: 600;
}
QWidget#segGroup { background: $surface2; border: 1px solid $sep_soft; border-radius: 8px; }

/* ---------- 输入 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $surface;
    border: 1px solid $sep;
    border-radius: 8px;
    padding: 5px 9px;
    min-height: 22px;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid $accent; }
QLineEdit:read-only { background: $surface2; color: $text2; }
QLineEdit:disabled, QComboBox:disabled { background: $surface2; color: $text3; }
QLineEdit[state="err"] { border-color: $err; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow {
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid $text2; width: 0; height: 0; margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: $surface; border: 1px solid $sep; border-radius: 8px;
    padding: 4px; selection-background-color: $accent; selection-color: $on_accent;
    outline: none;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 16px; border: none; background: transparent; }
QPlainTextEdit { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 12px; }

QCheckBox { spacing: 7px; color: $text; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid $sep; background: $surface;
}
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }
QCheckBox::indicator:hover { border-color: $accent; }

/* ---------- 表格 ---------- */
QTableWidget, QTreeWidget, QListWidget#adapterList {
    background: $surface;
    border: 1px solid $sep_soft;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: $sel;
    selection-color: $text;
    alternate-background-color: $surface2;
}
QTableWidget::item { padding: 6px 8px; border: none; }
QTableWidget::item:selected { background: $sel; color: $text; }
QHeaderView::section {
    background: $surface2;
    color: $text2;
    border: none;
    border-bottom: 1px solid $sep_soft;
    padding: 6px 9px;
    font-weight: 600;
    font-size: 11px;
}
QTableCornerButton::section { background: $surface2; border: none; }
QTableWidget QTableWidget { border: none; }
QListWidget#adapterList::item {
    border-radius: 8px;
    margin: 1px 2px;
    color: $text;
}
QListWidget#adapterList::item:selected { background: $sel; }
QListWidget#adapterList::item:hover:!selected { background: $surface2; }

/* ---------- 标签页 ---------- */
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent; color: $text2; border: none;
    padding: 6px 14px; margin-right: 4px; border-radius: 7px;
}
QTabBar::tab:hover { color: $text; background: $hover; }
QTabBar::tab:selected { color: $text; background: $surface; font-weight: 600; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $sep; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $text3; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $sep; border-radius: 4px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---------- 状态栏 / 工具提示 ---------- */
QStatusBar { background: $bg; border-top: 1px solid $sep_soft; color: $text2; font-size: 11px; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $text2; font-size: 11px; padding: 0 10px; }
QToolTip {
    background: $surface; color: $text; border: 1px solid $sep;
    border-radius: 6px; padding: 4px 8px;
}
QMenu {
    background: $surface; border: 1px solid $sep; border-radius: 9px; padding: 5px;
}
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 6px; color: $text; }
QMenu::item:selected { background: $accent; color: $on_accent; }
QMenu::item:disabled { color: $text2; }
QMenu::separator { height: 1px; background: $sep_soft; margin: 4px 8px; }

/* ---------- 自定义小部件 ---------- */
QWidget#toast {
    background: $surface; border: 1px solid $sep; border-radius: 10px;
}
QLabel#toastText { color: $text; font-size: 12px; }
QWidget#emptyBox { background: transparent; }
QLabel#emptyTitle { color: $text2; font-size: 14px; font-weight: 600; }
QLabel#emptySub { color: $text3; font-size: 12px; }
QFrame#statTile { background: $surface2; border: 1px solid $sep_soft; border-radius: 10px; }
QLabel#statLabel { color: $text2; font-size: 11px; }
QLabel#statValue { color: $text; font-size: 14px; font-weight: 600; }
""")


def tokens(dark: bool) -> dict:
    return DARK if dark else LIGHT


def stylesheet(dark: bool) -> str:
    return _QSS.substitute(tokens(dark))


def is_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return app.palette().color(QPalette.Window).lightness() < 128


def palette(dark: bool) -> QPalette:
    t = tokens(dark)
    p = QPalette()
    p.setColor(QPalette.Window, QColor(t["bg"]))
    p.setColor(QPalette.WindowText, QColor(t["text"]))
    p.setColor(QPalette.Base, QColor(t["surface"]))
    p.setColor(QPalette.AlternateBase, QColor(t["surface2"]))
    p.setColor(QPalette.Text, QColor(t["text"]))
    p.setColor(QPalette.PlaceholderText, QColor(t["text3"]))
    p.setColor(QPalette.Button, QColor(t["surface"]))
    p.setColor(QPalette.ButtonText, QColor(t["text"]))
    p.setColor(QPalette.Highlight, QColor(t["accent"]))
    p.setColor(QPalette.HighlightedText, QColor(t["on_accent"]))
    p.setColor(QPalette.ToolTipBase, QColor(t["surface"]))
    p.setColor(QPalette.ToolTipText, QColor(t["text"]))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(t["text3"]))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t["text3"]))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(t["text3"]))
    return p


class ThemeManager(QObject):
    """主题管理：follow system / light / dark，切换时重建全局 QSS 并通知页面刷新图标"""
    changed = Signal(bool)          # True = 深色

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.mode = "system"
        self._dark = False
        try:
            app.styleHints().colorSchemeChanged.connect(self._system_changed)
        except Exception:
            pass

    @property
    def dark(self) -> bool:
        return self._dark

    def apply(self, mode: str = None):
        if mode:
            self.mode = mode
        self._dark = is_dark(self.app) if self.mode == "system" else (self.mode == "dark")
        self.app.setPalette(palette(self._dark))
        self.app.setStyleSheet(stylesheet(self._dark))
        self.changed.emit(self._dark)
        return self._dark

    def _system_changed(self, *_):
        if self.mode == "system":
            self.apply()
            return
        # 自定义模式下仍要跟随系统对未覆盖控件的影响，这里不重设
        self._dark = is_dark(self.app) if self.mode == "system" else (self.mode == "dark")


_THEME_REF = {}


def install(app: QApplication, mode: str = "system") -> ThemeManager:
    """创建全局主题管理器（单例），返回实例"""
    mgr = _THEME_REF.get("mgr")
    if mgr is None:
        mgr = ThemeManager(app)
        _THEME_REF["mgr"] = mgr
    mgr.apply(mode)
    return mgr


def current() -> ThemeManager:
    return _THEME_REF.get("mgr")


def current_tokens() -> dict:
    mgr = current()
    return tokens(mgr.dark if mgr else False)

"""全局主题样式（macOS 浅色原生风格：侧边栏导航）"""

STYLESHEET = """
/* ---------- 全局 ---------- */
QWidget {
    font-family: "PingFang SC", "Helvetica Neue", sans-serif;
    font-size: 13px;
    color: #1d1d1f;
}
QMainWindow, QDialog { background: #f5f5f7; }

/* ---------- 侧边栏 ---------- */
#sidebarPanel { background: #ececf1; }
#contentPanel { background: #ffffff; }
QListWidget#sidebar {
    background: transparent;
    border: none;
    outline: none;
    font-size: 13px;
}
QListWidget#sidebar::item {
    padding: 9px 12px;
    margin: 2px 4px;
    border-radius: 8px;
    color: #2c2c2e;
}
QListWidget#sidebar::item:selected {
    background: #2f6fd3;
    color: #ffffff;
}
QListWidget#sidebar::item:hover:!selected { background: #dfdee4; }
QLabel#pageTitle { font-size: 21px; font-weight: 600; }
QLabel#pageTip { color: #86868b; font-size: 12px; }
QFrame#pageLine { color: #e8e8ed; }

/* ---------- 侧边栏底部按钮 ---------- */
QPushButton#aboutBtn {
    background: transparent; border: none; border-radius: 6px;
    padding: 4px 10px; font-size: 12px; color: #86868b;
}
QPushButton#aboutBtn:hover { background: #dfdee4; color: #515154; }

/* ---------- 表格 ---------- */
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f7f8fa;
    border: 1px solid #e5e5e8;
    border-radius: 8px;
    gridline-color: #ececef;
    selection-background-color: #dbe7fb;
    selection-color: #1d1d1f;
}
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected { border-radius: 4px; }
QHeaderView::section {
    background: #f7f7f9;
    color: #6e6e73;
    border: none;
    border-bottom: 1px solid #e5e5e8;
    padding: 7px 10px;
    font-weight: 600;
    font-size: 12px;
}
QTableCornerButton::section { background: #f7f7f9; border: none; }

/* ---------- 按钮 ---------- */
QPushButton {
    background: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 6px 16px;
    color: #1d1d1f;
}
QPushButton:hover { background: #f0f0f2; }
QPushButton:pressed { background: #e4e4e8; }
QPushButton:disabled { color: #b0b0b5; background: #f5f5f7; border-color: #e5e5e8; }
QPushButton#primaryBtn {
    background: #2f6fd3; color: #ffffff; border: none;
    padding: 7px 20px; font-weight: 600;
}
QPushButton#primaryBtn:hover { background: #275cb4; }
QPushButton#primaryBtn:pressed { background: #214e9c; }
QPushButton#primaryBtn:disabled { background: #a9c3ec; color: #eef3fb; border: none; }
QPushButton#dangerBtn {
    background: #ffffff; color: #d0342c; border: 1px solid #e8b9b6;
}
QPushButton#dangerBtn:hover { background: #fdf1f0; }

/* ---------- 输入框 ---------- */
QLineEdit {
    background: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: #2f6fd3;
}
QLineEdit:focus { border-color: #2f6fd3; }

/* ---------- 分组框 ---------- */
QGroupBox {
    background: #fafafc;
    border: 1px solid #e5e5e8;
    border-radius: 9px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: 1px;
    color: #515154;
    font-size: 12px;
    font-weight: 600;
}

/* ---------- 下拉框 ---------- */
QComboBox {
    background: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 5px 10px;
}
QComboBox:hover { border-color: #b8b8bd; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d2d2d7;
    selection-background-color: #dbe7fb;
    selection-color: #1d1d1f;
}

/* ---------- 其他 ---------- */
QPlainTextEdit {
    border: 1px solid #e5e5e8;
    border-radius: 8px;
    background: #fbfbfd;
}
QStatusBar { background: #f5f5f7; color: #6e6e73; font-size: 12px; }
QStatusBar QLabel { color: #6e6e73; font-size: 12px; padding: 0 8px; }
QLabel { background: transparent; }
QCheckBox { spacing: 6px; }
QDoubleSpinBox {
    background: #ffffff; border: 1px solid #d2d2d7;
    border-radius: 6px; padding: 4px 8px;
}
"""


def app_stylesheet() -> str:
    return STYLESHEET


# 托盘菜单专用样式：保留半透明玻璃质感，但保证文字对比度（覆盖 macOS 原生液态玻璃的低对比渲染）
TRAY_MENU_QSS = """
QMenu#trayMenu {
    background-color: rgba(250, 250, 252, 0.96);
    border: 1px solid rgba(0, 0, 0, 0.14);
    border-radius: 10px;
    padding: 5px 0;
    font-size: 13px;
}
QMenu#trayMenu::item {
    padding: 6px 18px;
    color: #1d1d1f;
    background: transparent;
}
QMenu#trayMenu::item:disabled {
    color: #7c7c82;              /* 状态行：灰但清晰可读 */
    font-weight: 500;
}
QMenu#trayMenu::item:selected {
    background-color: #2f6fd3;
    color: #ffffff;
}
QMenu#trayMenu::separator {
    height: 1px;
    background: rgba(0, 0, 0, 0.12);
    margin: 4px 10px;
}
"""

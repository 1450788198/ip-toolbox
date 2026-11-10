"""主窗口：macOS 原生标题栏 + 220px 侧边栏 + 页面栈 + 状态栏 + Network Control 菜单栏面板"""
import datetime
import os
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                               QStackedWidget, QStatusBar, QVBoxLayout, QWidget)

from core import presets as preset_store
from core import settings
from core.dhcp_controller import DhcpController, app_data_dir
from core.netbase import IS_MAC, IS_WIN
from core.netstate import NetworkState
from core.net_mac import MacBackend
from core.net_win import WinBackend
from . import theme
from .common import Worker
from .components import Sidebar, Toast
from .dialogs import confirm
from .menubar import Panel, menubar_icon, tooltip_text
from .pages.dashboard import DashboardPage
from .pages.dhcp import DhcpPage
from .pages.dns import DnsPage
from .pages.history import HistoryPage
from .pages.network import NetworkPage
from .pages.routes import RoutesPage
from .pages.settings import SettingsPage, VERSION
from .pages.subnet import MaskPage, SubnetPage
from .pages.vlsm import VlsmPage

NAV = [
    {"group": "网络管理", "key": "dashboard", "title": "总览", "icon": "dashboard"},
    {"key": "network", "title": "网卡管理", "icon": "network"},
    {"key": "routes", "title": "路由管理", "icon": "routes"},
    {"key": "dhcp", "title": "DHCP 服务", "icon": "dhcp"},
    {"group": "网络工具", "key": "subnet", "title": "子网计算器", "icon": "calc"},
    {"key": "vlsm", "title": "VLSM 划分", "icon": "vlsm"},
    {"key": "mask", "title": "掩码速查", "icon": "mask"},
    {"key": "dns", "title": "DNS 测速", "icon": "dns"},
    {"group": "系统", "key": "history", "title": "操作记录", "icon": "history"},
    {"key": "settings", "title": "设置", "icon": "settings"},
]


def get_backend():
    if IS_MAC:
        return MacBackend()
    if IS_WIN:
        return WinBackend()
    raise RuntimeError("不支持的平台")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.backend = get_backend()
        self.ifaces = []
        self._workers = []
        self.state = NetworkState(self.backend, self)
        self.setWindowTitle("IP 工具箱")
        self.setMinimumSize(1080, 700)
        self.resize(1240, 800)
        self._build()
        self._build_tray()
        self.log(f"IP 工具箱 v{VERSION} 已启动（{self.backend.name}）")

    # ---------------- 布局 ----------------
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.sidebar = Sidebar(NAV, footer_text=f"v{VERSION} · {self.backend.name}")
        self.sidebar.navigate.connect(self.go_to)
        h.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.pages = {
            "dashboard": DashboardPage(self.backend, self.log, self.notify),
            "network": NetworkPage(self.backend, self.log, self.notify),
            "routes": RoutesPage(self.backend, self.log, self.notify),
            "dhcp": DhcpPage(self.backend, self.log, self.notify),
            "subnet": SubnetPage(self.notify),
            "vlsm": VlsmPage(self.notify),
            "mask": MaskPage(self.notify),
            "dns": DnsPage(self.backend, self.log, self.notify),
            "history": HistoryPage(self.notify),
            "settings": SettingsPage(self.backend, self.log, self.notify),
        }
        for key, page in self.pages.items():
            self.stack.addWidget(page)
            page.state = self.state          # 共享 Network State

        self.pages["dashboard"].navigate.connect(self.go_to)
        self.pages["dashboard"].open_iface.connect(self._open_iface)
        self.pages["network"].ifaces_changed.connect(self._ifaces_changed)
        self.pages["settings"].settings_applied.connect(self._settings_applied)

        self.toast = Toast(root)
        self._build_statusbar()

        if theme.current():
            theme.current().changed.connect(self._theme_changed)
        self.sidebar.set_current("dashboard")
        self.stack.setCurrentWidget(self.pages["dashboard"])
        QTimer.singleShot(1500, self._maybe_prompt_elevation)

    def _build_statusbar(self):
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.lbl_platform = QLabel(self.backend.name)
        self.lbl_ifaces = QLabel("网卡 —")
        self.lbl_elev = QLabel("免密授权 —")
        self.lbl_dhcp = QLabel("DHCP —")
        sb.addWidget(self.lbl_platform)
        sb.addWidget(self.lbl_ifaces)
        sb.addPermanentWidget(self.lbl_elev)
        sb.addPermanentWidget(self.lbl_dhcp)
        self.setStatusBar(sb)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start(3000)
        QTimer.singleShot(300, self._poll_status)

    def _poll_status(self):
        from core.elevation import is_installed
        try:
            running = DhcpController().is_running()
        except Exception:
            running = False
        self.lbl_dhcp.setText("DHCP 运行中" if running else "DHCP 未运行")
        self.lbl_dhcp.setProperty("state", "ok" if running else "muted")
        self.lbl_dhcp.style().unpolish(self.lbl_dhcp)
        self.lbl_dhcp.style().polish(self.lbl_dhcp)
        try:
            ok = is_installed()
        except Exception:
            ok = False
        self.lbl_elev.setText("免密授权已开启" if ok else "免密授权未开启")
        self.lbl_elev.setProperty("state", "ok" if ok else "muted")
        self.lbl_elev.style().unpolish(self.lbl_elev)
        self.lbl_elev.style().polish(self.lbl_elev)

    # ---------------- 导航 ----------------
    def go_to(self, key: str):
        page = self.pages.get(key)
        if not page:
            return
        self.stack.setCurrentWidget(page)
        self.sidebar.set_current(key)
        hook = getattr(page, "on_show", None)
        if hook:
            hook()

    def _open_iface(self, service: str):
        self.pages["network"].select_service(service)

    def _ifaces_changed(self, ifaces):
        self.ifaces = ifaces
        self.lbl_ifaces.setText(f"网卡 {len(ifaces)} 个")
        self.pages["dhcp"].set_ifaces(ifaces)

    def _settings_applied(self):
        self.pages["network"].reload_settings()
        self.pages["dashboard"].refresh()
        self.state.set_interval(settings.get("refresh_interval"))
        self.state.refresh()
        # 菜单栏图标模式可能已变化，立即应用
        self.tray.setIcon(menubar_icon(settings.get("menu_bar_icon"),
                                       self.state.snapshot()))

    def _theme_changed(self, dark: bool):
        self.sidebar.refresh_icons(dark)
        for page in self.pages.values():
            hook = getattr(page, "refresh_theme", None)
            if hook:
                hook()

    # ---------------- 提示与日志 ----------------
    def notify(self, text: str, kind: str = "ok"):
        if getattr(self, "toast", None):
            self.toast.show_message(text, kind)
            self.toast.reposition()

    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")
        try:
            log_file = os.path.join(app_data_dir(), "app.log")
            with open(log_file, "a", encoding="utf-8") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] [{level}] {msg}\n")
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "toast", None):
            self.toast.reposition()

    # ---------------- Network Control 菜单栏 ----------------
    def _build_tray(self):
        from PySide6.QtWidgets import QSystemTrayIcon
        self.panel = Panel(self.state)
        self.panel.open_main.connect(self._show_window)
        self.panel.open_settings.connect(self._open_settings)
        self.panel.open_diagnostics.connect(self._open_diagnostics)
        self.panel.open_dhcp.connect(self._open_dhcp)
        self.panel.apply_preset_requested.connect(self._apply_preset_from_panel)
        self.panel.quit_requested.connect(self._quit)

        self.tray = QSystemTrayIcon(menubar_icon(settings.get("menu_bar_icon"),
                                                self.state.snapshot()), self)
        self.tray.setToolTip(tooltip_text(self.state.snapshot()))
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.state.updated.connect(self._on_state)
        self.state.start()

    def _tray_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.Context):
            self.panel.toggle_at(QCursor.pos())

    def _on_state(self, snap: dict):
        """共享状态更新：菜单栏图标 + 面板 + 主窗口各页"""
        mode = settings.get("menu_bar_icon")
        self.tray.setIcon(menubar_icon(mode, snap))
        self.tray.setToolTip(tooltip_text(snap))
        self.panel.update_state(snap)

        ifaces = snap.get("ifaces") or []
        if ifaces and ifaces != self.ifaces:
            self.ifaces = ifaces
            self.lbl_ifaces.setText(f"网卡 {len(ifaces)} 个")
            self.pages["dhcp"].set_ifaces(ifaces)
        self.pages["network"].apply_state(snap)
        self.pages["dashboard"].apply_state(snap)
        self._update_nav_badges(snap)

    def _update_nav_badges(self, snap: dict):
        """侧边栏右端实时徽标：填满右半空间并直接给出关键状态"""
        try:
            ifaces = snap.get("ifaces") or []
            up = sum(1 for i in ifaces if i.get("status") == "up")
            total = len(ifaces)
            routes_n = len(snap.get("routes") or [])
            badges = {
                "network": (f"{up}/{total}", "ok" if up else "muted"),
                "routes": (f"{routes_n} 条", "accent" if routes_n else "muted"),
                "dhcp": ("运行中", "ok") if snap.get("dhcp_running")
                        else ("未运行", "muted"),
            }
            try:
                from core import history as hist
                badges["history"] = (f"{len(hist.load())} 条", "muted")
            except Exception:
                pass
            self.sidebar.set_badges(badges)
        except Exception:
            pass

    def _open_settings(self):
        self._show_window()
        self.go_to("settings")

    def _open_diagnostics(self):
        self._show_window()
        self.go_to("dns")
        self.notify("网络诊断：已打开 DNS 测速（连通性与延迟）", "info")

    def _open_dhcp(self):
        self._show_window()
        self.go_to("dhcp")

    def _apply_preset_from_panel(self, p: dict):
        svc = p["service"]
        err = preset_store.validate_preset(p)
        if err:
            self.panel.show_toast(f"方案无效：{err}", "err")
            return

        def job():
            if p.get("mode") == "static":
                self.backend.set_static_ip(svc, p.get("ip", ""),
                                           p.get("mask", "255.255.255.0"),
                                           p.get("router", ""))
            else:
                self.backend.set_dhcp(svc)
            if p.get("dns"):
                self.backend.set_dns(svc, p["dns"])
            return True

        w = Worker(job)
        w.ok.connect(lambda _: (self.panel.show_toast(f"已切换到「{p['name']}」"),
                                self.state.refresh()))
        w.err.connect(lambda m: self.panel.show_toast(f"切换失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    # ---------------- 授权 ----------------
    def _install_elevation(self, quiet=False):
        from core.elevation import install, is_installed

        def job():
            if is_installed():
                return True
            return install()

        w = Worker(job)
        w.ok.connect(lambda _: (self.log("免密授权已开启"),
                                self.notify("免密授权已开启，之后操作不再需要密码"),
                                self._poll_status(), self.state.refresh()))
        w.err.connect(lambda m: self.notify(f"授权失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _maybe_prompt_elevation(self):
        from core.elevation import is_installed
        try:
            if is_installed():
                return
        except Exception:
            return
        if confirm(self, "开启免密操作",
                   "检测到尚未开启免密授权。\n\n"
                   "现在通过 Touch ID / 密码授权一次，之后修改 IP、添加路由、"
                   "启动 DHCP 都不再需要输入密码。\n\n"
                   "原理：写入 /etc/sudoers.d 命令白名单，删除该文件即可撤销。",
                   "开启"):
            self._install_elevation()

    # ---------------- 窗口 ----------------
    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self.state.stop()
        self.panel.close()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if getattr(self, "_really_quit", False):
            event.accept()
            return
        event.ignore()
        self.hide()
        from PySide6.QtWidgets import QSystemTrayIcon
        self.tray.showMessage("IP 工具箱", "已最小化到菜单栏，点击菜单栏图标打开 Network Control",
                              QSystemTrayIcon.Information, 3000)


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("IP 工具箱")
    app.setQuitOnLastWindowClosed(False)
    theme.install(app, settings.get("appearance") or "system")

    from .common import _ACTIVE_WORKERS

    def _drain_workers():
        for w in list(_ACTIVE_WORKERS):
            w.wait(10000)

    app.aboutToQuit.connect(_drain_workers)
    win = MainWindow()

    def _after_unlock():
        theme.install(app, settings.get("appearance") or "system")
        if not settings.get("start_minimized"):
            win.show()
        win._maybe_prompt_elevation()

    from core.biometric import authenticate, biometry_available
    from PySide6.QtWidgets import QMessageBox

    def _gate():
        while True:
            ok, err = authenticate("解锁 IP 工具箱")
            if ok:
                _after_unlock()
                return
            if "cancel" in (err or "").lower() or "取消" in (err or ""):
                ret = QMessageBox.question(None, "已取消验证",
                                           "指纹验证已取消。重新验证还是退出？",
                                           QMessageBox.Retry | QMessageBox.Close)
            else:
                ret = QMessageBox.question(None, "验证失败",
                                           f"指纹验证未通过：{err or '未知原因'}\n重试还是退出？",
                                           QMessageBox.Retry | QMessageBox.Close)
            if ret != QMessageBox.Retry:
                app.quit()
                return

    if biometry_available():
        QTimer.singleShot(150, _gate)
    else:
        _after_unlock()
    sys.exit(app.exec())

"""主窗口：macOS 原生标题栏 + 220px 侧边栏 + 页面栈 + 状态栏 + 菜单栏托盘"""
import datetime
import os
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                               QMenu, QStackedWidget, QStatusBar,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from core import presets as preset_store
from core import settings
from core.dhcp_controller import DhcpController, app_data_dir
from core.netbase import IS_MAC, IS_WIN, is_system_route
from core.net_mac import MacBackend
from core.net_win import WinBackend
from . import theme
from .common import Worker
from .components import Sidebar, Toast
from .dialogs import confirm
from .icons import make_tray_icon
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

    # ---------------- 托盘 ----------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_tray_icon(), self)
        self.tray.setToolTip("IP 工具箱")
        self._rebuild_tray_menu()
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._tray_timer = QTimer(self)
        self._tray_timer.timeout.connect(self._refresh_tray)
        self._tray_timer.start(6000)

    def _refresh_tray(self):
        def job():
            routes = self.backend.list_routes()
            dns = {}
            for i in self.ifaces or []:
                svc = i.get("service")
                if i.get("ipv4") and svc:
                    try:
                        dns[svc] = self.backend.get_dns(svc)
                    except Exception:
                        dns[svc] = []
            return routes, dns

        w = Worker(job)
        w.ok.connect(lambda r: self._rebuild_tray_menu(r[0], r[1]))
        w.err.connect(lambda _: self._rebuild_tray_menu([], {}))
        w.start()
        self._workers.append(w)

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.Context):
            self._tray_menu.popup(QCursor.pos())

    def _rebuild_tray_menu(self, routes=None, dns=None):
        dark = theme.current().dark if theme.current() else False
        menu = QMenu()
        menu.setObjectName("trayMenu")
        menu.setStyleSheet(theme.tray_menu_qss(dark))
        dns = dns or {}

        def prefix(mask):
            try:
                import ipaddress
                return f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}', strict=False).prefixlen}"
            except Exception:
                return ""

        ifaces = [i for i in (self.ifaces or []) if i.get("ipv4")]
        if not ifaces:
            menu.addAction("未获取到 IP 地址").setEnabled(False)
        for i in ifaces:
            svc = i.get("service") or i.get("port")
            menu.addAction(f"{svc} ({i.get('device')})").setEnabled(False)
            menu.addAction(f"    IP    {i.get('ipv4')}{prefix(i.get('mask') or '')}"
                           f"    掩码 {i.get('mask') or '—'}").setEnabled(False)
            menu.addAction(f"    网关  {i.get('router') or '—'}").setEnabled(False)
            menu.addAction(f"    DNS   {', '.join((dns.get(svc) or [])[:3]) or '—'}").setEnabled(False)

        menu.addSeparator()
        biz = [r for r in (routes or []) if not is_system_route(r)]
        menu.addAction(f"手工路由：{len(biz)} 条").setEnabled(False)
        for r in biz[:5]:
            menu.addAction(f"    {r['destination']}  →  {r.get('gateway') or '直连'}").setEnabled(False)
        if len(biz) > 5:
            menu.addAction(f"    … 共 {len(biz)} 条").setEnabled(False)

        menu.addSeparator()
        running = self._dhcp_running()
        menu.addAction(f"DHCP 服务：{'运行中' if running else '未运行'}").setEnabled(False)
        act_dhcp = QAction("停止 DHCP 服务" if running else "启动 DHCP 服务…", menu)
        act_dhcp.triggered.connect(self._toggle_dhcp_from_tray)
        menu.addAction(act_dhcp)

        from core.elevation import is_installed
        if not is_installed():
            act = QAction("开启免密授权（Touch ID / 密码，一次即可）")
            act.triggered.connect(self._install_elevation)
            menu.addAction(act)

        menu.addSeparator()
        presets = preset_store.load_presets()
        if presets:
            for i, p in enumerate(presets):
                act = QAction(f"切换到「{p['name']}」({p.get('service')})", menu)
                act.triggered.connect(lambda checked=False, idx=i: self._apply_preset_from_tray(idx))
                menu.addAction(act)
            menu.addSeparator()

        act_show = QAction("打开主窗口")
        act_show.triggered.connect(self._show_window)
        menu.addAction(act_show)
        act_quit = QAction("退出")
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)
        self._tray_menu = menu

    def _dhcp_running(self):
        try:
            return DhcpController().is_running()
        except Exception:
            return False

    def _toggle_dhcp_from_tray(self):
        ctrl = DhcpController()
        if ctrl.is_running():
            w = Worker(ctrl.stop)
            w.ok.connect(lambda _: (self._refresh_tray(), self._poll_status(),
                                    self.pages["dhcp"]._poll()))
            w.start()
            self._workers.append(w)
        else:
            self._show_window()
            self.go_to("dhcp")
            self.notify("请在 DHCP 服务页确认地址池后启动", "info")

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
                                self._poll_status(), self._refresh_tray()))
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

    # ---------------- 托盘方案切换 ----------------
    def _apply_preset_from_tray(self, idx):
        presets = preset_store.load_presets()
        if idx >= len(presets):
            return
        p = presets[idx]
        svc = p["service"]

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
        w.ok.connect(lambda _: (self.notify(f"已切换到「{p['name']}」"),
                                self.pages["network"].refresh(),
                                self.tray.showMessage("IP 工具箱",
                                                      f"已切换到「{p['name']}」",
                                                      QSystemTrayIcon.Information, 3000)))
        w.err.connect(lambda m: (self.notify(f"切换失败：{m}", "err"),
                                 self.tray.showMessage("切换失败", m,
                                                       QSystemTrayIcon.Critical, 4000)))
        w.start()
        self._workers.append(w)

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if getattr(self, "_really_quit", False):
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage("IP 工具箱", "已最小化到菜单栏，点击菜单栏图标可打开菜单",
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

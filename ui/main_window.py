"""主窗口：macOS 原生标题栏 + 220px 侧边栏 + 页面栈 + 状态栏 + Network Control 菜单栏面板"""
import sys
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                               QStackedWidget, QStatusBar, QVBoxLayout, QWidget)

from core import applog
from core import presets as preset_store
from core import settings
from core.netbase import IS_MAC, IS_WIN, normalize_mask
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
        self._preset_job = None       # 正在下发的方案（防重复提交）
        self._verify = None           # 方案下发后的状态核验
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

    @staticmethod
    def _set_state_label(lbl: QLabel, text: str, state: str):
        if lbl.text() == text and lbl.property("state") == state:
            return
        lbl.setText(text)
        lbl.setProperty("state", state)
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)

    def _poll_status(self):
        """状态栏只读共享快照，不再单独执行系统命令（避免重复采集）"""
        self._update_statusbar(self.state.snapshot())

    def _update_statusbar(self, snap: dict):
        running = bool(snap.get("dhcp_running"))
        self._set_state_label(self.lbl_dhcp, "DHCP 运行中" if running else "DHCP 未运行",
                              "ok" if running else "muted")
        elev = snap.get("elevation_ok")
        self._set_state_label(self.lbl_elev,
                              "免密授权已开启" if elev else "免密授权未开启",
                              "ok" if elev else "muted")

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
        applog.log(msg, level)

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
        self.panel.open_dns.connect(self._open_dns)
        self.panel.open_dhcp.connect(self._open_dhcp)
        self.panel.open_iface.connect(self._open_iface_from_panel)
        self.panel.apply_preset_requested.connect(self._apply_preset_from_panel)
        self.panel.quit_requested.connect(self._quit)

        self.tray = QSystemTrayIcon(menubar_icon(settings.get("menu_bar_icon"),
                                                self.state.snapshot()), self)
        self.tray.setToolTip(tooltip_text(self.state.snapshot()))
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.state.updated.connect(self._on_state)
        self.state.start()

    def _tray_rect(self):
        """菜单栏图标的全局矩形；拿不到有效值时返回 None（由面板回退鼠标位置）"""
        try:
            g = self.tray.geometry()
            if g.isValid() and g.width() > 0 and g.height() > 0:
                return g
        except Exception as exc:
            applog.exception("读取菜单栏图标位置", exc)
        return None

    def _tray_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.Context):
            self.panel.toggle_at(QCursor.pos(), self._tray_rect())

    def _on_state(self, snap: dict):
        """共享状态更新：菜单栏图标 + 面板 + 主窗口各页（唯一数据入口）"""
        mode = settings.get("menu_bar_icon")
        self.tray.setIcon(menubar_icon(mode, snap))
        self.tray.setToolTip(tooltip_text(snap))
        self.panel.update_state(snap)

        ifaces = snap.get("ifaces") or []
        if ifaces != self.ifaces:
            self.ifaces = ifaces
            self.lbl_ifaces.setText(f"网卡 {len(ifaces)} 个")
            self.pages["dhcp"].set_ifaces(ifaces)
        self.pages["network"].apply_state(snap)
        self.pages["dashboard"].apply_state(snap)
        self._update_statusbar(snap)
        self._update_nav_badges(snap)

    def _update_nav_badges(self, snap: dict):
        """侧边栏右端实时徽标：填满右半空间并直接给出关键状态"""
        from .menubar.status import classify_iface
        try:
            ifaces = snap.get("ifaces") or []
            up = sum(1 for i in ifaces if classify_iface(i) == "up")
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
            except Exception as exc:
                applog.exception("侧边栏徽标-操作记录", exc)
            self.sidebar.set_badges(badges)
        except Exception as exc:
            applog.exception("侧边栏徽标", exc)

    def _open_settings(self):
        self._show_window()
        self.go_to("settings")

    def _open_dns(self):
        """菜单栏「DNS 测速」入口：打开 DNS 测速页（不冒充 Ping/Traceroute）"""
        self._show_window()
        self.go_to("dns")

    def _open_dhcp(self):
        self._show_window()
        self.go_to("dhcp")

    def _open_iface_from_panel(self, svc: str):
        self._show_window()
        self.go_to("network")
        self.pages["network"].select_service(svc)

    # ---------------- 方案下发（含真实状态核验） ----------------
    def _apply_preset_from_panel(self, p: dict):
        if self._preset_job is not None:
            return                      # 防重复提交
        svc = p.get("service") or ""
        err = preset_store.validate_preset(p)
        if err:
            self.panel.preset_apply_end(False, f"方案无效：{err}", "err")
            return

        self._preset_job = p

        def job():
            """返回 dict：dns_error 非空表示「IP 成功、DNS 失败」的部分成功"""
            res = {"dns_error": ""}
            if p.get("mode") == "static":
                self.backend.set_static_ip(svc, p.get("ip", ""),
                                           p.get("mask", "255.255.255.0"),
                                           p.get("router", ""))
            else:
                self.backend.set_dhcp(svc)
            if p.get("dns"):
                try:
                    self.backend.set_dns(svc, list(p["dns"]))
                except Exception as exc:
                    res["dns_error"] = str(exc) or "DNS 设置失败"
            return res

        w = Worker(job)
        w.ok.connect(lambda res: self._preset_dispatched(p, res))
        w.err.connect(self._preset_dispatch_failed)
        w.start()
        self._workers.append(w)
        self.log(f"应用方案「{p.get('name')}」→ {svc}")

    def _preset_dispatched(self, p: dict, res: dict):
        self.state.refresh()
        if res.get("dns_error"):
            msg = f"部分成功：IP 已切换，但 DNS 设置失败（{res['dns_error']}）"
            self._preset_finish(False, msg, "warn")
            self.notify(msg, "err")
            return
        self._verify = {"preset": p, "deadline": time.time() + 9.0}
        QTimer.singleShot(900, self._verify_tick)

    def _preset_dispatch_failed(self, msg: str):
        msg = f"切换失败：{msg}"
        self._preset_finish(False, msg, "err")
        self.notify(msg, "err")
        self.state.refresh()

    def _preset_finish(self, ok: bool, msg: str, kind: str):
        self._preset_job = None
        self._verify = None
        self.panel.preset_apply_end(ok, msg, kind)
        self.log(msg, "INFO" if ok else "WARN")

    @staticmethod
    def _preset_matches(p: dict, snap: dict) -> bool:
        """用采集到的真实状态判断方案是否真的生效（不信任命令返回值）"""
        svc = p.get("service") or ""
        ifc = next((i for i in snap.get("ifaces") or []
                    if (i.get("service") or i.get("device")) == svc), None)
        if not ifc:
            return False
        d = (snap.get("detail") or {}).get(svc, {})
        if p.get("mode") == "static":
            if (ifc.get("ipv4") or "") != (p.get("ip") or ""):
                return False
            try:
                if normalize_mask(ifc.get("mask") or "") != normalize_mask(p.get("mask") or ""):
                    return False
            except ValueError:
                return False
        else:
            if d.get("mode") != "dhcp":
                return False
        if p.get("dns"):
            if list(d.get("dns") or []) != list(p["dns"]):
                return False
        return True

    def _verify_tick(self):
        v = self._verify
        if not v:
            return
        snap = self.state.snapshot()
        if snap.get("refreshing"):
            QTimer.singleShot(500, self._verify_tick)
            return
        p = v["preset"]
        if self._preset_matches(p, snap):
            self._preset_finish(True, f"已应用「{p.get('name')}」并生效", "ok")
            self.notify(f"已切换到「{p.get('name')}」", "ok")
            return
        if time.time() > v["deadline"]:
            msg = "配置已下发，但未从系统读到生效状态，请检查当前配置"
            self._preset_finish(False, msg, "warn")
            self.notify(msg, "err")
            return
        self.state.refresh()
        QTimer.singleShot(900, self._verify_tick)

    def _open_dhcp(self):
        self._show_window()
        self.go_to("dhcp")

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

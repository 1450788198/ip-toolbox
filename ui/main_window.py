"""主窗口：macOS 侧边栏导航 + 内容区 + 状态栏托盘 + 日志"""
import os
import sys

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QIcon
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QStackedWidget,
                               QStatusBar, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from core.netbase import IS_MAC, IS_WIN
from core.net_mac import MacBackend
from core.net_win import WinBackend
from .common import Worker
from .icons import nav_icon, svg_svg, make_tray_icon
from .tabs_network import NetworkTab, IpConfigTab
from .tabs_presets import PresetsTab
from .tabs_routes import RoutesTab
from .tabs_dhcp import DhcpTab
from .tabs_subnet import SubnetTab
from .tabs_dns import DnsTab


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
        self.resize(1120, 720)
        self._build_statusbar()
        self._build_nav()
        self._build_tray()
        self.log("IP 工具箱已启动（平台: %s）" % self.backend.name)

    # ---- 状态栏（窗口底部）----
    def _build_statusbar(self):
        self.lbl_platform = QLabel(self.backend.name)
        self.lbl_ifaces = QLabel("网卡: -")
        self.lbl_dhcp = QLabel("DHCP: -")
        sb = QStatusBar()
        sb.addWidget(self.lbl_platform)
        sb.addWidget(self.lbl_ifaces)
        sb.addPermanentWidget(self.lbl_dhcp)
        self.setStatusBar(sb)
        self._dhcp_timer = QTimer(self)
        self._dhcp_timer.timeout.connect(self._poll_dhcp_status)
        self._dhcp_timer.start(2000)

    def _poll_dhcp_status(self):
        from core.dhcp_controller import DhcpController
        try:
            running = DhcpController().is_running()
        except Exception:
            running = False
        self.lbl_dhcp.setText("DHCP 服务: 运行中" if running else "DHCP 服务: 未运行")

    # ---- 侧边栏 + 内容区 ----
    def _build_nav(self):
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # 左侧栏
        sidebar = QWidget()
        sidebar.setObjectName("sidebarPanel")
        sidebar.setFixedWidth(216)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(10, 48, 10, 14)
        sv.setSpacing(4)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setIconSize(QSize(17, 17))
        # 导航结构定义：group=分组标题 / spacer=间隔 / item=(key, 名称)
        # 行号 → 页面序号的映射动态计算（_row_to_page），DHCP 行号存入 _row_dhcp 供托盘跳转
        nav_defs = [
            ("group", "系统"),
            ("spacer",),
            ("item", "network", "网卡管理"),
            ("item", "ip", "IP 配置"),
            ("item", "presets", "IP 方案"),
            ("item", "routes", "路由管理"),
            ("item", "dhcp", "DHCP 服务"),
            ("group", "工具"),
            ("spacer",),
            ("item", "calc", "子网计算器"),
            ("item", "dns", "DNS 查询"),
        ]
        self._row_to_page = {}
        page_idx = 0
        for d in nav_defs:
            if d[0] == "group":
                it = QListWidgetItem(d[1])
                it.setFlags(Qt.NoItemFlags)
                it.setForeground(Qt.gray)
                self.nav.addItem(it)
            elif d[0] == "spacer":
                it = QListWidgetItem()
                it.setFlags(Qt.NoItemFlags)
                it.setSizeHint(QSize(0, 8))
                self.nav.addItem(it)
            else:
                _, key, name = d
                it = QListWidgetItem(name)
                it.setIcon(nav_icon(key))
                it.setData(Qt.UserRole, key)
                self.nav.addItem(it)
                self._row_to_page[self.nav.count() - 1] = page_idx
                if key == "dhcp":
                    self._row_dhcp = self.nav.count() - 1
                page_idx += 1
        self.nav.setCurrentRow(2)
        sv.addWidget(self.nav, 1)

        # 底部：关于
        hb = QHBoxLayout()
        hb.setContentsMargins(6, 4, 6, 0)
        btn_about = QPushButton("关于 IP 工具箱")
        btn_about.setObjectName("aboutBtn")
        btn_about.setFixedHeight(28)
        btn_about.setToolTip("关于 IP 工具箱")
        btn_about.clicked.connect(self._show_about)
        hb.addWidget(btn_about)
        hb.addStretch(1)
        sv.addLayout(hb)

        h.addWidget(sidebar)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet("color:#d8d8dc;")
        h.addWidget(line)

        # 右侧内容
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentPanel")
        h.addWidget(self.stack, 1)

        self.tab_network = NetworkTab(self.backend, self.log, self._sync_ifaces)
        self.tab_ip = IpConfigTab(self.backend, self.log)
        self.tab_presets = PresetsTab(self.backend, self.log, self.on_preset_applied)
        self.tab_routes = RoutesTab(self.backend, self.log)
        self.tab_dhcp = DhcpTab(self.backend, self.log)
        self.tab_subnet = SubnetTab(self.log)
        self.tab_dns = DnsTab(self.backend, self.log)

        pages = [
            ("网卡管理", self.tab_network, "查看与管理所有网卡：状态、启用/禁用"),
            ("IP 配置", self.tab_ip, "设置主 IP（静态/DHCP/DNS），同一网卡添加多个附加 IP"),
            ("IP 方案", self.tab_presets, "保存常用 IP/DNS 组合，一键切换（状态栏也可切换）"),
            ("路由管理", self.tab_routes, "查看 IPv4 路由表，添加/删除静态与持久路由"),
            ("DHCP 服务", self.tab_dhcp, "为 BMC/新设备临时提供 DHCP 自动分配（需管理员授权）"),
            ("子网计算器", self.tab_subnet, "输入 IP 与掩码即算：网络/广播地址、可用主机范围与数量、二进制视图"),
            ("DNS 查询", self.tab_dns, "国内公共 DNS 一览、一键测速，选择后应用到指定网卡"),
        ]
        for title, widget, tip in pages:
            self.stack.addWidget(self._wrap_page(title, tip, widget))

        self.nav.currentRowChanged.connect(self._nav_changed)
        self.stack.setCurrentIndex(0)
        self.setCentralWidget(central)

        # 初始化数据（网卡管理页自带自动轮询，变化会经 _sync_ifaces 联动各页）
        self.tab_network.refresh()
        # 启动后检查一次性免密授权（未授权则引导开启，Touch ID / 密码一次即可）
        QTimer.singleShot(2000, self._maybe_prompt_elevation)

    def _nav_changed(self, i):
        idx = self._row_to_page.get(i)
        if idx is None:      # 分组标题 / 间隔行不可选
            return
        self.stack.setCurrentIndex(idx)
        if idx == 1:  # 切到 IP 配置页时即时刷新网卡与附加 IP
            self.tab_ip._reload_interfaces()
        elif idx == 3:  # 切到路由管理页时即时刷新路由表
            self.tab_routes.refresh()
        elif idx == 6:  # 切到 DNS 查询页时刷新网卡下拉
            self.tab_dns.reload_ifaces()

    def _wrap_page(self, title: str, tip: str, widget: QWidget) -> QWidget:
        """内容区页头（大标题 + 说明）+ 页面主体"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 16)
        v.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("pageTitle")
        v.addWidget(t)
        d = QLabel(tip)
        d.setObjectName("pageTip")
        v.addWidget(d)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("pageLine")
        v.addWidget(line)
        v.addWidget(widget, 1)
        return page

    def _show_about(self):
        QMessageBox.about(self, "关于 IP 工具箱",
                          "IP 工具箱\n\n网卡管理 · 多 IP · 方案切换 · 路由 · DHCP 服务\n\n"
                          "关闭窗口会最小化到状态栏，从托盘菜单可完全退出。")

    def _sync_ifaces(self, ifaces):
        """网卡管理页检测到网卡列表/IP 变化时联动：状态栏 + IP 配置页 + DHCP 页"""
        self.ifaces = ifaces
        self.lbl_ifaces.setText(f"网卡: {len(ifaces)} 个")
        self.tab_ip.update_ifaces(ifaces)
        self.tab_dhcp.set_ifaces(ifaces)

    def on_preset_applied(self):
        self.tab_network.refresh()

    # ---- 日志 ----
    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")
        try:
            import datetime
            from core.dhcp_controller import app_data_dir
            log_file = os.path.join(app_data_dir(), "app.log")
            with open(log_file, "a", encoding="utf-8") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] [{level}] {msg}\n")
        except Exception:
            pass
        self.statusBar().showMessage(msg, 5000)

    # ---- 状态栏托盘 ----
    def _build_tray(self):
        from .icons import make_tray_icon
        self.tray = QSystemTrayIcon(make_tray_icon(), self)
        self.tray.setToolTip("IP 工具箱")
        self._rebuild_tray_menu()
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        # 托盘状态定时刷新（IP / 手工路由 / DHCP 状态）
        self._tray_timer = QTimer(self)
        self._tray_timer.timeout.connect(self._refresh_tray)
        self._tray_timer.start(6000)

    def _refresh_tray(self):
        """后台取最新路由与 DNS，回主线程重建托盘菜单"""
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
        # 与主窗口解耦：点击托盘只弹出菜单，不再拉起主窗口
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.Context):
            self._tray_menu.popup(QCursor.pos())

    def _rebuild_tray_menu(self, routes=None, dns=None):
        """重建托盘菜单：顶部状态区（网卡 IP 明细 / 手工路由 / DHCP）+ 操作区"""
        menu = QMenu()
        menu.setObjectName("trayMenu")
        from .style import TRAY_MENU_QSS
        menu.setStyleSheet(TRAY_MENU_QSS)
        dns = dns or {}

        def mask_to_prefix(mask: str) -> str:
            try:
                import ipaddress
                return f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}', strict=False).prefixlen}"
            except (ValueError, OSError):
                return ""

        # --- 状态区（只读）：网卡 IP 明细 ---
        ifaces = self.ifaces or []
        shown_ip = False
        for i in ifaces:
            if not i.get("ipv4"):
                continue
            shown_ip = True
            svc = i["service"] or i["port"]
            menu.addAction(f"{svc} ({i['device']})").setEnabled(False)
            menu.addAction(f"    IP    {i['ipv4']}{mask_to_prefix(i.get('mask') or '')}"
                           f"    掩码 {i.get('mask') or '—'}").setEnabled(False)
            menu.addAction(f"    网关  {i.get('router') or '—'}").setEnabled(False)
            d = dns.get(svc) or []
            menu.addAction(f"    DNS   {', '.join(d[:3]) or '—'}").setEnabled(False)
        if not shown_ip:
            act = menu.addAction("未获取到 IP 地址")
            act.setEnabled(False)

        menu.addSeparator()
        # 手工路由（业务视图：默认/VPN/系统路由已排除）
        from core.netbase import is_system_route
        biz = [r for r in (routes or []) if not is_system_route(r)]
        hdr = menu.addAction(f"手工路由：{len(biz)} 条")
        hdr.setEnabled(False)
        for r in biz[:5]:
            act = menu.addAction(f"    {r['destination']}  →  {r.get('gateway') or '直连'}")
            act.setEnabled(False)
        if len(biz) > 5:
            more = menu.addAction(f"    … 共 {len(biz)} 条")
            more.setEnabled(False)

        menu.addSeparator()
        # DHCP 服务状态
        dhcp_running = self._dhcp_running()
        st = menu.addAction(f"DHCP 服务：{'运行中' if dhcp_running else '未运行'}")
        st.setEnabled(False)
        act_dhcp = QAction("停止 DHCP 服务" if dhcp_running else "启动 DHCP 服务…", menu)
        act_dhcp.triggered.connect(self._toggle_dhcp_from_tray)
        menu.addAction(act_dhcp)

        # 一次性免密授权入口
        from core.elevation import is_installed as _elev_installed
        self._elev_ok = _elev_installed()
        if not self._elev_ok:
            act_elev = QAction("开启免密授权（Touch ID / 密码，一次即可）")
            act_elev.triggered.connect(self._install_elevation)
            menu.addAction(act_elev)

        menu.addSeparator()
        # --- IP 方案一键切换 ---
        from core import presets as preset_store
        presets = preset_store.load_presets()
        if presets:
            for i, p in enumerate(presets):
                act = QAction(f"切换到「{p['name']}」({p.get('service')})", menu)
                act.triggered.connect(
                    lambda checked=False, idx=i: self._apply_preset_from_tray(idx))
                menu.addAction(act)
            menu.addSeparator()

        act_show = QAction("打开主窗口", menu)
        act_show.triggered.connect(self._show_window)
        menu.addAction(act_show)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)
        self._tray_menu = menu
        # 注意：不要调用 tray.setContextMenu()——macOS 上它会由系统自动弹原生菜单，
        # 与 _tray_activated 里的手动 popup() 叠加成两层。菜单统一由点击事件手动弹出。

    def _dhcp_running(self):
        from core.dhcp_controller import DhcpController
        try:
            return DhcpController().is_running()
        except Exception:
            return False

    # ---- 一次性免密授权 ----
    def _install_elevation(self):
        """弹一次系统授权框（Touch ID/密码），写入 sudoers 白名单"""
        self.log("请求一次性免密授权（Touch ID / 密码）...")
        from core.elevation import install, is_installed

        def job():
            if is_installed():
                return True
            return install()

        w = Worker(job)
        w.ok.connect(lambda _: (self.log("免密授权已开启，之后修改 IP / 路由 / DHCP 不再需要输密码"),
                                self.tray.showMessage("IP 工具箱",
                                    "免密授权已开启，操作不再需要输密码",
                                    QSystemTrayIcon.Information, 4000),
                                self._refresh_tray()))
        w.err.connect(lambda m: (self.log(f"免密授权失败: {m}", "WARN"),))
        w.start()
        self._workers.append(w)

    def _maybe_prompt_elevation(self):
        """启动 2 秒后检查：未授权且用户同意时引导开启免密"""
        from PySide6.QtWidgets import QMessageBox
        from core.elevation import is_installed
        if is_installed():
            self.log("免密授权已生效")
            return
        ret = QMessageBox.question(
            self, "开启免密操作",
            "检测到尚未开启免密授权。\n\n"
            "现在通过 Touch ID / 密码授权一次，之后修改 IP、\n"
            "添加路由、启动 DHCP 都不再需要输入密码。\n\n"
            "（原理：写入 /etc/sudoers.d 命令白名单，删除该文件即可撤销）",
            QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            self._install_elevation()
        else:
            self.log("跳过免密授权（可在托盘菜单中随时开启；未授权时每次操作会弹系统授权框）")

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _apply_preset_from_tray(self, idx):
        from core import presets as preset_store
        presets = preset_store.load_presets()
        if idx >= len(presets):
            return
        p = presets[idx]
        svc = p["service"]
        self.log(f"（托盘）应用方案「{p['name']}」到 {svc}")

        def job():
            if p["mode"] == "static":
                self.backend.set_static_ip(svc, p["ip"], p.get("mask", "255.255.255.0"),
                                           p.get("router", ""))
            else:
                self.backend.set_dhcp(svc)
            if "dns" in p:
                self.backend.set_dns(svc, p.get("dns") or [])
            return True

        w = Worker(job)
        w.ok.connect(lambda _: (self.log(f"方案「{p['name']}」已生效"),
                                self.tray.showMessage("IP 工具箱",
                                    f"已切换到方案「{p['name']}」",
                                    QSystemTrayIcon.Information, 3000),
                                self.tab_network.refresh()))
        w.err.connect(lambda m: (self.log(f"托盘切换失败: {m}", "ERROR"),
                                 self.tray.showMessage("切换失败", m,
                                                       QSystemTrayIcon.Critical, 5000)))
        w.start()
        self._workers.append(w)

    def _toggle_dhcp_from_tray(self):
        from core.dhcp_controller import DhcpController
        ctrl = DhcpController()
        if ctrl.is_running():
            w = Worker(ctrl.stop)
            w.ok.connect(lambda _: (self._refresh_tray(), self._poll_dhcp_status()))
            w.start()
        else:
            self._show_window()
            self.nav.setCurrentRow(getattr(self, "_row_dhcp", 6))  # DHCP 页
            self.tray.showMessage("IP 工具箱", "请在 DHCP 服务页配置并启动",
                                  QSystemTrayIcon.Information, 3000)

    def _quit(self):
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if getattr(self, "_really_quit", False):
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage("IP 工具箱", "已最小化到状态栏，点击菜单栏图标可打开菜单",
                              QSystemTrayIcon.Information, 3000)


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("IP 工具箱")
    app.setQuitOnLastWindowClosed(False)
    from .style import app_stylesheet
    app.setStyleSheet(app_stylesheet())
    from .common import _ACTIVE_WORKERS

    def _drain_workers():
        for w in list(_ACTIVE_WORKERS):
            w.wait(10000)
    app.aboutToQuit.connect(_drain_workers)
    win = MainWindow()

    # ---- 指纹解锁门：有 Touch ID 时须先验证才显示主窗口 ----
    from PySide6.QtWidgets import QMessageBox

    def _gate():
        from core.biometric import authenticate
        while True:
            ok, err = authenticate("解锁 IP 工具箱")
            if ok:
                win.show()
                win._maybe_prompt_elevation()
                return
            if "cancel" in (err or "").lower() or "取消" in (err or ""):
                ret = QMessageBox.question(
                    None, "已取消验证",
                    "指纹验证已取消。重新验证还是退出？",
                    QMessageBox.Retry | QMessageBox.Close)
                if ret != QMessageBox.Retry:
                    app.quit()
                    return
                continue
            ret = QMessageBox.question(
                None, "验证失败",
                f"指纹验证未通过：{err or '未知原因'}\n重试还是退出？",
                QMessageBox.Retry | QMessageBox.Close)
            if ret != QMessageBox.Retry:
                app.quit()
                return

    from core.biometric import biometry_available
    if biometry_available():
        QTimer.singleShot(150, _gate)     # 窗口创建但先不显示，验证通过再亮出
    else:
        win.show()                        # 无指纹硬件：直接进入
    sys.exit(app.exec())

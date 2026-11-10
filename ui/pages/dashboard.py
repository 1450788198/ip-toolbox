"""总览：当前连接、网卡概览、DHCP 状态、最近操作、快捷方案"""
import ipaddress

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import presets as preset_store
from core import history, settings
from core.dhcp_controller import DhcpController
from core.netbase import iface_is_external, sort_interfaces
from ..common import Worker
from ..components import Card, StatTile, StatusBadge
from .base import ScrollPage


def _prefix(mask: str) -> str:
    try:
        return f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}', strict=False).prefixlen}"
    except Exception:
        return ""


class DashboardPage(ScrollPage):
    navigate = Signal(str)
    open_iface = Signal(str)

    def __init__(self, backend, log, notify, parent=None):
        super().__init__("总览", "当前网络状态、服务运行情况与常用入口")
        self.backend = backend
        self.log = log
        self.notify = notify
        self.ifaces = []
        self.presets = []
        self._workers = []
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(10000)
        QTimer.singleShot(120, self.refresh)

    # ---------------- UI ----------------
    def _build(self):
        btn = QPushButton("刷新")
        btn.clicked.connect(self.refresh)
        self.add_action(btn)

        row = QHBoxLayout()
        row.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        right = QVBoxLayout()
        right.setSpacing(16)
        row.addLayout(left, 2)
        row.addLayout(right, 1)
        self.body.addLayout(row)

        # ---- 当前连接 ----
        self.card_conn = Card("当前连接", "优先显示默认网卡或外置网卡")
        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_service = QLabel("正在读取…")
        self.lbl_service.setObjectName("cardTitle")
        self.badge_conn = StatusBadge("", "muted")
        self.btn_detail = QPushButton("管理")
        self.btn_detail.setProperty("variant", "ghost")
        self.btn_detail.clicked.connect(lambda: self.navigate.emit("network"))
        top.addWidget(self.lbl_service)
        top.addWidget(self.badge_conn)
        top.addStretch(1)
        top.addWidget(self.btn_detail)
        self.card_conn.add_layout(top)

        self.lbl_ip = QLabel("—")
        self.lbl_ip.setObjectName("ipBig")
        self.lbl_ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.card_conn.add(self.lbl_ip)

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tile_mask = StatTile("子网掩码")
        self.tile_gw = StatTile("默认网关")
        self.tile_dns = StatTile("DNS")
        self.tile_rate = StatTile("链路速率")
        for t in (self.tile_mask, self.tile_gw, self.tile_dns, self.tile_rate):
            tiles.addWidget(t, 1)
        self.card_conn.add_layout(tiles)

        self.lbl_detail = QLabel("")
        self.lbl_detail.setObjectName("hint")
        self.lbl_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.card_conn.add(self.lbl_detail)
        left.addWidget(self.card_conn)

        # ---- 网卡概览 ----
        card_list = Card("网卡概览", "按外置 / 已连接优先排序，点击行进入管理")
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["网络服务", "接口", "类型", "状态", "IPv4"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.verticalHeader().setDefaultSectionSize(32)
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tbl.setMinimumHeight(190)
        self.tbl.cellDoubleClicked.connect(self._row_activated)
        card_list.add(self.tbl, 1)
        left.addWidget(card_list, 1)

        # ---- DHCP ----
        card_dhcp = Card("DHCP 服务", "为 BMC / 新上架设备临时分配地址")
        drow = QHBoxLayout()
        self.badge_dhcp = StatusBadge("未运行", "muted")
        drow.addWidget(self.badge_dhcp)
        drow.addStretch(1)
        btn_dhcp = QPushButton("配置")
        btn_dhcp.setProperty("variant", "ghost")
        btn_dhcp.clicked.connect(lambda: self.navigate.emit("dhcp"))
        drow.addWidget(btn_dhcp)
        card_dhcp.add_layout(drow)
        self.lbl_pool = QLabel("启动后可查看地址池与租约")
        self.lbl_pool.setObjectName("hint")
        self.lbl_pool.setWordWrap(True)
        card_dhcp.add(self.lbl_pool)
        right.addWidget(card_dhcp)

        # ---- 快捷方案 ----
        self.card_presets = Card("快捷方案", "一键切换常用 IP 配置")
        self.preset_box = QVBoxLayout()
        self.preset_box.setSpacing(6)
        self.card_presets.add_layout(self.preset_box)
        right.addWidget(self.card_presets)

        # ---- 最近操作 ----
        card_hist = Card("最近操作", "只记录真实的配置变更")
        self.hist_box = QVBoxLayout()
        self.hist_box.setSpacing(6)
        card_hist.add_layout(self.hist_box)
        btn_hist = QPushButton("查看全部记录")
        btn_hist.setProperty("variant", "ghost")
        btn_hist.clicked.connect(lambda: self.navigate.emit("history"))
        card_hist.add(btn_hist)
        right.addWidget(card_hist)
        right.addStretch(1)

    # ---------------- 数据 ----------------
    def on_show(self):
        self.refresh()

    def refresh(self):
        if any(w.isRunning() for w in self._workers):
            return

        def job():
            ifaces = sort_interfaces(self.backend.list_interfaces())
            state = DhcpController().read_state()
            dns, rate = [], ""
            default_svc = settings.get("default_iface")
            current = None
            for i in ifaces:
                if default_svc and i.get("service") == default_svc:
                    current = i
                    break
            if current is None:
                candidates = [i for i in ifaces if i.get("ipv4")]
                candidates.sort(key=lambda i: (not iface_is_external(i), i.get("status") != "up"))
                current = candidates[0] if candidates else (ifaces[0] if ifaces else None)
            if current and current.get("service"):
                try:
                    dns = self.backend.get_dns(current["service"])
                except Exception:
                    dns = []
                if hasattr(self.backend, "link_info"):
                    try:
                        rate = self.backend.link_info(current["device"])
                    except Exception:
                        rate = ""
            return {"ifaces": ifaces, "state": state, "dns": dns, "rate": rate,
                    "current": current, "history": history.load()[-5:],
                    "presets": preset_store.load_presets()}

        w = Worker(job)
        w.ok.connect(self._fill)
        w.err.connect(lambda m: self.log(f"总览刷新失败: {m}", "WARN"))
        w.start()
        self._workers.append(w)

    def _fill(self, data):
        self.ifaces = data["ifaces"]
        current = data.get("current")
        self._fill_connection(current, data.get("dns") or [], data.get("rate") or "")
        self._fill_table(self.ifaces)
        self._fill_dhcp(data.get("state") or {})
        self._fill_history(data.get("history") or [])
        self._fill_presets(data.get("presets") or [])

    def _fill_connection(self, ifc, dns, rate):
        if not ifc:
            self.lbl_service.setText("未检测到网卡")
            self.badge_conn.set_state("", "muted")
            self.lbl_ip.setText("—")
            self.lbl_detail.setText("")
            for t in (self.tile_mask, self.tile_gw, self.tile_dns, self.tile_rate):
                t.set_value("—")
            return
        svc = ifc.get("service") or ifc.get("port")
        self.lbl_service.setText(svc)
        status, state = {
            "up": ("已连接", "ok"), "down": ("断开", "warn"),
            "absent": ("未插入", "warn"),
        }.get(ifc.get("status"), ("未知", "muted"))
        self.badge_conn.set_state(status, state)
        ip = ifc.get("ipv4") or ""
        self.lbl_ip.setText(f"{ip}{_prefix(ifc.get('mask', ''))}" if ip else "未获取到 IP")
        self.tile_mask.set_value(ifc.get("mask") or "—")
        self.tile_gw.set_value(ifc.get("router") or "—")
        self.tile_dns.set_value(", ".join(dns[:2]) if dns else "自动")
        self.tile_rate.set_value(rate or "—")
        kind = "外置 / USB" if iface_is_external(ifc) else "内置"
        self.lbl_detail.setText(
            f"接口 {ifc.get('device', '—')}　·　{kind}　·　"
            f"硬件端口 {ifc.get('port', '—')}　·　MAC {ifc.get('mac') or '—'}")

    def _fill_table(self, ifaces):
        self.tbl.setRowCount(0)
        for i in ifaces:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            status = {"up": "已连接", "down": "断开", "absent": "未插入"}.get(
                i.get("status"), "未知")
            vals = [i.get("service") or i.get("port"), i.get("device"),
                    "USB" if iface_is_external(i) else "内置", status,
                    i.get("ipv4") or "—"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 3:
                    it.setForeground(
                        Qt.darkGreen if i.get("status") == "up"
                        else Qt.gray if i.get("status") == "down"
                        else Qt.darkYellow)
                if c == 4:
                    f = it.font()
                    f.setFamily("Menlo")
                    it.setFont(f)
                self.tbl.setItem(r, c, it)
            self.tbl.item(r, 0).setData(Qt.UserRole, i.get("service") or i.get("port"))

    def _fill_dhcp(self, state):
        running = bool(state.get("running"))
        self.badge_dhcp.set_state("运行中" if running else "未运行", "ok" if running else "muted")
        cfg = state.get("config") or state.get("cfg") or {}
        pool = f"{cfg.get('start')} ~ {cfg.get('end')}" if cfg.get("start") else ""
        if running:
            leases = state.get("leases") or {}
            self.lbl_pool.setText(
                f"{cfg.get('interface', '')}　地址池 {pool or '—'}　已分配 {len(leases)} 个")
        else:
            self.lbl_pool.setText("启动后可查看地址池与租约")

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _fill_history(self, items):
        self._clear_layout(self.hist_box)
        if not items:
            lb = QLabel("暂无操作记录")
            lb.setObjectName("hint")
            self.hist_box.addWidget(lb)
            return
        for it in reversed(items):
            row = QVBoxLayout()
            row.setSpacing(1)
            t = QLabel(f"{it.get('action', '')}")
            t.setObjectName("value")
            s = QLabel(f"{it.get('time', '')[5:16]}　{it.get('service', '') or '—'}")
            s.setObjectName("hint")
            row.addWidget(t)
            row.addWidget(s)
            self.hist_box.addLayout(row)

    def _fill_presets(self, presets):
        self.presets = presets
        self._clear_layout(self.preset_box)
        if not presets:
            lb = QLabel("尚未保存方案，可在网卡管理中保存当前配置")
            lb.setObjectName("hint")
            lb.setWordWrap(True)
            self.preset_box.addWidget(lb)
            return
        for i, p in enumerate(presets[:4]):
            btn = QPushButton(f"切换到「{p['name']}」")
            btn.setToolTip(f"{p.get('service')} · {p.get('ip') or 'DHCP'}")
            btn.clicked.connect(lambda _=False, idx=i: self._apply_preset(idx))
            self.preset_box.addWidget(btn)

    # ---------------- 操作 ----------------
    def _row_activated(self, row, _col):
        item = self.tbl.item(row, 0)
        if not item:
            return
        service = item.data(Qt.UserRole) or item.text()
        self.open_iface.emit(service)
        self.navigate.emit("network")

    def _apply_preset(self, idx):
        if idx >= len(self.presets):
            return
        p = self.presets[idx]
        svc = p.get("service")

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
        w.ok.connect(lambda _: self._preset_done(p))
        w.err.connect(lambda m: (self.log(f"应用方案失败: {m}", "ERROR"),
                                 self.notify(f"应用失败：{m}", "err")))
        w.start()
        self._workers.append(w)

    def _preset_done(self, p):
        history.record("应用方案", p.get("service", ""),
                       "当前配置", f"{p.get('name')} · {p.get('ip') or 'DHCP'}",
                       "成功", "从总览快捷方案应用")
        self.notify(f"已切换到「{p.get('name')}」")
        self.refresh()

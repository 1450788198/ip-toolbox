"""DHCP 服务：状态、配置、租约、运行日志（独立提权进程）"""
import ipaddress

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core import history
from core.dhcp_controller import DhcpController
from core.netbase import iface_is_external, normalize_mask, sort_interfaces
from ..common import Worker
from ..components import Card, PageHeader, StatusBadge
from ..dialogs import confirm
from .base import Page


class DhcpPage(Page):
    def __init__(self, backend, log, notify, parent=None):
        super().__init__("DHCP 服务", "为 BMC / 新上架设备临时提供地址分配，独立提权进程运行")
        self.backend = backend
        self.log = log
        self.notify = notify
        self.ctrl = DhcpController()
        self.ifaces = []
        self._workers = []
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1500)
        self._poll()

    # ---------------- UI ----------------
    def _build(self):
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self._reload)
        self.add_action(self.btn_refresh)

        # ---- 状态 ----
        status = Card("服务状态", "由独立进程运行，关闭主窗口不影响服务")
        row = QHBoxLayout()
        row.setSpacing(14)
        self.badge = StatusBadge("未运行", "muted")
        self.lbl_summary = QLabel("尚未启动")
        self.lbl_summary.setObjectName("hint")
        self.lbl_summary.setWordWrap(True)
        row.addWidget(self.badge)
        row.addWidget(self.lbl_summary, 1)
        self.btn_start = QPushButton("启动服务")
        self.btn_start.setProperty("variant", "primary")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = QPushButton("停止服务")
        self.btn_stop.setProperty("variant", "danger")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_stop)
        status.add_layout(row)
        self.body.addWidget(status)

        mid = QHBoxLayout()
        mid.setSpacing(16)

        # ---- 配置 ----
        cfg = Card("服务配置", "地址池需与监听网卡在同一网段")
        self.form = QGridLayout()
        self.form.setHorizontalSpacing(12)
        self.form.setVerticalSpacing(9)
        self.form.setColumnStretch(1, 1)
        r = 0
        self.form.addWidget(self._lab("监听网卡"), r, 0)
        self.cmb_iface = QComboBox()
        self.cmb_iface.currentIndexChanged.connect(self._iface_changed)
        self.form.addWidget(self.cmb_iface, r, 1)
        r += 1
        self.form.addWidget(self._lab("服务器 IP"), r, 0)
        self.ed_server = QLineEdit()
        self.ed_server.setPlaceholderText("留空则使用网卡当前 IP")
        self.form.addWidget(self.ed_server, r, 1)
        r += 1
        self.form.addWidget(self._lab("地址池"), r, 0)
        pool = QHBoxLayout()
        pool.setSpacing(6)
        self.ed_start = QLineEdit()
        self.ed_start.setPlaceholderText("起始")
        self.ed_end = QLineEdit()
        self.ed_end.setPlaceholderText("结束")
        pool.addWidget(self.ed_start)
        pool.addWidget(QLabel("~"))
        pool.addWidget(self.ed_end)
        self.form.addLayout(pool, r, 1)
        r += 1
        self.form.addWidget(self._lab("子网掩码"), r, 0)
        self.ed_mask = QLineEdit("255.255.255.0")
        self.ed_mask.setPlaceholderText("255.255.255.0 或 24")
        self.form.addWidget(self.ed_mask, r, 1)
        r += 1
        self.form.addWidget(self._lab("下发网关"), r, 0)
        self.ed_router = QLineEdit()
        self.ed_router.setPlaceholderText("默认与服务器 IP 相同")
        self.form.addWidget(self.ed_router, r, 1)
        r += 1
        self.form.addWidget(self._lab("下发 DNS"), r, 0)
        self.ed_dns = QLineEdit()
        self.ed_dns.setPlaceholderText("逗号分隔，留空则下发服务器 IP")
        self.form.addWidget(self.ed_dns, r, 1)
        r += 1
        self.form.addWidget(self._lab("租约时长"), r, 0)
        self.sp_lease = QDoubleSpinBox()
        self.sp_lease.setRange(0.1, 72.0)
        self.sp_lease.setSingleStep(0.5)
        self.sp_lease.setValue(1.0)
        self.sp_lease.setSuffix(" 小时")
        self.form.addWidget(self.sp_lease, r, 1)
        cfg.add_layout(self.form)
        mid.addWidget(cfg, 3)

        # ---- 租约 ----
        lease = Card("当前租约", "OFFER 阶段即预留地址，避免并发冲突")
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["分配 IP", "客户端 MAC", "到期时间"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.verticalHeader().setDefaultSectionSize(30)
        h = self.tbl.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl.setMinimumHeight(210)
        lease.add(self.tbl, 1)
        self.lbl_lease = QLabel("尚无租约")
        self.lbl_lease.setObjectName("hint")
        lease.add(self.lbl_lease)
        mid.addWidget(lease, 2)
        self.body.addLayout(mid, 1)

        # ---- 日志 ----
        logcard = Card("运行日志", "最近 100 行")
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setMinimumHeight(120)
        self.txt.setMaximumHeight(160)
        self.txt.setPlaceholderText("启动服务后，这里会显示地址分配过程…")
        logcard.add(self.txt)
        self.body.addWidget(logcard)

    @staticmethod
    def _lab(text):
        lb = QLabel(text)
        lb.setObjectName("muted")
        lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lb

    # ---------------- 网卡 ----------------
    def on_show(self):
        self._poll()
        if not self.ifaces:
            self._reload()

    def set_ifaces(self, ifaces):
        self.ifaces = sort_interfaces(ifaces) or []
        cur = self.cmb_iface.currentData()
        cur_svc = cur.get("service") if isinstance(cur, dict) else None
        self.cmb_iface.blockSignals(True)
        self.cmb_iface.clear()
        for i in self.ifaces:
            label = f"{i.get('service') or i.get('port')} ({i.get('device')})"
            if iface_is_external(i):
                label += " · USB"
            if not i.get("ipv4"):
                label += " · 无 IP"
            self.cmb_iface.addItem(label, i)
        idx = 0
        if cur_svc:
            for k in range(self.cmb_iface.count()):
                d = self.cmb_iface.itemData(k)
                if isinstance(d, dict) and d.get("service") == cur_svc:
                    idx = k
                    break
        self.cmb_iface.setCurrentIndex(idx)
        self.cmb_iface.blockSignals(False)
        if self.ifaces:
            self._iface_changed(idx)

    def _reload(self):
        w = Worker(self.backend.list_interfaces)
        w.ok.connect(self.set_ifaces)
        w.start()
        self._workers.append(w)

    def _iface_changed(self, _idx):
        ifc = self.cmb_iface.currentData()
        if not isinstance(ifc, dict):
            return
        ip = ifc.get("ipv4") or ""
        if not ip:
            return
        self.ed_server.setText(ip)
        self.ed_router.setText(ip)
        try:
            net = ipaddress.ip_network(f"{ip}/{ifc.get('mask') or '24'}", strict=False)
            hosts = list(net.hosts())
            if len(hosts) >= 2:
                self.ed_start.setText(str(hosts[min(100, len(hosts) - 2)]))
                self.ed_end.setText(str(hosts[min(150, len(hosts) - 1)]))
            self.ed_mask.setText(ifc.get("mask") or "255.255.255.0")
        except Exception:
            pass

    # ---------------- 启停 ----------------
    def _collect(self) -> dict:
        ifc = self.cmb_iface.currentData()
        if not isinstance(ifc, dict):
            raise ValueError("请先选择监听网卡")
        server_ip = self.ed_server.text().strip() or ifc.get("ipv4") or ""
        if not server_ip:
            raise ValueError("该网卡没有 IP，请先配置网卡地址或手动填写服务器 IP")
        try:
            ipaddress.IPv4Address(server_ip)
        except ValueError:
            raise ValueError(f"服务器 IP 无效：{server_ip}")
        start, end = self.ed_start.text().strip(), self.ed_end.text().strip()
        if not start or not end:
            raise ValueError("地址池起始与结束不能为空")
        try:
            if ipaddress.IPv4Address(end) < ipaddress.IPv4Address(start):
                raise ValueError("地址池结束地址小于起始地址")
        except ValueError as e:
            raise ValueError(f"地址池无效：{e}")
        try:
            mask = normalize_mask(self.ed_mask.text() or "255.255.255.0")
        except ValueError as e:
            raise ValueError(f"掩码有误：{e}")
        dns = [x.strip() for x in self.ed_dns.text().replace("，", ",").split(",") if x.strip()]
        return {"interface": ifc.get("service") or ifc.get("port"),
                "device": ifc.get("device"), "server_ip": server_ip,
                "start": start, "end": end, "mask": mask,
                "router": self.ed_router.text().strip() or server_ip,
                "dns": dns or [server_ip], "lease_hours": self.sp_lease.value()}

    def _start(self):
        if self.ctrl.is_running():
            self.notify("DHCP 服务已在运行", "info")
            return
        try:
            cfg = self._collect()
        except ValueError as e:
            self.notify(str(e), "err")
            return
        if not confirm(self, "启动 DHCP 服务",
                       f"网卡 {cfg['interface']}（{cfg['device']}）\n"
                       f"地址池 {cfg['start']} ~ {cfg['end']}\n"
                       f"网关 {cfg['router']}　DNS {', '.join(cfg['dns'])}", "启动"):
            return
        self.btn_start.setEnabled(False)
        w = Worker(self.ctrl.start, cfg)
        w.ok.connect(lambda _: self._started(cfg))
        w.err.connect(self._start_err)
        w.start()
        self._workers.append(w)

    def _started(self, cfg):
        history.record("启动 DHCP 服务", cfg["interface"], "",
                       f"{cfg['start']}~{cfg['end']} /{cfg['mask']}", "成功", "")
        self.notify("DHCP 服务已启动")
        self._poll()

    def _start_err(self, msg):
        self.btn_start.setEnabled(True)
        history.record("启动 DHCP 服务", "", "", "", "失败", str(msg)[:200])
        self.notify(f"启动失败：{msg}", "err")
        self._poll()

    def _stop(self):
        if not confirm(self, "停止 DHCP 服务", "停止后已分配地址的设备将无法续租，是否继续？",
                       "停止", danger=True):
            return
        self.btn_stop.setEnabled(False)

        def job():
            self.ctrl.stop()
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._stopped())
        w.err.connect(lambda m: self.notify(f"停止失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _stopped(self):
        history.record("停止 DHCP 服务", "", "运行中", "已停止", "成功", "")
        self.notify("DHCP 服务已停止")
        self._poll()

    # ---------------- 轮询 ----------------
    def _poll(self):
        state = self.ctrl.read_state()
        running = bool(state.get("running"))
        self.badge.set_state("运行中" if running else "未运行", "ok" if running else "muted")
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        cfg = state.get("config") or {}
        if running:
            self.lbl_summary.setText(
                f"{cfg.get('interface', '—')} · {cfg.get('device', '—')}　|　"
                f"地址池 {cfg.get('start', '—')} ~ {cfg.get('end', '—')}　|　"
                f"网关 {cfg.get('router', '—')}")
        else:
            self.lbl_summary.setText("尚未启动。配置好地址池后点击「启动服务」，"
                                     "会对系统发起一次授权（Touch ID / 密码）。")
        logs = state.get("logs") or []
        if logs:
            text = "\n".join(logs[-100:])
            if self.txt.toPlainText() != text:
                self.txt.setPlainText(text)
                self.txt.verticalScrollBar().setValue(
                    self.txt.verticalScrollBar().maximum())
        leases = state.get("leases") or {}
        self.tbl.setRowCount(0)
        for ip, info in sorted(leases.items()):
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(ip))
            self.tbl.setItem(r, 1, QTableWidgetItem(str(info.get("mac", ""))))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(info.get("expires", ""))))
        self.lbl_lease.setText(f"已分配 {len(leases)} 个地址" if leases else "尚无租约")

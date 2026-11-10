"""标签页 5：内置 DHCP 服务（参考 bmc-dhcp-tool）"""
import ipaddress

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.dhcp_controller import DhcpController
from core.netbase import normalize_mask, sort_interfaces, iface_is_external
from .common import Worker


class DhcpTab(QWidget):
    LEASE_COLS = ["分配 IP", "客户端 MAC", "到期时间"]

    def __init__(self, backend, log, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.log = log
        self.ctrl = DhcpController()
        self.ifaces = []
        self._worker = None
        self._build_ui()
        # 状态轮询定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1500)
        self._poll()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        gb = QGroupBox("服务配置")
        f = QFormLayout(gb)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.cmb_iface = QComboBox()
        self.cmb_iface.currentIndexChanged.connect(self._iface_changed)
        btn_reload = QPushButton("刷新网卡")
        btn_reload.clicked.connect(self._reload)
        hl = QHBoxLayout()
        hl.addWidget(self.cmb_iface, 1)
        hl.addWidget(btn_reload)
        f.addRow("监听网卡:", hl)
        self.ed_server_ip = QLineEdit()
        self.ed_server_ip.setPlaceholderText("本网卡当前 IP（留空自动获取）")
        f.addRow("服务器 IP:", self.ed_server_ip)
        self.ed_start = QLineEdit()
        self.ed_end = QLineEdit()
        f.addRow("地址池起始:", self.ed_start)
        f.addRow("地址池结束:", self.ed_end)
        self.ed_mask = QLineEdit("255.255.255.0")
        self.ed_mask.setPlaceholderText("255.255.255.0 或 24 均可")
        self.ed_router = QLineEdit()
        f.addRow("子网掩码:", self.ed_mask)
        f.addRow("下发网关:", self.ed_router)
        self.ed_dns = QLineEdit()
        self.ed_dns.setPlaceholderText("逗号分隔，留空则下发服务器 IP")
        f.addRow("下发 DNS:", self.ed_dns)
        sp = QDoubleSpinBox()
        sp.setRange(0.1, 72.0)
        sp.setValue(1.0)
        sp.setSuffix(" 小时")
        self.sp_lease = sp
        f.addRow("租约时长:", sp)
        v.addWidget(gb)

        h = QHBoxLayout()
        self.btn_start = QPushButton("启动 DHCP 服务")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("dangerBtn")
        self.btn_stop.setEnabled(False)
        self.lbl_status = QLabel("状态：未运行")
        h.addWidget(self.btn_start)
        h.addWidget(self.btn_stop)
        h.addWidget(self.lbl_status)
        h.addStretch(1)
        v.addLayout(h)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)

        # 租约表
        gb2 = QGroupBox("当前租约")
        v2 = QVBoxLayout(gb2)
        self.tbl_leases = QTableWidget(0, 3)
        self.tbl_leases.setHorizontalHeaderLabels(self.LEASE_COLS)
        self.tbl_leases.verticalHeader().setVisible(False)
        self.tbl_leases.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_leases.horizontalHeader().setStretchLastSection(True)
        v2.addWidget(self.tbl_leases)
        v.addWidget(gb2, 1)

        # 日志
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(160)
        self.txt_log.setPlaceholderText("启动 DHCP 服务后，这里会实时显示 IP 分配日志…")
        self.txt_log.setStyleSheet("font-family:Menlo,Consolas,monospace;font-size:11px;"
                                   "background:#fbfbfd;color:#333;")
        v.addWidget(self.txt_log)

    # ---- 配置 ----
    def set_ifaces(self, ifaces):
        self.ifaces = sort_interfaces(ifaces) or []
        cur = self.cmb_iface.currentData()
        cur_dev = cur["device"] if cur else None
        self.cmb_iface.blockSignals(True)
        self.cmb_iface.clear()
        for i in self.ifaces:
            label = f"{i['service'] or i['port']}  ({i['device']})"
            if iface_is_external(i):
                label += "  [USB]"
            self.cmb_iface.addItem(label, i)
        idx = -1
        if cur_dev:
            for k in range(self.cmb_iface.count()):
                if self.cmb_iface.itemData(k) and self.cmb_iface.itemData(k)["device"] == cur_dev:
                    idx = k
                    break
        self.cmb_iface.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_iface.blockSignals(False)
        if self.ifaces:
            self._iface_changed(self.cmb_iface.currentIndex())

    def _reload(self):
        w = Worker(self.backend.list_interfaces)
        w.ok.connect(self.set_ifaces)
        w.start()
        self._worker = w

    def _iface_changed(self, idx):
        ifc = self.cmb_iface.currentData()
        if not ifc:
            return
        ip = ifc.get("ipv4") or ""
        self.ed_server_ip.setText(ip)
        # 根据现有网段猜地址池
        if ip:
            try:
                import struct, socket as s
                net = ipaddress.ip_network(f"{ip}/24", strict=False)
                hosts = list(net.hosts())
                self.ed_start.setText(str(hosts[100]) if len(hosts) > 100 else str(hosts[0]))
                self.ed_end.setText(str(hosts[150]) if len(hosts) > 150 else str(hosts[-1]))
                self.ed_router.setText(ip)
                return
            except Exception:
                pass

    def _collect_cfg(self):
        ifc = self.cmb_iface.currentData()
        if not ifc:
            raise ValueError("请先选择监听网卡")
        server_ip = self.ed_server_ip.text().strip() or self.backend.interface_ip(
            ifc["service"] or ifc["device"]) or ifc.get("ipv4") or ""
        if not server_ip:
            raise ValueError("无法确定服务器 IP，请手动填写")
        try:
            ipaddress.IPv4Address(server_ip)
        except ValueError:
            raise ValueError(f"服务器 IP 无效: {server_ip}")
        start, end = self.ed_start.text().strip(), self.ed_end.text().strip()
        if not start or not end:
            raise ValueError("地址池起始/结束不能为空")
        try:
            if ipaddress.IPv4Address(end) < ipaddress.IPv4Address(start):
                raise ValueError("地址池结束 IP 小于起始 IP")
        except ValueError as e:
            raise ValueError(f"地址池无效: {e}")
        mask = normalize_mask(self.ed_mask.text().strip() or "255.255.255.0")
        dns = [x.strip() for x in self.ed_dns.text().split(",") if x.strip()]
        return {
            "interface": ifc["service"] or ifc["device"],
            "device": ifc["device"],
            "server_ip": server_ip,
            "start": start, "end": end,
            "mask": mask,
            "router": self.ed_router.text().strip() or server_ip,
            "dns": dns or [server_ip],
            "lease_hours": self.sp_lease.value(),
        }

    # ---- 启停 ----
    def _start(self):
        if self.ctrl.is_running():
            QMessageBox.information(self, "提示", "DHCP 服务已在运行")
            return
        try:
            cfg = self._collect_cfg()
        except ValueError as e:
            QMessageBox.warning(self, "配置有误", str(e))
            return
        self.btn_start.setEnabled(False)
        self.log(f"启动 DHCP 服务（网卡 {cfg['interface']}，池 {cfg['start']}~{cfg['end']}）...")
        w = Worker(self.ctrl.start, cfg)
        w.ok.connect(lambda _: (self.log("DHCP 服务启动成功"),
                                QMessageBox.information(self, "完成", "DHCP 服务已启动"),
                                self.btn_start.setEnabled(True), self._poll()))
        w.err.connect(lambda m: (self.log(f"启动失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "启动失败", m),
                                 self.btn_start.setEnabled(True), self._poll()))
        w.start()
        self._worker = w

    def _stop(self):
        self.btn_stop.setEnabled(False)
        w = Worker(self.ctrl.stop)
        w.ok.connect(lambda _: self._poll())
        w.err.connect(lambda m: self.log(f"停止失败: {m}", "ERROR"))
        w.start()
        self._worker = w

    # ---- 轮询 ----
    def _poll(self):
        st = self.ctrl.read_state()
        running = self.ctrl.is_running()
        self.lbl_status.setText("状态：● 运行中" if running else "状态：未运行")
        self.lbl_status.setStyleSheet(
            "color:#2e9e5b;font-weight:bold;" if running else "color:#999;")
        self.btn_stop.setEnabled(running)
        if running:
            # 服务启动后就别再让它可以重复点
            self.btn_start.setEnabled(False)
        else:
            self.btn_start.setEnabled(True)
        # 日志
        logs = st.get("logs", [])
        if logs:
            current = "\n".join(logs[-100:])
            if self.txt_log.toPlainText() != current:
                self.txt_log.setPlainText(current)
                self.txt_log.verticalScrollBar().setValue(
                    self.txt_log.verticalScrollBar().maximum())
        # 租约
        leases = st.get("leases", {})
        self.tbl_leases.setRowCount(0)
        for ip, info in sorted(leases.items()):
            r = self.tbl_leases.rowCount()
            self.tbl_leases.insertRow(r)
            self.tbl_leases.setItem(r, 0, QTableWidgetItem(ip))
            self.tbl_leases.setItem(r, 1, QTableWidgetItem(info.get("mac", "")))
            self.tbl_leases.setItem(r, 2, QTableWidgetItem(info.get("expires", "")))

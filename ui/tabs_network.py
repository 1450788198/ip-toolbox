"""标签页 1+2：网卡管理 / IP 配置（多 IP）"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import presets as preset_store
from core.netbase import normalize_mask, sort_interfaces, iface_is_external
from .common import Worker


class NetworkTab(QWidget):
    """网卡管理（后台自动轮询，插拔 USB 网卡即时可见）"""
    COLS = ["设备", "硬件端口", "MAC 地址", "IPv4 地址", "子网掩码", "网关", "状态"]

    def __init__(self, backend, log, on_ifaces_changed=None, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.log = log
        self.on_ifaces_changed = on_ifaces_changed  # 网卡变化回调（联动其他页）
        self._worker = None
        self.ifaces = []
        self._snap = []          # 上一次快照（变化检测用）
        self._auto = False       # 当前是否为自动轮询触发
        self._build_ui()
        self.refresh()
        # 自动轮询：每 4 秒后台检测一次，变化才更新
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_refresh)
        self._timer.start(4000)

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(32)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(True)
        v.addWidget(self.table, 1)

        h = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setObjectName("primaryBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        self.lbl_auto = QLabel("● 自动检测中")
        self.lbl_auto.setStyleSheet("color:#86868b;font-size:12px;")
        self.btn_on = QPushButton("启用网卡")
        self.btn_off = QPushButton("禁用网卡")
        for b in (self.btn_on, self.btn_off):
            b.setEnabled(False)
        self.table.itemSelectionChanged.connect(
            lambda: [b.setEnabled(True) for b in (self.btn_on, self.btn_off)])
        self.btn_on.clicked.connect(lambda: self._toggle(True))
        self.btn_off.clicked.connect(lambda: self._toggle(False))
        h.addWidget(self.btn_refresh)
        h.addWidget(self.lbl_auto)
        h.addStretch(1)
        h.addWidget(self.btn_on)
        h.addWidget(self.btn_off)
        v.addLayout(h)

    def _auto_refresh(self):
        self._auto = True
        self.refresh()

    def refresh(self):
        if self._worker and self._worker.isRunning():
            return
        if not self._auto:
            self.btn_refresh.setEnabled(False)
        self._worker = Worker(self.backend.list_interfaces)
        self._worker.ok.connect(self._fill)
        self._worker.err.connect(self._err)
        self._worker.start()

    @staticmethod
    def _signature(ifaces):
        return [(i.get("device"), i.get("port"), i.get("mac"),
                 i.get("ipv4"), i.get("mask"), i.get("router"), i.get("status"))
                for i in ifaces]

    def _fill(self, ifaces):
        ifaces = sort_interfaces(ifaces)
        self.btn_refresh.setEnabled(True)
        self._auto = False
        snap = self._signature(ifaces)
        if snap == self._snap:
            self.ifaces = ifaces
            return  # 无变化，跳过重绘
        changed = bool(self._snap)
        self._snap = snap
        self.ifaces = ifaces

        # 记住选中行对应的设备，重绘后恢复
        sel_device = None
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        if rows and list(rows)[0] < len(self.ifaces if not changed else self.ifaces):
            sel_row = list(rows)[0]
            if sel_row < self.table.rowCount():
                sel_device = self.table.item(sel_row, 0).text()

        self.table.setRowCount(0)
        new_row = None
        for i in ifaces:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [i["device"], i["port"], i["mac"], i["ipv4"] or "—",
                    i["mask"] or "—", i["router"] or "—",
                    {"up": "已连接", "down": "断开", "absent": "未插入",
                     "": "未知"}.get(i["status"], i["status"])]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                if c == 6 and i["status"] == "up":
                    it.setForeground(Qt.darkGreen)
                elif c == 6 and i["status"] == "down":
                    it.setForeground(Qt.gray)
                elif c == 6 and i["status"] == "absent":
                    it.setForeground(QColor("#c77700"))
                self.table.setItem(r, c, it)
            if i["device"] == sel_device:
                new_row = r

        if new_row is not None:
            self.table.selectRow(new_row)

        if changed:
            self.log(f"检测到网卡变化，共 {len(ifaces)} 个接口")
            if self.on_ifaces_changed:
                self.on_ifaces_changed(ifaces)
        else:
            self.log(f"网卡列表已刷新，共 {len(ifaces)} 个接口")
            if self.on_ifaces_changed:
                self.on_ifaces_changed(ifaces)

    def _err(self, msg):
        self.btn_refresh.setEnabled(True)
        self._auto = False
        if self._snap:  # 自动轮询失败不弹窗，只记日志
            self.log(f"自动检测失败: {msg}", "ERROR")
        else:
            self.log(f"刷新失败: {msg}", "ERROR")
            QMessageBox.warning(self, "刷新失败", msg)

    def _toggle(self, enable: bool):
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        if not rows:
            return
        ifc = self.ifaces[list(rows)[0]]
        svc = ifc.get("service") or ifc["device"]
        name = "启用" if enable else "禁用"
        if QMessageBox.question(self, "确认", f"确定要{name}网卡「{svc}」吗？") != QMessageBox.Yes:
            return
        self.log(f"{name}网卡 {svc} ...")
        w = Worker(self.backend.enable_interface, svc, enable)
        w.ok.connect(lambda _: (self.log(f"网卡 {svc} 已{name}"), self.refresh()))
        w.err.connect(lambda m: (self.log(f"{name}网卡失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "操作失败", m)))
        w.start()
        self._worker = w


class IpConfigTab(QWidget):
    """IP 配置：主 IP（静态/DHCP/DNS）+ 多 IP（别名/附加地址）"""
    ALIAS_COLS = ["附加 IP 地址", "操作"]

    def __init__(self, backend, log, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.log = log
        self.ifaces = []
        self._worker = None
        self._build_ui()
        self._reload_interfaces()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        # 选择网卡
        h0 = QHBoxLayout()
        h0.addWidget(QLabel("网卡:"))
        self.cmb_iface = QComboBox()
        self.cmb_iface.setMinimumWidth(260)
        self.cmb_iface.currentIndexChanged.connect(self._iface_changed)
        btn_reload = QPushButton("刷新")
        btn_reload.clicked.connect(self._reload_interfaces)
        h0.addWidget(self.cmb_iface)
        h0.addWidget(btn_reload)
        h0.addStretch(1)
        v.addLayout(h0)

        # 主 IP 组
        gb1 = QGroupBox("主 IP 配置（networksetup / netsh）")
        f1 = QFormLayout(gb1)
        f1.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.ed_ip = QLineEdit()
        self.ed_ip.setPlaceholderText("例: 192.168.1.100")
        self.ed_mask = QLineEdit()
        self.ed_mask.setPlaceholderText("255.255.255.0 或 24 均可")
        self.ed_gw = QLineEdit()
        self.ed_gw.setPlaceholderText("例: 192.168.1.1")
        f1.addRow("IP 地址:", self.ed_ip)
        f1.addRow("子网掩码:", self.ed_mask)
        f1.addRow("默认网关:", self.ed_gw)
        self.ed_dns = QLineEdit()
        self.ed_dns.setPlaceholderText("多个 DNS 用逗号分隔，例: 223.5.5.5,114.114.114.114")
        f1.addRow("DNS 服务器:", self.ed_dns)
        h1 = QHBoxLayout()
        self.btn_apply = QPushButton("应用静态 IP")
        self.btn_apply.clicked.connect(self._apply_static)
        self.btn_dhcp = QPushButton("切换为 DHCP 自动获取")
        self.btn_dhcp.clicked.connect(self._apply_dhcp)
        h1.addWidget(self.btn_apply)
        h1.addWidget(self.btn_dhcp)
        h1.addStretch(1)
        f1.addRow(h1)
        v.addWidget(gb1)

        # 多 IP 组
        gb2 = QGroupBox("同网卡多 IP（附加地址，不覆盖主 IP）")
        v2 = QVBoxLayout(gb2)
        self.tbl_alias = QTableWidget(0, 2)
        self.tbl_alias.setHorizontalHeaderLabels(self.ALIAS_COLS)
        self.tbl_alias.verticalHeader().setVisible(False)
        self.tbl_alias.horizontalHeader().setStretchLastSection(True)
        self.tbl_alias.verticalHeader().setDefaultSectionSize(32)
        v2.addWidget(self.tbl_alias, 1)
        h2 = QHBoxLayout()
        self.ed_alias_ip = QLineEdit()
        self.ed_alias_ip.setPlaceholderText("附加 IP，例: 10.0.0.55")
        self.ed_alias_mask = QLineEdit()
        self.ed_alias_mask.setPlaceholderText("掩码：255.255.255.0 或 24 均可")
        btn_add = QPushButton("添加附加 IP")
        btn_add.clicked.connect(self._add_alias)
        btn_del = QPushButton("删除选中 IP")
        btn_del.clicked.connect(self._del_alias)
        h2.addWidget(QLabel("IP:"))
        h2.addWidget(self.ed_alias_ip)
        h2.addWidget(QLabel("掩码:"))
        h2.addWidget(self.ed_alias_mask)
        h2.addWidget(btn_add)
        h2.addWidget(btn_del)
        v2.addLayout(h2)
        v.addWidget(gb2, 1)

        tip = QLabel("说明：macOS 附加 IP 通过 ifconfig alias 实现，重启后失效；Windows 通过 netsh 附加地址持久保存。")
        tip.setStyleSheet("color:#777;")
        v.addWidget(tip)

    # ---- 数据加载 ----
    def _reload_interfaces(self):
        self._worker = Worker(self.backend.list_interfaces)
        self._worker.ok.connect(self._ifaces_loaded)
        self._worker.err.connect(lambda m: self.log(f"加载网卡失败: {m}", "ERROR"))
        self._worker.start()

    def update_ifaces(self, ifaces):
        """网卡列表变化时由网卡管理页联动调用（保持当前选中）"""
        cur = self._current()
        cur_dev = cur["device"] if cur else None
        self.ifaces = sort_interfaces(ifaces)
        self.cmb_iface.blockSignals(True)
        self.cmb_iface.clear()
        for i in self.ifaces:
            label = f"{i['service'] or i['port']}  ({i['device']})"
            if iface_is_external(i):
                label += "  [USB]"
            self.cmb_iface.addItem(label, i)
        # 恢复之前的选中网卡
        idx = -1
        if cur_dev:
            for k in range(self.cmb_iface.count()):
                if self.cmb_iface.itemData(k) and self.cmb_iface.itemData(k)["device"] == cur_dev:
                    idx = k
                    break
        self.cmb_iface.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_iface.blockSignals(False)
        self._iface_changed(self.cmb_iface.currentIndex())

    def _ifaces_loaded(self, ifaces):
        self.update_ifaces(ifaces)

    def _current(self):
        return self.cmb_iface.currentData()

    def _iface_changed(self, idx):
        ifc = self._current()
        if not ifc:
            return
        self.ed_ip.setText(ifc.get("ipv4") or "")
        self.ed_mask.setText(ifc.get("mask") or "")
        self.ed_gw.setText(ifc.get("router") or "")
        self._load_aliases()

    def _load_aliases(self):
        ifc = self._current()
        if not ifc:
            return
        w = Worker(self.backend.list_alias_ips, ifc["device"])
        w.ok.connect(self._fill_aliases)
        w.err.connect(lambda m: self.log(
            f"{ifc['device']} 未插入，无附加 IP 可读" if "does not exist" in m
            else f"读取附加 IP 失败: {m}",
            "INFO" if "does not exist" in m else "ERROR"))
        w.start()
        self._worker = w

    def _fill_aliases(self, aliases):
        self.tbl_alias.setRowCount(0)
        for ip in aliases:
            r = self.tbl_alias.rowCount()
            self.tbl_alias.insertRow(r)
            self.tbl_alias.setItem(r, 0, QTableWidgetItem(ip))
            self.tbl_alias.setItem(r, 1, QTableWidgetItem("附加地址"))

    # ---- 操作 ----
    def _apply_static(self):
        ifc = self._current()
        if not ifc:
            return
        ip, gw = self.ed_ip.text().strip(), self.ed_gw.text().strip()
        if not ip or not self.ed_mask.text().strip():
            QMessageBox.warning(self, "缺少参数", "IP 地址和子网掩码不能为空")
            return
        try:
            mask = normalize_mask(self.ed_mask.text())
        except ValueError as e:
            QMessageBox.warning(self, "掩码有误", str(e))
            return
        svc = ifc["service"] or ifc["device"]
        if QMessageBox.question(self, "确认",
                f"将网卡「{svc}」设为静态 IP {ip}/{mask} 网关 {gw or '无'}？") != QMessageBox.Yes:
            return
        self.log(f"设置 {svc} 静态 IP {ip}/{mask} ...")
        w = Worker(self.backend.set_static_ip, svc, ip, mask, gw)
        w.ok.connect(lambda _: (self.log(f"{svc} 静态 IP 已生效"),
                                QMessageBox.information(self, "完成", "静态 IP 已应用")))
        w.err.connect(lambda m: (self.log(f"设置失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "设置失败", m)))
        w.start()
        self._worker = w

    def _apply_dhcp(self):
        ifc = self._current()
        if not ifc:
            return
        svc = ifc["service"] or ifc["device"]
        if QMessageBox.question(self, "确认", f"将网卡「{svc}」切回 DHCP 自动获取？") != QMessageBox.Yes:
            return
        self.log(f"切换 {svc} 为 DHCP ...")
        w = Worker(self.backend.set_dhcp, svc)
        w.ok.connect(lambda _: (self.log(f"{svc} 已切换为 DHCP"),
                                QMessageBox.information(self, "完成", "已切换为 DHCP")))
        w.err.connect(lambda m: (self.log(f"切换失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "切换失败", m)))
        w.start()
        self._worker = w

    def _check_device(self, ifc: dict) -> bool:
        """接口是否真实存在（USB 网卡未插入时提前拦截并提示）"""
        if ifc.get("status") == "absent" or \
                (hasattr(self.backend, "device_exists")
                 and not self.backend.device_exists(ifc["device"])):
            QMessageBox.warning(
                self, "网卡未插入",
                f"接口 {ifc['device']} 当前不存在——USB 网卡未插入或未识别。\n\n"
                "请先插上网卡，待网卡管理页显示「已连接」后再操作。")
            return False
        return True

    def _add_alias(self):
        ifc = self._current()
        if not ifc:
            return
        ip = self.ed_alias_ip.text().strip()
        try:
            mask = normalize_mask(self.ed_alias_mask.text() or "255.255.255.255")
        except ValueError as e:
            QMessageBox.warning(self, "掩码有误", str(e))
            return
        if not ip or ip.count(".") != 3:
            QMessageBox.warning(self, "格式错误", "请输入有效的附加 IP 地址")
            return
        dev = ifc["device"]
        if not self._check_device(ifc):
            return
        self.log(f"添加附加 IP {ip}/{mask} 到 {dev} ...")
        w = Worker(self.backend.add_alias_ip, dev, ip, mask)
        w.ok.connect(lambda _: (self.log(f"附加 IP {ip} 已添加"),
                                self.ed_alias_ip.clear(),
                                self._load_aliases()))
        w.err.connect(lambda m: (self.log(f"添加失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "添加失败", m)))
        w.start()
        self._worker = w

    def _del_alias(self):
        ifc = self._current()
        rows = {i.row() for i in self.tbl_alias.selectedIndexes()}
        if not ifc or not rows:
            return
        ip = self.tbl_alias.item(list(rows)[0], 0).text()
        dev = ifc["device"]
        if not self._check_device(ifc):
            return
        if QMessageBox.question(self, "确认", f"删除附加 IP {ip}？") != QMessageBox.Yes:
            return
        self.log(f"删除附加 IP {ip} ...")
        w = Worker(self.backend.remove_alias_ip, dev, ip)
        w.ok.connect(lambda _: (self.log(f"附加 IP {ip} 已删除"), self._load_aliases()))
        w.err.connect(lambda m: (self.log(f"删除失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "删除失败", m)))
        w.start()
        self._worker = w

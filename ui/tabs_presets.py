"""标签页 3：IP 方案一键切换（对标 ipchange.app）"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import presets as preset_store
from core.netbase import normalize_mask, sort_interfaces
from .common import Worker


class PresetDialog(QDialog):
    """新建/编辑方案"""

    def __init__(self, ifaces, preset=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑方案" if preset else "新建方案")
        self.ifaces = ifaces
        f = QFormLayout(self)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.ed_name = QLineEdit()
        f.addRow("方案名称:", self.ed_name)
        self.cmb_iface = QComboBox()
        for i in ifaces:
            self.cmb_iface.addItem(f"{i['service'] or i['port']}  ({i['device']})",
                                   i["service"] or i["device"])
        f.addRow("目标网卡:", self.cmb_iface)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["静态 IP", "DHCP 自动获取"])
        self.cmb_mode.currentIndexChanged.connect(self._mode_changed)
        f.addRow("获取方式:", self.cmb_mode)
        self.ed_ip = QLineEdit()
        self.ed_mask = QLineEdit("255.255.255.0")
        self.ed_mask.setPlaceholderText("255.255.255.0 或 24 均可")
        self.ed_gw = QLineEdit()
        f.addRow("IP 地址:", self.ed_ip)
        f.addRow("子网掩码:", self.ed_mask)
        f.addRow("默认网关:", self.ed_gw)
        self.ed_dns = QLineEdit()
        self.ed_dns.setPlaceholderText("逗号分隔，例: 223.5.5.5,114.114.114.114")
        f.addRow("DNS:", self.ed_dns)
        self._mode_changed(self.cmb_mode.currentIndex())
        if preset:
            self.ed_name.setText(preset.get("name", ""))
            idx = self.cmb_iface.findData(preset.get("service"))
            if idx >= 0:
                self.cmb_iface.setCurrentIndex(idx)
            self.cmb_mode.setCurrentIndex(0 if preset.get("mode") == "static" else 1)
            self.ed_ip.setText(preset.get("ip", ""))
            self.ed_mask.setText(preset.get("mask", ""))
            self.ed_gw.setText(preset.get("router", ""))
            self.ed_dns.setText(",".join(preset.get("dns", [])))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _mode_changed(self, idx):
        for w in (self.ed_ip, self.ed_mask, self.ed_gw):
            w.setEnabled(idx == 0)

    def result_preset(self) -> dict:
        dns = [x.strip() for x in self.ed_dns.text().split(",") if x.strip()]
        # 掩码统一归一化为点分十进制存库（输入支持 24 / /24 / 255.255.255.0）
        mask = normalize_mask(self.ed_mask.text()) if self.ed_mask.text().strip() else ""
        return {
            "name": self.ed_name.text().strip(),
            "service": self.cmb_iface.currentData(),
            "mode": "static" if self.cmb_mode.currentIndex() == 0 else "dhcp",
            "ip": self.ed_ip.text().strip(),
            "mask": mask,
            "router": self.ed_gw.text().strip(),
            "dns": dns,
        }


class PresetsTab(QWidget):
    """IP 方案管理 + 一键切换"""
    COLS = ["方案名称", "目标网卡", "方式", "IP 地址", "网关", "DNS"]

    def __init__(self, backend, log, on_applied, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.log = log
        self.on_applied = on_applied   # 切换成功后回调（刷新托盘菜单等）
        self.ifaces = []
        self.presets = []
        self._worker = None
        self._build_ui()
        self.reload()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        # 表格 + 空状态（QStackedWidget 切换）
        self._stack = QStackedWidget()
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self._stack.addWidget(self.table)

        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.setAlignment(Qt.AlignCenter)
        icon = QLabel()
        from .icons import svg_svg
        icon.setPixmap(svg_svg("presets", "#b8b8bd", 56))
        icon.setAlignment(Qt.AlignCenter)
        ev.addWidget(icon)
        lbl = QLabel("暂无 IP 方案")
        lbl.setStyleSheet("color:#86868b;font-size:15px;font-weight:600;")
        lbl.setAlignment(Qt.AlignCenter)
        ev.addWidget(lbl)
        sub = QLabel("创建方案保存常用 IP/DNS 组合，一键切换")
        sub.setStyleSheet("color:#aeaeb2;font-size:12px;")
        sub.setAlignment(Qt.AlignCenter)
        ev.addWidget(sub)
        self.btn_empty_new = QPushButton("新建方案")
        self.btn_empty_new.setObjectName("primaryBtn")
        ev.addWidget(self.btn_empty_new, 0, Qt.AlignCenter)
        self._stack.addWidget(empty)
        self._stack.setCurrentIndex(1)
        v.addWidget(self._stack, 1)

        h = QHBoxLayout()
        self.btn_new = QPushButton("新建方案")
        self.btn_edit = QPushButton("编辑")
        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("dangerBtn")
        self.btn_apply = QPushButton("应用选中方案")
        self.btn_apply.setObjectName("primaryBtn")
        self.btn_refresh = QPushButton("刷新")
        for b in (self.btn_new, self.btn_edit, self.btn_del, self.btn_apply, self.btn_refresh):
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)

        self.btn_new.clicked.connect(self._new)
        self.btn_empty_new.clicked.connect(self._new)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_refresh.clicked.connect(self.reload)

    def reload(self):
        self.presets = preset_store.load_presets()
        self._worker = Worker(self.backend.list_interfaces)
        self._worker.ok.connect(self._fill)
        self._worker.err.connect(lambda m: self._fill([]))
        self._worker.start()

    def _fill(self, ifaces):
        if ifaces:
            self.ifaces = sort_interfaces(ifaces)
        self.table.setRowCount(0)
        for p in self.presets:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [p.get("name", ""), p.get("service", ""),
                    "静态 IP" if p.get("mode") == "static" else "DHCP",
                    p.get("ip") or "—", p.get("router") or "—",
                    ", ".join(p.get("dns", [])) or "—"]
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))
        self._stack.setCurrentIndex(1 if not self.presets else 0)
        self.log(f"方案列表已刷新，共 {len(self.presets)} 个方案")

    def _selected(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            return None
        return list(rows)[0]

    def _new(self):
        if not self.ifaces:
            QMessageBox.warning(self, "提示", "尚未获取到网卡列表，请稍候重试")
            return
        dlg = PresetDialog(self.ifaces, parent=self)
        if dlg.exec() == QDialog.Accepted:
            p = dlg.result_preset()
            err = preset_store.validate_preset(p)
            if err:
                QMessageBox.warning(self, "校验失败", err)
                return
            self.presets.append(p)
            preset_store.save_presets(self.presets)
            self.log(f"方案「{p['name']}」已保存")
            self._fill(self.ifaces)

    def _edit(self):
        idx = self._selected()
        if idx is None:
            QMessageBox.information(self, "提示", "请先选中一个方案")
            return
        dlg = PresetDialog(self.ifaces, self.presets[idx], parent=self)
        if dlg.exec() == QDialog.Accepted:
            p = dlg.result_preset()
            err = preset_store.validate_preset(p)
            if err:
                QMessageBox.warning(self, "校验失败", err)
                return
            self.presets[idx] = p
            preset_store.save_presets(self.presets)
            self._fill(self.ifaces)

    def _delete(self):
        idx = self._selected()
        if idx is None:
            return
        p = self.presets[idx]
        if QMessageBox.question(self, "确认", f"删除方案「{p['name']}」？") != QMessageBox.Yes:
            return
        del self.presets[idx]
        preset_store.save_presets(self.presets)
        self._fill(self.ifaces)

    def _apply(self):
        idx = self._selected()
        if idx is None:
            QMessageBox.information(self, "提示", "请先选中一个方案")
            return
        p = self.presets[idx]
        svc = p["service"]
        desc = (f"{p['ip']}/{p.get('mask')}" if p["mode"] == "static" else "DHCP")
        if QMessageBox.question(self, "确认切换",
                f"将网卡「{svc}」切换到方案「{p['name']}」（{desc}）？\n"
                "切换可能短暂断开该网卡的网络连接。") != QMessageBox.Yes:
            return
        self.log(f"应用方案「{p['name']}」到 {svc} ...")
        self.btn_apply.setEnabled(False)

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
                                QMessageBox.information(self, "完成",
                                    f"方案「{p['name']}」已应用到「{svc}」"),
                                self.btn_apply.setEnabled(True),
                                self.on_applied()))
        w.err.connect(lambda m: (self.log(f"切换失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "切换失败", m),
                                 self.btn_apply.setEnabled(True)))
        w.start()
        self._worker = w

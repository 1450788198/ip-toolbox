"""统一对话框：变更预览、通用确认、附加 IP、批量添加、路由、方案"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.netbase import normalize_mask
from .components.segmented import Segmented


class DialogBase(QDialog):
    def __init__(self, parent, title: str, subtitle: str = "", width: int = 460):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("cardTitle")
        head.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("cardSub")
            s.setWordWrap(True)
            head.addWidget(s)
        root.addLayout(head)

        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        root.addWidget(line)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body, 1)

        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.footer.addStretch(1)
        root.addLayout(self.footer)

    def add_cancel(self, text: str = "取消"):
        btn = QPushButton(text)
        btn.clicked.connect(self.reject)
        self.footer.addWidget(btn)
        return btn

    def add_ok(self, text: str = "确定", danger: bool = False):
        btn = QPushButton(text)
        btn.setProperty("variant", "danger" if danger else "primary")
        btn.setDefault(True)
        btn.clicked.connect(self.accept)
        self.footer.addWidget(btn)
        return btn


def confirm(parent, title: str, message: str, ok_text: str = "确定",
            danger: bool = False) -> bool:
    dlg = DialogBase(parent, title, message, width=420)
    dlg.add_cancel()
    dlg.add_ok(ok_text, danger)
    return dlg.exec() == QDialog.Accepted


class ChangePreview(DialogBase):
    """应用前的变更预览：变更前 → 变更后"""

    def __init__(self, parent, service: str, changes: list, note: str = ""):
        super().__init__(parent, "确认变更",
                         f"即将修改「{service}」的配置，请核对以下变更：", width=520)
        table = QTableWidget(len(changes), 3)
        table.setHorizontalHeaderLabels(["项目", "变更前", "变更后"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.verticalHeader().setDefaultSectionSize(30)
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        for r, (label, before, after) in enumerate(changes):
            changed = (before or "—") != (after or "—")
            for c, val in enumerate((label, before or "—", after or "—")):
                it = QTableWidgetItem(str(val))
                if c == 0:
                    it.setForeground(Qt.gray)
                if c == 2 and changed:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                table.setItem(r, c, it)
        table.setMinimumHeight(min(240, 34 * len(changes) + 34))
        self.body.addWidget(table)
        if note:
            tip = QLabel(note)
            tip.setObjectName("hint")
            tip.setWordWrap(True)
            self.body.addWidget(tip)
        self.add_cancel("取消")
        self.add_ok("应用变更")


class AliasDialog(DialogBase):
    """添加单个附加 IP"""

    def __init__(self, parent, device: str, count_hint: str = ""):
        super().__init__(parent, "添加附加 IP",
                         f"在接口 {device} 上追加地址，不覆盖主 IP。{count_hint}", 420)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.addWidget(QLabel("IP 地址"), 0, 0)
        self.ed_ip = QLineEdit()
        self.ed_ip.setPlaceholderText("例: 10.0.0.55")
        grid.addWidget(self.ed_ip, 0, 1)
        grid.addWidget(QLabel("子网掩码"), 1, 0)
        self.ed_mask = QLineEdit("255.255.255.255")
        self.ed_mask.setPlaceholderText("255.255.255.0 或 24 均可")
        grid.addWidget(self.ed_mask, 1, 1)
        self.body.addLayout(grid)
        self.err = QLabel("")
        self.err.setProperty("state", "err")
        self.err.setWordWrap(True)
        self.body.addWidget(self.err)
        self.add_cancel()
        self.add_ok("添加")
        self.ed_ip.setFocus()

    def values(self):
        ip = self.ed_ip.text().strip()
        try:
            mask = normalize_mask(self.ed_mask.text() or "255.255.255.255")
        except ValueError as e:
            raise ValueError(f"掩码有误：{e}")
        parts = ip.split(".")
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            raise ValueError("请输入有效的 IPv4 地址")
        return ip, mask


class BulkAliasDialog(DialogBase):
    """批量添加附加 IP：每行一个，可写 IP 或 IP/掩码"""

    def __init__(self, parent, device: str):
        super().__init__(parent, "批量添加附加 IP",
                         f"接口 {device}：每行一条，支持 10.0.0.5 或 10.0.0.5/24", 480)
        from PySide6.QtWidgets import QPlainTextEdit
        self.ed = QPlainTextEdit()
        self.ed.setPlaceholderText("10.0.0.5/24\n10.0.0.6/24\n10.0.0.7 255.255.255.0")
        self.ed.setMinimumHeight(160)
        self.body.addWidget(self.ed)
        self.err = QLabel("")
        self.err.setProperty("state", "err")
        self.err.setWordWrap(True)
        self.body.addWidget(self.err)
        self.add_cancel()
        self.add_ok("添加全部")

    def values(self):
        rows = []
        for line in self.ed.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            if "/" in line:
                ip, _, mask = line.partition("/")
                try:
                    mask = normalize_mask(mask)
                except ValueError:
                    raise ValueError(f"掩码无效：{line}")
            elif len(line.split()) == 2:
                ip, mask = line.split()
                try:
                    mask = normalize_mask(mask)
                except ValueError:
                    raise ValueError(f"掩码无效：{line}")
            else:
                ip, mask = line, "255.255.255.255"
            parts = ip.split(".")
            if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                raise ValueError(f"IP 无效：{ip}")
            rows.append((ip, mask))
        if not rows:
            raise ValueError("请至少填写一条附加 IP")
        return rows


class PresetDialog(DialogBase):
    """保存 / 编辑 IP 方案"""

    def __init__(self, parent, services: list, data: dict = None):
        data = data or {}
        super().__init__(parent, "保存为方案", "保存常用 IP / DNS 组合，之后可一键切换", 480)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.addWidget(QLabel("方案名称"), 0, 0)
        self.ed_name = QLineEdit(data.get("name", ""))
        self.ed_name.setPlaceholderText("例: 客户现场 A 段")
        grid.addWidget(self.ed_name, 0, 1)
        grid.addWidget(QLabel("目标网卡"), 1, 0)
        self.cmb_service = QComboBox()
        for label, value in services:
            self.cmb_service.addItem(label, value)
        if data.get("service"):
            idx = self.cmb_service.findData(data["service"])
            if idx >= 0:
                self.cmb_service.setCurrentIndex(idx)
        grid.addWidget(self.cmb_service, 1, 1)
        grid.addWidget(QLabel("配置方式"), 2, 0)
        self.seg = Segmented(["手动", "DHCP"])
        self.seg.set_index(0 if data.get("mode", "static") == "static" else 1)
        grid.addWidget(self.seg, 2, 1)
        grid.addWidget(QLabel("IP 地址"), 3, 0)
        self.ed_ip = QLineEdit(data.get("ip", ""))
        grid.addWidget(self.ed_ip, 3, 1)
        grid.addWidget(QLabel("子网掩码"), 4, 0)
        self.ed_mask = QLineEdit(data.get("mask", "255.255.255.0"))
        self.ed_mask.setPlaceholderText("255.255.255.0 或 24 均可")
        grid.addWidget(self.ed_mask, 4, 1)
        grid.addWidget(QLabel("默认网关"), 5, 0)
        self.ed_gw = QLineEdit(data.get("router", ""))
        grid.addWidget(self.ed_gw, 5, 1)
        grid.addWidget(QLabel("DNS"), 6, 0)
        self.ed_dns = QLineEdit(", ".join(data.get("dns", []) or []))
        self.ed_dns.setPlaceholderText("多个用逗号分隔，留空表示不改动")
        grid.addWidget(self.ed_dns, 6, 1)
        self.body.addLayout(grid)
        self.err = QLabel("")
        self.err.setProperty("state", "err")
        self.body.addWidget(self.err)
        self.add_cancel()
        self.add_ok("保存")

    def result_preset(self) -> dict:
        name = self.ed_name.text().strip()
        if not name:
            raise ValueError("请填写方案名称")
        mode = "static" if self.seg.index() == 0 else "dhcp"
        ip = self.ed_ip.text().strip()
        mask = self.ed_mask.text().strip()
        gw = self.ed_gw.text().strip()
        if mode == "static":
            if not ip:
                raise ValueError("手动方式需要填写 IP")
            parts = ip.split(".")
            if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                raise ValueError("IP 格式无效")
            try:
                mask = normalize_mask(mask)
            except ValueError as e:
                raise ValueError(f"掩码有误：{e}")
        dns = [x.strip() for x in self.ed_dns.text().replace("，", ",").split(",") if x.strip()]
        return {"name": name, "service": self.cmb_service.currentData(),
                "mode": mode, "ip": ip, "mask": mask or "255.255.255.0",
                "router": gw, "dns": dns}


class RouteDialog(DialogBase):
    """添加静态路由"""

    def __init__(self, parent, ifaces: list):
        super().__init__(parent, "添加静态路由",
                         "目标可写 10.20.0.0/16 或 10.20.1.5（单主机）", 480)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.addWidget(QLabel("目标网络"), 0, 0)
        self.ed_dest = QLineEdit()
        self.ed_dest.setPlaceholderText("10.20.0.0/16")
        grid.addWidget(self.ed_dest, 0, 1)
        grid.addWidget(QLabel("子网掩码"), 1, 0)
        self.ed_mask = QLineEdit()
        self.ed_mask.setPlaceholderText("可选，255.255.0.0 或 16；目标已带 /前缀 时可留空")
        grid.addWidget(self.ed_mask, 1, 1)
        grid.addWidget(QLabel("下一跳"), 2, 0)
        self.ed_gw = QLineEdit()
        self.ed_gw.setPlaceholderText("192.168.1.254")
        grid.addWidget(self.ed_gw, 2, 1)
        grid.addWidget(QLabel("出接口"), 3, 0)
        self.cmb_iface = QComboBox()
        self.cmb_iface.addItem("自动（由系统选择）", "")
        for i in ifaces or []:
            label = f"{i.get('service') or i.get('port')} ({i.get('device')})"
            self.cmb_iface.addItem(label, i.get("device"))
        grid.addWidget(self.cmb_iface, 3, 1)
        self.chk_persist = QCheckBox("持久路由（Windows 写入系统配置；macOS 重启后失效）")
        from core.netbase import IS_WIN
        self.chk_persist.setEnabled(IS_WIN)
        grid.addWidget(self.chk_persist, 4, 0, 1, 2)
        self.body.addLayout(grid)
        self.err = QLabel("")
        self.err.setProperty("state", "err")
        self.err.setWordWrap(True)
        self.body.addWidget(self.err)
        self.add_cancel()
        self.add_ok("添加路由")

    def values(self):
        dest = self.ed_dest.text().strip()
        gw = self.ed_gw.text().strip()
        if not dest:
            raise ValueError("请填写目标网络")
        if not gw:
            raise ValueError("请填写下一跳网关")
        mask = ""
        if self.ed_mask.text().strip():
            try:
                mask = normalize_mask(self.ed_mask.text())
            except ValueError as e:
                raise ValueError(f"掩码有误：{e}")
        return dest, gw, mask, self.cmb_iface.currentData(), self.chk_persist.isChecked()

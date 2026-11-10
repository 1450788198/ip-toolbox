"""标签页 6：子网计算器（纯本地计算，无需权限）

功能：
1. 子网信息计算：IP + 掩码 → 网络/广播/可用范围/主机数/通配符/类型/二进制视图
2. 子网划分器（VLSM）：按子网数量或每子网可用主机数切分网段
3. 掩码速查表：/8~/32 对照，双击行直接填入
"""
import ipaddress
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.netbase import normalize_mask
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFormLayout,
                               QGridLayout, QGroupBox, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton,
                               QSpinBox, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

# 常用前缀快捷选择
COMMON_PREFIX = [8, 16, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]


def _fmt_bin(ip_obj) -> str:
    """IP/掩码转点分二进制（8 位一组）"""
    return ".".join(f"{int(o):08b}" for o in str(ip_obj).split("."))


def _mono(item: QTableWidgetItem):
    f = item.font()
    f.setFamily("Menlo")
    item.setFont(f)
    return item


class SubnetTab(QWidget):
    SPLIT_COLS = ["#", "网络地址", "掩码", "可用主机范围", "广播地址", "可用主机数"]
    MASK_COLS = ["前缀", "子网掩码", "通配符掩码", "可用主机数"]

    def __init__(self, log, parent=None):
        super().__init__(parent)
        self.log = log
        self._build_ui()
        self._recalc()

    # ================= UI =================
    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        # ---- 1. 子网信息 ----
        gb_in = QGroupBox("子网信息（输入即时计算）")
        g = QGridLayout(gb_in)
        g.setHorizontalSpacing(10)

        g.addWidget(QLabel("IP 地址:"), 0, 0)
        self.ed_ip = QLineEdit("192.168.1.66")
        self.ed_ip.setPlaceholderText("例如 192.168.1.66")
        self.ed_ip.textChanged.connect(self._recalc)
        g.addWidget(self.ed_ip, 0, 1)

        g.addWidget(QLabel("掩码 / 前缀:"), 0, 2)
        self.ed_mask = QLineEdit("255.255.255.0")
        self.ed_mask.setPlaceholderText("点分掩码或 /24 均可")
        self.ed_mask.textChanged.connect(self._recalc)
        g.addWidget(self.ed_mask, 0, 3)

        g.addWidget(QLabel("常用前缀:"), 0, 4)
        self.cmb_prefix = QComboBox()
        self.cmb_prefix.addItem("—")
        for p in COMMON_PREFIX:
            self.cmb_prefix.addItem(f"/{p}")
        self.cmb_prefix.currentIndexChanged.connect(self._prefix_picked)
        g.addWidget(self.cmb_prefix, 0, 5)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 2)

        f = QFormLayout()
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        def ro_field():
            e = QLineEdit()
            e.setReadOnly(True)
            return e

        self.f_mask = ro_field()
        self.f_wild = ro_field()
        self.f_net = ro_field()
        self.f_bcast = ro_field()
        self.f_range = ro_field()
        self.f_hosts = ro_field()
        self.f_type = ro_field()
        self.f_note = ro_field()
        f.addRow("子网掩码:", self.f_mask)
        f.addRow("通配符掩码:", self.f_wild)
        f.addRow("网络地址:", self.f_net)
        f.addRow("广播地址:", self.f_bcast)
        f.addRow("可用主机范围:", self.f_range)
        f.addRow("可用主机数:", self.f_hosts)
        f.addRow("地址类型:", self.f_type)
        f.addRow("备注:", self.f_note)
        g.addLayout(f, 1, 0, 1, 6)

        self.txt_bin = QPlainTextEdit()
        self.txt_bin.setReadOnly(True)
        self.txt_bin.setMaximumHeight(96)
        mono = QFont("Menlo")
        mono.setPixelSize(12)
        self.txt_bin.setFont(mono)
        self.txt_bin.setStyleSheet(
            "background:#fbfbfd;color:#333;border:1px solid #dcdce0;border-radius:6px;")
        self.txt_bin.setPlaceholderText("输入合法的 IP 与掩码后显示二进制对齐视图…")
        g.addWidget(self.txt_bin, 2, 0, 1, 6)
        v.addWidget(gb_in)

        # ---- 2. 扩展工具（子网划分 / 掩码速查）----
        self.tabs_ext = QTabWidget()
        self.tabs_ext.addTab(self._build_split_panel(), "子网划分 (VLSM)")
        self.tabs_ext.addTab(self._build_mask_panel(), "掩码速查表")
        v.addWidget(self.tabs_ext, 1)

    def _build_split_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)

        g = QGridLayout()
        g.addWidget(QLabel("要划分的网段:"), 0, 0)
        self.ed_split_net = QLineEdit("192.168.1.0/24")
        self.ed_split_net.setPlaceholderText("如 192.168.1.0/24")
        g.addWidget(self.ed_split_net, 0, 1)
        g.setColumnStretch(1, 1)

        g.addWidget(QLabel("划分方式:"), 0, 2)
        self.cmb_split_mode = QComboBox()
        self.cmb_split_mode.addItem("按子网数量", "count")
        self.cmb_split_mode.addItem("按每子网可用主机数", "hosts")
        g.addWidget(self.cmb_split_mode, 0, 3)

        g.addWidget(QLabel("数量:"), 0, 4)
        self.sp_split = QSpinBox()
        self.sp_split.setRange(1, 65536)
        self.sp_split.setValue(4)
        g.addWidget(self.sp_split, 0, 5)

        btn = QPushButton("划分子网")
        btn.setObjectName("primaryBtn")
        btn.clicked.connect(self._do_split)
        g.addWidget(btn, 0, 6)
        v.addLayout(g)

        self.lbl_split = QLabel("输入网段与需求后点击「划分子网」")
        self.lbl_split.setStyleSheet("color:#86868b;")
        v.addWidget(self.lbl_split)

        self.tbl_split = QTableWidget(0, len(self.SPLIT_COLS))
        self.tbl_split.setHorizontalHeaderLabels(self.SPLIT_COLS)
        self.tbl_split.verticalHeader().setVisible(False)
        self.tbl_split.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_split.setSelectionBehavior(QAbstractItemView.SelectRows)
        hdr = self.tbl_split.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self.tbl_split.setColumnWidth(0, 50)
        self.tbl_split.setColumnWidth(1, 140)
        self.tbl_split.setColumnWidth(2, 130)
        self.tbl_split.setColumnWidth(3, 240)
        v.addWidget(self.tbl_split, 1)
        return w

    def _build_mask_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        tip = QLabel("双击任意行即可把该掩码填到上方「子网信息」的掩码输入框")
        tip.setStyleSheet("color:#86868b;")
        v.addWidget(tip)

        self.tbl_mask = QTableWidget(0, len(self.MASK_COLS))
        self.tbl_mask.setHorizontalHeaderLabels(self.MASK_COLS)
        self.tbl_mask.verticalHeader().setVisible(False)
        self.tbl_mask.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_mask.setSelectionBehavior(QAbstractItemView.SelectRows)
        hdr = self.tbl_mask.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self.tbl_mask.setColumnWidth(0, 70)
        self.tbl_mask.setColumnWidth(1, 150)
        self.tbl_mask.setColumnWidth(2, 150)
        self.tbl_mask.cellDoubleClicked.connect(self._mask_picked)

        self.tbl_mask.setRowCount(25)
        for i, prefix in enumerate(range(8, 33)):
            net = ipaddress.IPv4Network(f"0.0.0.0/{prefix}")
            if prefix == 32:
                hosts = "1（主机路由）"
            elif prefix == 31:
                hosts = "2（点对点）"
            else:
                hosts = str(net.num_addresses - 2)
            vals = (f"/{prefix}", str(net.netmask), str(net.hostmask), hosts)
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if c:
                    _mono(it)
                if c == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tbl_mask.setItem(i, c, it)
        v.addWidget(self.tbl_mask)
        return w

    # ================= 交互 =================
    def _prefix_picked(self, idx):
        if idx <= 0:
            return
        prefix = self.cmb_prefix.itemText(idx).lstrip("/")
        mask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
        self.ed_mask.setText(mask)
        self.cmb_prefix.setCurrentIndex(0)  # 允许再次选择同项

    def _mask_picked(self, row, _col):
        self.ed_mask.setText(self.tbl_mask.item(row, 1).text())
        self.tabs_ext.setCurrentIndex(0)

    # ---- 子网信息 ----
    def _recalc(self):
        ip_s = self.ed_ip.text().strip()
        mask_s = self.ed_mask.text().strip()
        empty = "—"
        try:
            ip = ipaddress.IPv4Address(ip_s)
            mask = normalize_mask(mask_s)
            net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
        except ValueError:
            for f_ in (self.f_mask, self.f_wild, self.f_net, self.f_bcast,
                       self.f_range, self.f_hosts, self.f_type, self.f_note):
                f_.setText(empty)
            self.f_note.setText("输入格式不正确，请检查 IP 与掩码")
            self.f_note.setStyleSheet("color:#c04343;")
            self.txt_bin.setPlainText("")
            return

        self.f_note.setStyleSheet("")
        prefix = net.prefixlen
        total = net.num_addresses

        if prefix == 32:
            usable, rng = 1, str(net.network_address)
        elif prefix == 31:
            usable = 2
            rng = f"{net.network_address} ~ {net.broadcast_address}"
        else:
            usable = total - 2
            first = net.network_address + 1
            last = net.broadcast_address - 1
            rng = (f"{first} ~ {last}" if usable > 0 else "无（该网段只有网络/广播地址）")

        if ip.is_loopback:
            atype = "回环地址（127.0.0.0/8）"
        elif ip.is_link_local:
            atype = "链路本地（169.254.0.0/16）"
        elif ip.is_private:
            atype = f"私网地址（RFC1918，{self._priv_scope(net)}）"
        else:
            atype = "公网地址"

        notes = []
        if prefix <= 30 and ip == net.network_address:
            notes.append("该 IP 是网络地址，不能分配给主机")
        if prefix <= 30 and ip == net.broadcast_address:
            notes.append("该 IP 是广播地址，不能分配给主机")

        self.f_mask.setText(f"{net.netmask}  (/{prefix})")
        self.f_wild.setText(str(net.hostmask))
        self.f_net.setText(str(net.network_address))
        self.f_bcast.setText(str(net.broadcast_address))
        self.f_range.setText(rng)
        self.f_hosts.setText(f"{usable}  （网段共 {total} 个地址）")
        self.f_type.setText(atype)
        self.f_note.setText("；".join(notes) if notes else "—")

        self.txt_bin.setPlainText(
            f"IP  地址  {_fmt_bin(ip)}   ({ip})\n"
            f"子网掩码  {_fmt_bin(net.netmask)}   ({net.netmask})\n"
            f"网络地址  {_fmt_bin(net.network_address)}   ({net.network_address})")

    @staticmethod
    def _priv_scope(net) -> str:
        n = str(net.network_address)
        if n.startswith("10."):
            return "10.0.0.0/8"
        if n.startswith("172."):
            return "172.16.0.0/12"
        if n.startswith("192.168."):
            return "192.168.0.0/16"
        return "保留段"

    # ---- 子网划分 ----
    def _do_split(self):
        net_s = self.ed_split_net.text().strip()
        mode = self.cmb_split_mode.currentData()
        count = self.sp_split.value()
        try:
            # 掩码部分同样支持 /24、24、255.255.255.0 三种写法
            parts = net_s.split("/", 1)
            if len(parts) == 2:
                net_s = f"{parts[0].strip()}/{normalize_mask(parts[1])}"
            net = ipaddress.IPv4Network(net_s, strict=False)
        except ValueError:
            self.lbl_split.setText("网段格式不正确，应为如 192.168.1.0/24（掩码支持 24 或 255.255.255.0 写法）")
            self.lbl_split.setStyleSheet("color:#c04343;")
            return

        if mode == "count":
            # 按子网数量：需要 ceil(log2(count)) 个新位
            bits = max(0, math.ceil(math.log2(count)))
        else:
            # 按每子网可用主机数：每子网需容纳 count+2 个地址
            host_bits = math.ceil(math.log2(count + 2))
            bits = (32 - net.prefixlen) - host_bits
            if bits < 0:
                self.lbl_split.setText(
                    f"无法划分：{net} 只有 {2 ** (32 - net.prefixlen)} 个地址，"
                    f"不够每个子网 {count} 台可用主机")
                self.lbl_split.setStyleSheet("color:#c04343;")
                return

        new_prefix = net.prefixlen + bits
        if new_prefix > 32:
            self.lbl_split.setText("前缀超出 /32，无法继续划分")
            self.lbl_split.setStyleSheet("color:#c04343;")
            return

        n_subnets = 2 ** bits
        shown = list(net.subnets(prefixlen_diff=bits))
        limit = 1024
        truncated = len(shown) > limit
        if truncated:
            shown = shown[:limit]

        self.tbl_split.setRowCount(len(shown))
        for r, sub in enumerate(shown):
            if sub.prefixlen <= 30:
                rng = f"{sub.network_address + 1} ~ {sub.broadcast_address - 1}"
                hosts = sub.num_addresses - 2
            elif sub.prefixlen == 31:
                rng = f"{sub.network_address} ~ {sub.broadcast_address}"
                hosts = 2
            else:
                rng = str(sub.network_address)
                hosts = 1
            vals = [str(r + 1), str(sub.network_address), str(sub.netmask), rng,
                    str(sub.broadcast_address), str(hosts)]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if c != 0:
                    _mono(it)
                if c == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tbl_split.setItem(r, c, it)

        note = f"{net}  →  /{new_prefix}，共 {n_subnets} 个子网"
        if mode == "count" and n_subnets != count:
            note += f"（需求 {count} 个，按最接近的 2^{bits}={n_subnets} 划分）"
        if truncated:
            note += f"，表格仅显示前 {limit} 行"
        self.lbl_split.setText(note)
        self.lbl_split.setStyleSheet("color:#86868b;")

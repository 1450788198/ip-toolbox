"""子网计算器 + 掩码速查表"""
import ipaddress

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.netbase import normalize_mask
from core import subnet_utils
from ..components import Card, StatTile
from .base import ScrollPage, Page

COMMON_PREFIX = [8, 16, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]


class SubnetPage(ScrollPage):
    def __init__(self, notify, parent=None):
        super().__init__("子网计算器", "输入 IP 与掩码即时计算，掩码支持 24 / /24 / 255.255.255.0")
        self.notify = notify
        self._build()
        self._recalc()

    def _build(self):
        btn_copy = QPushButton("复制结果")
        btn_copy.clicked.connect(self._copy)
        self.add_action(btn_copy)

        card_in = Card("输入", "任意修改立即计算")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)
        grid.addWidget(self._lab("IP 地址"), 0, 0)
        self.ed_ip = QLineEdit("192.168.1.66")
        self.ed_ip.setPlaceholderText("192.168.1.66")
        self.ed_ip.textChanged.connect(self._recalc)
        grid.addWidget(self.ed_ip, 0, 1, 1, 3)
        grid.addWidget(self._lab("掩码 / 前缀"), 1, 0)
        self.ed_mask = QLineEdit("255.255.255.0")
        self.ed_mask.setPlaceholderText("255.255.255.0 / 24 / /24")
        self.ed_mask.textChanged.connect(self._recalc)
        grid.addWidget(self.ed_mask, 1, 1)
        self.cmb_prefix = QComboBox()
        self.cmb_prefix.addItem("常用前缀")
        for p in COMMON_PREFIX:
            self.cmb_prefix.addItem(f"/{p}")
        self.cmb_prefix.currentIndexChanged.connect(self._prefix_picked)
        grid.addWidget(self.cmb_prefix, 1, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        card_in.add_layout(grid)
        self.body.addWidget(card_in)

        card_out = Card("计算结果", "网络地址 / 广播地址 / 可用范围 / 主机数量")
        tiles = QGridLayout()
        tiles.setHorizontalSpacing(10)
        tiles.setVerticalSpacing(10)
        self.tiles = {}
        for i, (key, label) in enumerate([
                ("network", "网络地址"), ("broadcast", "广播地址"),
                ("range", "可用主机范围"), ("hosts", "可用主机数"),
                ("wildcard", "通配符掩码"), ("mask", "子网掩码"),
                ("cidr", "CIDR"), ("type", "地址类型")]):
            t = StatTile(label)
            tiles.addWidget(t, i // 4, i % 4)
            self.tiles[key] = t
        card_out.add_layout(tiles)
        self.lbl_note = QLabel("")
        self.lbl_note.setObjectName("hint")
        self.lbl_note.setWordWrap(True)
        card_out.add(self.lbl_note)
        self.body.addWidget(card_out)

        card_bin = Card("二进制对齐", "网络位与主机位一眼看清")
        self.txt_bin = QPlainTextEdit()
        self.txt_bin.setReadOnly(True)
        self.txt_bin.setMinimumHeight(96)
        self.txt_bin.setMaximumHeight(120)
        card_bin.add(self.txt_bin)
        self.body.addWidget(card_bin)

    @staticmethod
    def _lab(text):
        lb = QLabel(text)
        lb.setObjectName("muted")
        lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lb

    def _prefix_picked(self, idx):
        if idx > 0:
            self.ed_mask.setText(f"/{COMMON_PREFIX[idx - 1]}")

    def _recalc(self):
        try:
            data = subnet_utils.calc(self.ed_ip.text(), self.ed_mask.text(), normalize_mask)
        except ValueError as e:
            for t in self.tiles.values():
                t.set_value("—")
            self.lbl_note.setText(str(e))
            self.lbl_note.setProperty("state", "err")
            self.lbl_note.style().unpolish(self.lbl_note)
            self.lbl_note.style().polish(self.lbl_note)
            self.txt_bin.setPlainText("")
            return
        self.lbl_note.setProperty("state", "warn" if data["note"] else "")
        self.lbl_note.style().unpolish(self.lbl_note)
        self.lbl_note.style().polish(self.lbl_note)
        for key, t in self.tiles.items():
            t.set_value(data[key])
        self.lbl_note.setText(data["note"] or
                              f"CIDR 写法：{data['cidr']}　·　掩码 /{data['prefix']}")
        self.txt_bin.setPlainText(
            f"IP      {data['bin_ip']}\n"
            f"掩码    {data['bin_mask']}\n"
            f"网络    {data['bin_net']}")
        self._last = data

    def _copy(self):
        data = getattr(self, "_last", None)
        if not data:
            self.notify("没有可复制的结果", "info")
            return
        text = (f"IP: {self.ed_ip.text()}\n掩码: {data['mask']} (/{data['prefix']})\n"
                f"网络地址: {data['network']}\n广播地址: {data['broadcast']}\n"
                f"可用范围: {data['range']}\n可用主机: {data['hosts']}\n"
                f"通配符: {data['wildcard']}\n类型: {data['type']}")
        QGuiApplication.clipboard().setText(text)
        self.notify("计算结果已复制")


class MaskPage(ScrollPage):
    """掩码速查表：/8 ~ /32 全表，双击复制"""

    def __init__(self, notify, parent=None):
        super().__init__("掩码速查", "常用前缀的掩码、通配符与可用主机数，双击行复制")
        self.notify = notify
        card = Card("前缀对照表", "共 25 个前缀（/8 ~ /32）")
        self.table = QTableWidget(25, 4)
        self.table.setHorizontalHeaderLabels(["前缀", "子网掩码", "通配符掩码", "可用主机数"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(30)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._copy_row)
        for r, prefix in enumerate(range(8, 33)):
            net = ipaddress.IPv4Network(f"0.0.0.0/{prefix}")
            mask = str(net.netmask)
            wild = str(ipaddress.IPv4Address(int(net.hostmask)))
            hosts = ("1（主机路由）" if prefix == 32 else
                     "2（点对点）" if prefix == 31 else str(net.num_addresses - 2))
            for c, v in enumerate((f"/{prefix}", mask, wild, hosts)):
                it = QTableWidgetItem(v)
                if c in (0, 1, 2):
                    f = it.font()
                    f.setFamily("Menlo")
                    it.setFont(f)
                self.table.setItem(r, c, it)
        self.table.setMinimumHeight(520)
        card.add(self.table)
        tip = QLabel("提示：所有输入框都支持 24、/24、255.255.255.0 三种写法；双击行可复制掩码。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        card.add(tip)
        self.body.addWidget(card)

    def _copy_row(self, row, _col):
        mask = self.table.item(row, 1).text()
        prefix = self.table.item(row, 0).text()
        QGuiApplication.clipboard().setText(mask)
        self.notify(f"已复制 {prefix} 掩码 {mask}")

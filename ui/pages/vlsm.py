"""VLSM 子网划分器：按子网数量或每子网主机数切分"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem)

from core.netbase import normalize_mask
from core import subnet_utils
from ..components import Card
from .base import ScrollPage


class VlsmPage(ScrollPage):
    def __init__(self, notify, parent=None):
        super().__init__("VLSM 划分", "按子网数量或每子网可用主机数自动划分网段")
        self.notify = notify
        self.rows = []
        self._build()
        self._do_split()

    def _build(self):
        btn_copy = QPushButton("复制结果")
        btn_copy.clicked.connect(self._copy)
        self.add_action(btn_copy)

        card = Card("划分设置", "网段支持 192.168.1.0/24 或 192.168.1.0/255.255.255.0")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.ed_net = QLineEdit("192.168.1.0/24")
        self.ed_net.setPlaceholderText("192.168.1.0/24")
        self.ed_net.returnPressed.connect(self._do_split)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("按子网数量", "count")
        self.cmb_mode.addItem("按每子网主机数", "hosts")
        self.cmb_mode.currentIndexChanged.connect(self._mode_changed)
        self.sp_value = QSpinBox()
        self.sp_value.setRange(1, 65536)
        self.sp_value.setValue(4)
        self.sp_value.setMinimumWidth(96)
        self.btn_split = QPushButton("划分")
        self.btn_split.setProperty("variant", "primary")
        self.btn_split.clicked.connect(self._do_split)
        row.addWidget(QLabel("网段"))
        row.addWidget(self.ed_net, 2)
        row.addWidget(self.cmb_mode)
        row.addWidget(self.sp_value)
        row.addWidget(self.btn_split)
        card.add_layout(row)

        self.lbl_result = QLabel("")
        self.lbl_result.setObjectName("value")
        self.lbl_result.setWordWrap(True)
        card.add(self.lbl_result)
        self.lbl_err = QLabel("")
        self.lbl_err.setObjectName("hint")
        self.lbl_err.setWordWrap(True)
        card.add(self.lbl_err)
        self.body.addWidget(card)

        table_card = Card("划分明细", "最多显示 1024 行（更大空间请缩小前缀后重试）")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "网络地址", "子网掩码", "可用主机范围", "广播地址", "可用主机数"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(30)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setMinimumHeight(420)
        table_card.add(self.table)
        self.body.addWidget(table_card)

    def _mode_changed(self):
        self.sp_value.setValue(4 if self.cmb_mode.currentData() == "count" else 50)

    def _do_split(self):
        self.table.setRowCount(0)
        self.rows = []
        try:
            rows, desc, prefix = subnet_utils.split(
                self.ed_net.text(), self.cmb_mode.currentData(),
                self.sp_value.value(), normalize_mask)
        except ValueError as e:
            self.lbl_result.setText("无法划分")
            self.lbl_err.setText(str(e))
            return
        self.rows = rows
        self.lbl_result.setText(desc)
        self.lbl_err.setText(f"子网掩码统一为 /{prefix}，共 {len(rows)} 个子网"
                             + ("（仅显示前 1024 行）" if len(rows) >= 1024 else ""))
        for i, (net, mask, rng, bcast, hosts) in enumerate(rows):
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [str(i + 1), net, mask, rng, bcast, hosts]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (1, 2, 3, 4):
                    f = it.font()
                    f.setFamily("Menlo")
                    it.setFont(f)
                self.table.setItem(r, c, it)

    def _copy(self):
        if not self.rows:
            self.notify("没有可复制的结果", "info")
            return
        lines = ["#\t网络地址\t掩码\t可用范围\t广播地址\t主机数"]
        for i, row in enumerate(self.rows):
            lines.append(f"{i + 1}\t" + "\t".join(row))
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.notify(f"已复制 {len(self.rows)} 个子网")

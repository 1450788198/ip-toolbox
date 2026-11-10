"""操作记录：真实的配置变更历史，可查看详情与复制"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QLabel, QPlainTextEdit, QPushButton,
                               QStackedLayout, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core import history
from ..components import Card, EmptyState
from ..dialogs import confirm
from .base import Page


class HistoryPage(Page):
    def __init__(self, notify, parent=None):
        super().__init__("操作记录", "记录真实的配置变更与结果，可复制用于反馈")
        self.notify = notify
        self.items = []
        self._build()
        self.refresh()

    def _build(self):
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.add_action(self.btn_refresh)
        self.btn_clear = QPushButton("清空记录")
        self.btn_clear.setProperty("variant", "danger")
        self.btn_clear.clicked.connect(self._clear)
        self.add_action(self.btn_clear)

        wrap = QWidget()
        self.stack = QStackedLayout(wrap)
        self.stack.setContentsMargins(0, 0, 0, 0)

        card = Card()
        card.body.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["时间", "操作", "网卡", "结果", "变更"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(32)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        card.add(self.table, 1)
        self.stack.addWidget(card)

        self.empty = EmptyState("history", "暂无操作记录",
                                "修改 IP、DNS、路由或启停 DHCP 后，记录会出现在这里")
        self.stack.addWidget(self.empty)
        self.body.addWidget(wrap, 1)

        detail = Card("记录详情", "选中一行查看完整内容，可复制")
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setMinimumHeight(120)
        self.txt.setMaximumHeight(150)
        self.txt.setPlaceholderText("选择上方任意一条记录…")
        detail.add(self.txt)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_copy = QPushButton("复制这条记录")
        btn_copy.clicked.connect(self._copy)
        row.addWidget(btn_copy)
        detail.add_layout(row)
        self.body.addWidget(detail)
        self._current = None

    def on_show(self):
        self.refresh()

    def refresh_theme(self):
        self.empty.refresh_theme()

    def refresh(self):
        self.items = list(reversed(history.load()))
        self.table.setRowCount(0)
        for it in self.items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            change = f"{it.get('before') or '—'} → {it.get('after') or '—'}"
            vals = [it.get("time", ""), it.get("action", ""), it.get("service") or "—",
                    it.get("result", ""), change]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(str(v))
                if c == 0:
                    f = cell.font()
                    f.setFamily("Menlo")
                    cell.setFont(f)
                if c == 3:
                    cell.setForeground(Qt.darkGreen if it.get("result") == "成功"
                                       else Qt.darkYellow if it.get("result") == "部分失败"
                                       else Qt.red)
                self.table.setItem(r, c, cell)
        self.stack.setCurrentIndex(1 if not self.items else 0)
        self.txt.clear()
        self._current = None

    def _selection_changed(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.items):
            self._current = self.items[row]
            self.txt.setPlainText(history.copy_text(self._current))

    def _copy(self):
        if not self._current:
            self.notify("请先选中一条记录", "warn")
            return
        QGuiApplication.clipboard().setText(self.txt.toPlainText())
        self.notify("记录已复制")

    def _clear(self):
        if not confirm(self, "清空操作记录", "将删除本地保存的全部操作记录，是否继续？",
                       "清空", danger=True):
            return
        history.clear()
        self.refresh()
        self.notify("操作记录已清空")

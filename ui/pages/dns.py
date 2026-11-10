"""DNS 测速：国内公共 DNS / 分省运营商 DNS，测速排名并一键应用到网卡"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from core import dns_data, history
from core.netbase import iface_is_external, sort_interfaces
from ..common import Worker
from ..components import Card
from ..dialogs import confirm
from .base import Page

COLS = ["排名", "名称", "主 DNS", "备 DNS", "延迟(主)", "延迟(备)", "说明"]


class DnsPanel(QWidget):
    def __init__(self, providers, parent=None):
        super().__init__(parent)
        self.providers = list(providers)
        self.results = {}
        self._workers = []
        self.pending = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
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
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setMinimumHeight(240)
        v.addWidget(self.table)
        self._fill()

    def set_providers(self, providers):
        self.providers = list(providers)
        self.results = {}
        self._fill()

    def _fill(self):
        self.table.setRowCount(0)
        for r, p in enumerate(self.providers):
            name, primary, secondary, desc = p
            entry = self.results.get(name) or (None, None, False)
            ms1, ms2 = entry[0], entry[1]
            self.table.insertRow(r)
            vals = [str(r + 1), name, primary, secondary or "—",
                    self._ms_text(ms1), self._ms_text(ms2), desc]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (2, 3):
                    f = it.font()
                    f.setFamily("Menlo")
                    it.setFont(f)
                if c in (4, 5) and self.results.get(name):
                    it.setForeground(self._color(ms1 if c == 4 else ms2))
                if c == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)

    @staticmethod
    def _ms_text(ms):
        return "—" if ms is None else (f"{ms:.0f} ms" if ms != -1 else "超时")

    @staticmethod
    def _color(ms):
        from PySide6.QtGui import QColor
        if ms is None:
            return QColor("#86868B")
        if ms == -1:
            return QColor("#FF453A")
        if ms < 30:
            return QColor("#30A46C")
        if ms < 100:
            return QColor("#E5A000")
        return QColor("#FF453A")

    def selected(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.providers):
            return self.providers[r]
        return None

    def run_test(self, on_done=None):
        self.pending = 0
        for name, primary, secondary, _d in self.providers:
            self.results.pop(name, None)
            for ip in (primary, secondary):
                if not ip:
                    continue
                self.pending += 1
                w = Worker(dns_data.ping_ms, ip)
                w.ok.connect(lambda ms, n=name, addr=ip: self._one(n, addr, ms, primary))
                w.start()
                self._workers.append(w)
        self._fill()
        if self.pending == 0:
            if on_done:
                on_done()
            return
        self._on_done = on_done

    def _one(self, name, addr, ms, primary):
        value = -1 if ms is None else ms
        entry = list(self.results.get(name, (None, None, False)))
        if addr == primary:
            entry[0] = value
        else:
            entry[1] = value
        self.results[name] = tuple(entry)
        self.pending -= 1
        self._fill()
        if self.pending <= 0:
            self._rank()
            if getattr(self, "_on_done", None):
                cb, self._on_done = self._on_done, None
                cb()

    def _rank(self):
        def key(p):
            ms1, ms2, _ = self.results.get(p[0], (None, None, False))
            best = ms1 if ms1 not in (None, -1) else (ms2 if ms2 not in (None, -1) else 10 ** 6)
            return best
        self.providers.sort(key=key)
        self._fill()


class DnsPage(Page):
    def __init__(self, backend, log, notify, parent=None):
        super().__init__("DNS 测速", "国内公共 DNS 与分省运营商 DNS，测速后可直接应用到网卡")
        self.backend = backend
        self.log = log
        self.notify = notify
        self._workers = []
        self._build()
        self.reload_ifaces()

    def _build(self):
        self.btn_test = QPushButton("测速")
        self.btn_test.setProperty("variant", "primary")
        self.btn_test.clicked.connect(self._test)
        self.add_action(self.btn_test)

        card = Card("DNS 列表", "测速会向主备 DNS 各发一个 ping 包，约 2~5 秒")
        self.tabs = QTabWidget()
        self.panel_public = DnsPanel(dns_data.PUBLIC_DNS)
        self.tabs.addTab(self.panel_public, "公共 DNS")

        isp_wrap = QWidget()
        iv = QVBoxLayout(isp_wrap)
        iv.setContentsMargins(0, 6, 0, 0)
        iv.setSpacing(8)
        prow = QHBoxLayout()
        prow.setSpacing(8)
        prow.addWidget(QLabel("省份"))
        self.cmb_prov = QComboBox()
        self.cmb_prov.addItems(dns_data.PROVINCES)
        self.cmb_prov.currentTextChanged.connect(self._load_province)
        prow.addWidget(self.cmb_prov)
        tip = QLabel("运营商 DNS 为省内节点，实际以宽带自动下发为准")
        tip.setObjectName("hint")
        prow.addWidget(tip)
        prow.addStretch(1)
        iv.addLayout(prow)
        self.panel_isp = DnsPanel(dns_data.isp_providers("黑龙江"))
        iv.addWidget(self.panel_isp, 1)
        self.tabs.addTab(isp_wrap, "运营商 DNS（分省）")
        card.add(self.tabs, 1)
        self.body.addWidget(card, 1)

        bottom = Card("应用到网卡", "对当前标签页选中的 DNS 生效，写入后立即切换")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("目标网卡"))
        self.cmb_iface = QComboBox()
        self.cmb_iface.setMinimumWidth(280)
        row.addWidget(self.cmb_iface, 1)
        btn_reload = QPushButton("刷新网卡")
        btn_reload.clicked.connect(self.reload_ifaces)
        row.addWidget(btn_reload)
        self.btn_apply = QPushButton("设为 DNS")
        self.btn_apply.setProperty("variant", "primary")
        self.btn_apply.clicked.connect(self._apply)
        row.addWidget(self.btn_apply)
        self.btn_auto = QPushButton("恢复自动获取")
        self.btn_auto.clicked.connect(self._restore)
        row.addWidget(self.btn_auto)
        bottom.add_layout(row)
        self.body.addWidget(bottom)

    # ---- 数据 ----
    def on_show(self):
        self.reload_ifaces()

    def _load_province(self, province):
        self.panel_isp.set_providers(dns_data.isp_providers(province))

    def reload_ifaces(self):
        if getattr(self, "state", None) is not None and self.state.ifaces():
            self._ifaces(self.state.ifaces())
            return
        w = Worker(self.backend.list_interfaces)
        w.ok.connect(self._ifaces)
        w.err.connect(lambda m: self.notify(f"刷新网卡失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _ifaces(self, ifaces):
        cur = self.cmb_iface.currentData()
        self.cmb_iface.clear()
        for i in sort_interfaces(ifaces):
            label = f"{i.get('service') or i.get('port')} ({i.get('device')})"
            if iface_is_external(i):
                label += " · USB"
            self.cmb_iface.addItem(label, i.get("service") or i.get("port"))
        if cur:
            idx = self.cmb_iface.findData(cur)
            if idx >= 0:
                self.cmb_iface.setCurrentIndex(idx)

    def _panel(self) -> DnsPanel:
        return self.panel_public if self.tabs.currentIndex() == 0 else self.panel_isp

    # ---- 操作 ----
    def _test(self):
        self.btn_test.setEnabled(False)
        self.btn_test.setText("测速中…")
        panel = self._panel()
        panel.run_test(lambda: self._test_done())

    def _test_done(self):
        self.btn_test.setEnabled(True)
        self.btn_test.setText("测速")
        self.notify("测速完成，已按延迟排序")

    def _apply(self):
        p = self._panel().selected()
        if not p:
            self.notify("请先在列表中选择一行 DNS", "warn")
            return
        svc = self.cmb_iface.currentData()
        if not svc:
            self.notify("请选择目标网卡", "warn")
            return
        name, primary, secondary, _desc = p
        dns_list = [primary] + ([secondary] if secondary else [])
        if not confirm(self, "设置 DNS",
                       f"将「{svc}」的 DNS 设为：\n{name}\n" + "\n".join(dns_list), "设置"):
            return

        def job():
            self.backend.set_dns(svc, dns_list)
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._applied(svc, name, dns_list))
        w.err.connect(lambda m: self.notify(f"设置失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _applied(self, svc, name, dns_list):
        history.record("设置 DNS", svc, "", f"{name} · {', '.join(dns_list)}", "成功", "")
        self.notify(f"DNS 已设置为 {name}")

    def _restore(self):
        svc = self.cmb_iface.currentData()
        if not svc:
            self.notify("请选择目标网卡", "warn")
            return
        if not confirm(self, "恢复自动获取", f"清除「{svc}」的手动 DNS，改由 DHCP 下发？", "恢复"):
            return

        def job():
            self.backend.set_dns(svc, [])
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._restored(svc))
        w.err.connect(lambda m: self.notify(f"清除失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _restored(self, svc):
        history.record("恢复自动 DNS", svc, "手动 DNS", "自动获取", "成功", "")
        self.notify("已恢复自动获取 DNS")

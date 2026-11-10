"""路由管理：业务视图表格、搜索、添加/删除、最长前缀匹配分析"""
import ipaddress

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QStackedLayout)

from core import history
from core.netbase import (classify_route, is_system_route, normalize_mask,
                          sort_routes)
from ..common import Worker
from ..components import Card, EmptyState, PageHeader
from ..dialogs import DialogBase, RouteDialog, confirm
from .base import Page


class LookupDialog(DialogBase):
    """最长前缀匹配分析：输入一个目标 IP，看会被哪条路由命中"""

    def __init__(self, parent, routes):
        super().__init__(parent, "路由匹配分析",
                         "输入目标 IP，按最长前缀匹配判断实际走哪条路由", 560)
        self.routes = routes
        row = QHBoxLayout()
        row.setSpacing(8)
        self.ed_ip = QLineEdit()
        self.ed_ip.setPlaceholderText("例: 10.20.5.8")
        btn = QPushButton("分析")
        btn.setProperty("variant", "primary")
        btn.clicked.connect(self._analyze)
        row.addWidget(self.ed_ip, 1)
        row.addWidget(btn)
        self.body.addLayout(row)
        self.result = QLabel("")
        self.result.setObjectName("value")
        self.result.setWordWrap(True)
        self.body.addWidget(self.result)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["命中路由", "网关", "接口"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(30)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(170)
        self.body.addWidget(self.table)
        self.add_cancel("关闭")
        self.ed_ip.setFocus()
        self.ed_ip.returnPressed.connect(self._analyze)

    def _analyze(self):
        text = self.ed_ip.text().strip()
        self.table.setRowCount(0)
        try:
            ip = ipaddress.IPv4Address(text)
        except ValueError:
            self.result.setText("请输入有效的 IPv4 地址")
            return
        matches = []
        for r in self.routes:
            dest = r.get("destination", "")
            try:
                net = ipaddress.ip_network(dest if "/" in dest else f"{dest}/32", strict=False)
            except ValueError:
                continue
            if dest == "default":
                matches.append((0, r))
            elif ip in net:
                matches.append((net.prefixlen, r))
        matches.sort(key=lambda m: m[0], reverse=True)
        if not matches:
            self.result.setText("没有匹配的路由，该地址将无法访问")
            return
        best = matches[0]
        self.result.setText(
            f"{ip} 命中 {best[1].get('destination')}（前缀 /{best[0]}），"
            f"下一跳 {best[1].get('gateway') or '直连'}，接口 {best[1].get('iface') or '—'}")
        for prefix, r in matches[:10]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(
                f"{r.get('destination')}  （/{prefix}）"))
            self.table.setItem(row, 1, QTableWidgetItem(str(r.get("gateway") or "直连")))
            self.table.setItem(row, 2, QTableWidgetItem(str(r.get("iface") or "—")))


class RoutesPage(Page):
    def __init__(self, backend, log, notify, parent=None):
        super().__init__("路由管理", "默认隐藏默认网关 / VPN / 系统保留路由，只显示现场手工路由")
        self.backend = backend
        self.log = log
        self.notify = notify
        self.routes = []
        self.shown = []
        self._workers = []
        self._build()
        self.refresh()

    def _build(self):
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.add_action(self.btn_refresh)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("搜索目标 / 网关 / 接口")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.setMaximumWidth(260)
        self.ed_search.textChanged.connect(self._render)
        self.chk_all = QCheckBox("显示系统 / VPN / 默认路由")
        self.chk_all.toggled.connect(self._render)
        self.btn_lookup = QPushButton("匹配分析")
        self.btn_lookup.clicked.connect(self._lookup)
        self.btn_add = QPushButton("添加路由")
        self.btn_add.setProperty("variant", "primary")
        self.btn_add.clicked.connect(self._add)
        self.btn_del = QPushButton("删除选中")
        self.btn_del.setProperty("variant", "danger")
        self.btn_del.clicked.connect(self._delete)
        bar.addWidget(self.ed_search)
        bar.addWidget(self.chk_all)
        bar.addStretch(1)
        bar.addWidget(self.btn_lookup)
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_del)
        self.body.addLayout(bar)

        wrap = QWidget()
        self.stack = QStackedLayout(wrap)
        self.stack.setContentsMargins(0, 0, 0, 0)

        card = Card()
        card.body.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["目标网络", "前缀", "下一跳", "出口接口", "类型", "持久化"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(32)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4, 5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        card.add(self.table, 1)
        self.stack.addWidget(card)

        self.empty = EmptyState("routes", "暂无手工路由",
                                "在客户现场添加的静态路由会显示在这里\n"
                                "默认网关 / VPN / 系统保留路由已自动隐藏",
                                "添加路由", self._add)
        self.stack.addWidget(self.empty)
        self.body.addWidget(wrap, 1)

        self.card_detail = Card()
        detail = QHBoxLayout()
        detail.setSpacing(20)
        self.lbl_detail = QLabel("选择一条路由查看详情")
        self.lbl_detail.setObjectName("hint")
        self.lbl_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail.addWidget(self.lbl_detail, 1)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("hint")
        detail.addWidget(self.lbl_count)
        self.card_detail.add_layout(detail)
        self.body.addWidget(self.card_detail)

    # ---------------- 数据 ----------------
    def on_show(self):
        self.refresh()

    def refresh_theme(self):
        self.empty.refresh_theme()

    def refresh(self):
        self.btn_refresh.setEnabled(False)
        w = Worker(self.backend.list_routes)
        w.ok.connect(self._fill)
        w.err.connect(self._err)
        w.start()
        self._workers.append(w)

    def _fill(self, routes):
        self.btn_refresh.setEnabled(True)
        self.routes = sort_routes(routes)
        self._render()
        n_sys = sum(1 for r in self.routes if is_system_route(r))
        self.log(f"路由表已刷新：{len(self.routes)} 条（业务 "
                 f"{len(self.routes) - n_sys} 条 + 系统 {n_sys} 条）")

    def _err(self, msg):
        self.btn_refresh.setEnabled(True)
        self.notify(f"读取路由表失败：{msg}", "err")

    @staticmethod
    def _prefix(r) -> str:
        dest = r.get("destination", "")
        if dest == "default":
            return "/0"
        if "/" in dest:
            return "/" + dest.split("/")[1]
        mask = r.get("netmask") or ""
        try:
            return f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}').prefixlen}"
        except Exception:
            return "/32" if r.get("flags", "").startswith("UH") else ""

    def _render(self):
        text = self.ed_search.text().strip().lower()
        show_all = self.chk_all.isChecked()
        items = []
        for r in self.routes:
            if not show_all and is_system_route(r):
                continue
            hay = f"{r.get('destination')} {r.get('gateway')} {r.get('iface')}".lower()
            if text and text not in hay:
                continue
            items.append(r)
        self.shown = items
        self.table.setRowCount(0)
        for r in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            typ = classify_route(r)
            vals = [r.get("destination", ""), self._prefix(r),
                    str(r.get("gateway") or "直连"), r.get("iface") or "—", typ,
                    "持久" if r.get("persistent") else "临时"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (0, 2):
                    f = it.font()
                    f.setFamily("Menlo")
                    it.setFont(f)
                if c == 4:
                    it.setForeground(Qt.darkGreen if typ == "直连路由"
                                     else Qt.darkBlue if typ == "默认路由" else Qt.gray)
                if c == 5:
                    it.setForeground(Qt.gray)
                self.table.setItem(row, c, it)
        self.stack.setCurrentIndex(1 if not items else 0)
        self.lbl_count.setText(
            f"显示 {len(items)} 条"
            + ("" if show_all else f"（已隐藏 {len(self.routes) - len(items)} 条系统路由）"))
        self.lbl_detail.setText("选择一条路由查看详情")

    def _selection_changed(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.shown):
            return
        r = self.shown[row]
        self.lbl_detail.setText(
            f"目标 {r.get('destination')}　·　下一跳 {r.get('gateway') or '直连'}　·　"
            f"接口 {r.get('iface') or '—'}　·　类型 {classify_route(r)}　·　"
            f"{'持久路由' if r.get('persistent') else '临时路由（重启后失效）'}")

    # ---------------- 操作 ----------------
    def _add(self):
        dlg = RouteDialog(self, self._iface_hints())
        while True:
            if not dlg.exec():
                return
            try:
                dest, gw, mask, iface, persist = dlg.values()
                break
            except ValueError as e:
                dlg.err.setText(str(e))
                continue
        self.btn_add.setEnabled(False)

        def job():
            self.backend.add_route(dest, gw, mask, iface or "", persist)
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._added(dest, gw, iface))
        w.err.connect(lambda m: self._add_err(m))
        w.start()
        self._workers.append(w)

    def _iface_hints(self):
        if getattr(self, "state", None) is not None and self.state.ifaces():
            return self.state.ifaces()
        try:
            from core.netbase import sort_interfaces
            return sort_interfaces(self.backend.list_interfaces())
        except Exception:
            return []

    def _added(self, dest, gw, iface):
        self.btn_add.setEnabled(True)
        history.record("添加路由", "", "", f"{dest} → {gw} ({iface or '自动'})", "成功", "")
        self.notify(f"路由 {dest} 已添加")
        self.refresh()

    def _add_err(self, msg):
        self.btn_add.setEnabled(True)
        history.record("添加路由", "", "", "", "失败", str(msg)[:200])
        self.notify(f"添加失败：{msg}", "err")

    def _delete(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.shown):
            self.notify("请先选中要删除的路由", "warn")
            return
        r = self.shown[row]
        dest = r.get("destination")
        if not confirm(self, "删除路由",
                       f"删除路由 {dest}（下一跳 {r.get('gateway') or '直连'}）？",
                       "删除", danger=True):
            return

        def job():
            self.backend.delete_route(dest, r.get("gateway", ""), r.get("iface", ""))
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._deleted(dest))
        w.err.connect(lambda m: self.notify(f"删除失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _deleted(self, dest):
        history.record("删除路由", "", dest, "", "成功", "")
        self.notify(f"路由 {dest} 已删除")
        self.refresh()

    def _lookup(self):
        LookupDialog(self, self.routes).exec()

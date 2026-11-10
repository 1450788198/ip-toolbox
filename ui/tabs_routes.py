"""标签页 4：路由管理（业务视图：默认隐藏系统保留路由）"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPushButton,
                               QStackedLayout, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.netbase import classify_route, is_system_route, normalize_mask, sort_routes
from .common import Worker


def _empty_icon() -> QPixmap:
    """空状态插画：抽屉图形（macOS 风格线条）"""
    pm = QPixmap(96, 72)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#b9b9c0"))
    pen.setWidth(3)
    p.setPen(pen)
    p.drawRoundedRect(14, 14, 68, 48, 8, 8)
    p.drawLine(14, 34, 34, 34)
    p.drawArc(37, 26, 22, 16, 180 * 16, 180 * 16)
    p.drawLine(62, 34, 82, 34)
    p.end()
    return pm


class RoutesTab(QWidget):
    COLS = ["目标网络", "网关", "接口", "类型", "Flags"]

    def __init__(self, backend, log, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.log = log
        self._worker = None
        self.routes = []
        self._row_routes = []   # 当前行号 → 路由对象映射（过滤后）
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedLayout()
        outer.addLayout(self._stack, 1)

        # ---- 第 0 页：主内容 ----
        v = QWidget()
        sv = QVBoxLayout(v)
        sv.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(32)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(True)
        sv.addWidget(self.table, 1)

        # 过滤开关
        hf = QHBoxLayout()
        self.chk_show_all = QCheckBox("显示全部路由（默认网关 / VPN 隧道 / 系统保留）")
        self.chk_show_all.setChecked(False)
        self.chk_show_all.toggled.connect(lambda _: self._render())
        hf.addWidget(self.chk_show_all)
        hf.addStretch(1)
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color:#86868b;font-size:12px;")
        hf.addWidget(self.lbl_count)
        sv.addLayout(hf)

        gb = QGroupBox("添加静态路由")
        f = QFormLayout(gb)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.ed_dest = QLineEdit()
        self.ed_dest.setPlaceholderText("例: 10.20.0.0/16 或 10.20.1.5（单主机）")
        self.ed_gw = QLineEdit()
        self.ed_gw.setPlaceholderText("下一跳网关，例: 192.168.1.254")
        self.ed_mask = QLineEdit()
        self.ed_mask.setPlaceholderText("可选，255.255.0.0 或 16 均可")
        self.ed_iface = QLineEdit()
        self.ed_iface.setPlaceholderText("可选，macOS: en0 / Windows: 接口序号")
        self.chk_persist = QCheckBox("持久路由（写入系统配置）")
        self.chk_persist.setToolTip("Windows 支持 route -p 持久化；macOS 路由为临时路由，重启后失效")
        from core.netbase import IS_WIN
        self.chk_persist.setEnabled(IS_WIN)
        if not IS_WIN:
            self.chk_persist.setText("持久路由（macOS 暂不支持，路由重启后失效）")
        f.addRow("目标网络:", self.ed_dest)
        f.addRow("网关:", self.ed_gw)
        f.addRow("子网掩码:", self.ed_mask)
        f.addRow("出接口:", self.ed_iface)
        f.addRow("", self.chk_persist)
        h = QHBoxLayout()
        self.btn_add = QPushButton("添加路由")
        self.btn_add.setObjectName("primaryBtn")
        self.btn_del = QPushButton("删除选中路由")
        self.btn_del.setObjectName("dangerBtn")
        self.btn_refresh = QPushButton("刷新路由表")
        h.addWidget(self.btn_add)
        h.addWidget(self.btn_del)
        h.addWidget(self.btn_refresh)
        h.addStretch(1)
        f.addRow(h)
        sv.addWidget(gb)

        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._delete)
        self.btn_refresh.clicked.connect(self.refresh)

        # ---- 第 1 页：空状态 ----
        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.setAlignment(Qt.AlignCenter)
        icon = QLabel()
        icon.setPixmap(_empty_icon())
        icon.setAlignment(Qt.AlignCenter)
        ev.addWidget(icon)
        lbl = QLabel("暂无手工路由")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#86868b;font-size:15px;font-weight:600;")
        ev.addWidget(lbl)
        sub = QLabel("在客户现场添加的静态路由会显示在这里\n（默认网关 / VPN / 系统路由已自动隐藏）")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#aeaeb2;font-size:12px;")
        ev.addWidget(sub)
        self.btn_empty_add = QPushButton("添加路由")
        self.btn_empty_add.setObjectName("primaryBtn")
        ev.addWidget(self.btn_empty_add, 0, Qt.AlignCenter)
        self.btn_empty_add.clicked.connect(self._add)

        self._stack.addWidget(v)
        self._stack.addWidget(empty)
        self._stack.setCurrentIndex(1)  # 初始显示空状态，加载完成后切换

    def refresh(self):
        self.btn_refresh.setEnabled(False)
        w = Worker(self.backend.list_routes)
        w.ok.connect(self._fill)
        w.err.connect(self._err)
        w.start()
        self._worker = w

    def _fill(self, routes):
        self.routes = sort_routes(routes)
        self._render()
        self.btn_refresh.setEnabled(True)
        n_sys = sum(1 for r in self.routes if is_system_route(r))
        self.log(f"路由表已刷新：{len(self.routes)} 条"
                 f"（业务 {len(self.routes) - n_sys} 条 + 系统保留 {n_sys} 条）")

    def _render(self):
        """根据过滤开关渲染表格（行号 → 路由对象映射保存在 self._row_routes）"""
        show_all = self.chk_show_all.isChecked()
        shown = [r for r in self.routes
                 if show_all or not is_system_route(r)]
        self._row_routes = shown
        self.lbl_count.setText(f"手工路由 {len(shown)} 条" + ("" if show_all
                               else f"（已隐藏 {len(self.routes) - len(shown)} 条默认/VPN/系统路由）"))
        self._stack.setCurrentIndex(1 if not self.routes else 0)
        self.table.setRowCount(0)
        for r in shown:
            row = self.table.rowCount()
            self.table.insertRow(row)
            typ = classify_route(r)
            vals = [r.get("destination", ""), r.get("gateway", ""),
                    r.get("iface", ""), typ, r.get("flags") or ""]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                if c == 3:
                    if typ == "默认路由":
                        it.setForeground(QColor("#2f6fd3"))
                        f = it.font()
                        f.setBold(True)
                        it.setFont(f)
                    elif typ == "直连路由":
                        it.setForeground(QColor("#86868b"))
                if c == 4:
                    it.setForeground(QColor("#aeaeb2"))
                self.table.setItem(row, c, it)

    def _err(self, msg):
        self.btn_refresh.setEnabled(True)
        self.log(f"读取路由表失败: {msg}", "ERROR")
        QMessageBox.warning(self, "读取失败", msg)

    def _add(self):
        dest = self.ed_dest.text().strip()
        gw = self.ed_gw.text().strip()
        if not dest or not gw:
            QMessageBox.warning(self, "缺少参数", "目标网络和网关不能为空")
            return
        try:
            mask = normalize_mask(self.ed_mask.text()) if self.ed_mask.text().strip() else ""
        except ValueError as e:
            QMessageBox.warning(self, "掩码有误", str(e))
            return
        iface = self.ed_iface.text().strip()
        persist = self.chk_persist.isChecked()
        if QMessageBox.question(self, "确认",
                f"添加路由 {dest} -> 网关 {gw}"
                f"{'（持久）' if persist else ''}？") != QMessageBox.Yes:
            return
        self.log(f"添加路由 {dest} via {gw} ...")
        w = Worker(self.backend.add_route, dest, gw, mask, iface, persist)
        w.ok.connect(lambda _: (self.log(f"路由 {dest} 已添加"),
                                QMessageBox.information(self, "完成", "路由已添加"),
                                self.refresh()))
        w.err.connect(lambda m: (self.log(f"添加路由失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "添加失败", m)))
        w.start()
        self._worker = w

    def _delete(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "提示", "请先在路由表中选中要删除的路由")
            return
        r = self._row_routes[list(rows)[0]]
        if QMessageBox.question(self, "确认",
                f"删除路由 {r['destination']}（网关 {r.get('gateway')}）？") != QMessageBox.Yes:
            return
        self.log(f"删除路由 {r['destination']} ...")
        w = Worker(self.backend.delete_route, r["destination"], r.get("gateway", ""),
                   r.get("iface", ""))
        w.ok.connect(lambda _: (self.log(f"路由 {r['destination']} 已删除"), self.refresh()))
        w.err.connect(lambda m: (self.log(f"删除路由失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "删除失败", m)))
        w.start()
        self._worker = w

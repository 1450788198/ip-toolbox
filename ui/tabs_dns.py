"""标签页 7：DNS 快速查询（国内公共 DNS + 全国分省运营商 DNS，测速 + 一键应用）

运营商数据来源：dnsdaquan.com / ip138 / 运维兔 等公开资料整理（2025-2026）。
运营商 DNS 为省内节点，由运营商维护，可能随线路调整，以当地实际下发为准。
"""
import re
import subprocess

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.netbase import sort_interfaces, iface_is_external
from .common import Worker

# ---------------- 国内公共 DNS（名称, 主, 备, 特点） ----------------
PUBLIC_DNS = [
    ("阿里 AliDNS",     "223.5.5.5",       "223.6.6.6",        "纯净无劫持，节点覆盖广，通用推荐"),
    ("腾讯 DNSPod",     "119.29.29.29",    "182.254.116.116",  "稳定快速，国内覆盖好"),
    ("114 DNS",         "114.114.114.114", "114.114.115.115",  "老牌公共 DNS，纯净版"),
    ("百度 DNS",        "180.76.76.76",    "",                 "百度公共 DNS"),
    ("360 安全 DNS",    "101.226.4.6",     "218.30.118.6",     "拦截钓鱼与恶意网站"),
    ("CNNIC SDNS",      "1.2.4.8",         "210.2.4.8",        "国家顶级节点，权威纯净"),
    ("火山引擎",        "180.184.1.1",     "180.184.2.2",      "字节跳动公共 DNS"),
    ("OneDNS 纯净版",   "117.50.10.10",    "117.50.22.22",     "拦截广告与恶意域名"),
]

# ---------------- 全国分省运营商 DNS ----------------
# 省份顺序：黑龙江置顶（默认），其余按地理/拼音大致排列
ISP_PROVINCES = ["黑龙江", "吉林", "辽宁", "北京", "上海", "天津", "重庆",
                 "河北", "山西", "内蒙古", "山东", "河南", "江苏", "浙江",
                 "安徽", "福建", "江西", "湖北", "湖南", "广东", "广西",
                 "海南", "四川", "贵州", "云南", "陕西", "甘肃", "新疆",
                 "西藏", "宁夏"]

DNS_TELECOM = {
    "黑龙江": ("219.147.198.230", "219.147.198.242"),
    "吉林":   ("219.149.194.55", ""),
    "辽宁":   ("219.148.204.66", ""),
    "北京":   ("219.141.136.10", "219.141.140.10"),
    "上海":   ("202.96.209.133", "116.228.111.118"),
    "天津":   ("219.150.32.132", "219.146.0.132"),
    "重庆":   ("61.128.192.68", "61.128.128.68"),
    "河北":   ("222.222.202.202", ""),
    "山西":   ("59.49.49.49", ""),
    "内蒙古": ("219.148.162.31", "222.74.39.50"),
    "山东":   ("219.146.1.66", "219.147.1.66"),
    "河南":   ("222.88.88.88", "222.85.85.85"),
    "江苏":   ("218.2.2.2", "218.4.4.4"),
    "浙江":   ("202.101.172.35", "202.101.172.47"),
    "安徽":   ("61.132.163.68", "202.102.213.68"),
    "福建":   ("218.85.152.99", "218.85.157.99"),
    "江西":   ("202.101.224.69", "202.101.226.68"),
    "湖北":   ("202.103.24.68", "202.103.0.68"),
    "湖南":   ("59.51.78.211", "59.51.78.210"),
    "广东":   ("202.96.128.86", "202.96.128.166"),
    "广西":   ("202.103.225.68", "202.103.224.68"),
    "海南":   ("202.100.192.68", ""),
    "四川":   ("61.139.2.69", "218.6.200.139"),
    "贵州":   ("202.98.192.67", "202.98.198.167"),
    "云南":   ("222.172.200.68", "61.166.150.123"),
    "陕西":   ("218.30.19.40", "61.134.1.4"),
    "甘肃":   ("202.100.64.68", "61.178.0.93"),
    "新疆":   ("61.128.114.167", ""),
}
DNS_UNICOM = {
    "黑龙江": ("202.97.224.68", "202.97.224.69"),
    "吉林":   ("202.98.0.68", "202.98.5.68"),
    "辽宁":   ("202.96.69.38", "202.96.64.68"),
    "北京":   ("123.123.123.123", "123.123.123.124"),
    "上海":   ("210.22.70.3", "210.22.84.3"),
    "天津":   ("202.99.104.68", "202.99.96.68"),
    "重庆":   ("221.5.203.98", "221.7.92.98"),
    "河北":   ("202.99.160.68", "202.99.166.4"),
    "山西":   ("202.99.192.66", "202.99.192.68"),
    "内蒙古": ("202.99.224.68", "202.99.224.8"),
    "山东":   ("202.102.128.68", "202.102.152.3"),
    "河南":   ("202.102.224.68", "202.102.227.68"),
    "江苏":   ("221.6.4.66", "221.6.4.67"),
    "浙江":   ("221.12.1.227", "221.12.33.227"),
    "安徽":   ("218.104.78.2", "58.242.2.2"),
    "福建":   ("218.104.128.106", ""),
    "江西":   ("220.248.192.12", ""),
    "湖北":   ("218.104.111.122", ""),
    "湖南":   ("58.20.127.238", ""),
    "广东":   ("210.21.196.6", "221.5.88.88"),
    "广西":   ("221.7.128.68", ""),
    "海南":   ("221.11.132.2", ""),
    "四川":   ("119.6.6.6", "124.161.87.155"),
    "贵州":   ("221.13.30.242", ""),
    "云南":   ("221.3.131.11", ""),
    "陕西":   ("221.11.1.67", "221.11.1.68"),
    "甘肃":   ("221.7.34.11", ""),
    "新疆":   ("221.7.1.20", ""),
    "西藏":   ("221.13.65.34", ""),
    "宁夏":   ("221.199.12.157", ""),
}
DNS_MOBILE = {
    "黑龙江": ("211.137.241.34", "211.137.241.35"),
    "北京":   ("211.138.30.66", "211.136.17.107"),
    "上海":   ("211.136.112.50", "211.136.150.66"),
    "天津":   ("211.137.160.50", "211.137.160.185"),
    "重庆":   ("218.201.4.3", "218.201.21.132"),
    "安徽":   ("211.138.180.2", "211.138.180.3"),
    "山东":   ("218.201.96.130", "211.137.191.26"),
    "山西":   ("211.138.106.2", "211.138.106.3"),
    "江苏":   ("221.131.143.69", "112.4.0.55"),
    "浙江":   ("211.140.13.188", "211.140.188.188"),
    "湖南":   ("211.142.210.98", "211.142.210.99"),
}


def isp_providers(province: str):
    """返回某省运营商 DNS 行 [(名称, 主, 备, 说明)]"""
    rows = []
    for isp, src in (("中国电信", DNS_TELECOM), ("中国联通", DNS_UNICOM),
                     ("中国移动", DNS_MOBILE)):
        if province in src:
            p, s = src[province]
            rows.append((isp, p, s, f"{province}省内节点，运营商本地解析"))
    return rows


COL_NAME, COL_P, COL_S, COL_DESC, COL_MS_P, COL_MS_S = range(6)
COLS = ["名称", "主 DNS", "备 DNS", "说明", "延迟(主)", "延迟(备)"]


def _ping_ms(ip: str):
    """返回延迟毫秒数；不通返回 None"""
    if not ip:
        return None
    try:
        p = subprocess.run(["ping", "-c", "1", "-W", "2000", ip],
                           capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    m = re.search(r"time[=<]([\d.]+)\s*ms", p.stdout)
    return float(m.group(1)) if m else 0.0


def _ms_text(ms):
    return f"{ms:.0f} ms" if ms is not None else "超时"


def _ms_color(ms):
    if ms is None:
        return QColor("#c04343")
    if ms < 30:
        return QColor("#1d7a34")
    if ms < 100:
        return QColor("#b0700a")
    return QColor("#c04343")


def _fill_cell(tbl, row, col, ms):
    it = QTableWidgetItem(_ms_text(ms))
    it.setForeground(_ms_color(ms))
    it.setTextAlignment(Qt.AlignCenter)
    tbl.setItem(row, col, it)


class DnsListPanel(QWidget):
    """一张 DNS 列表 + 测速按钮（公共 DNS / 运营商 DNS 两个面板共用）"""

    def __init__(self, providers, tip, parent=None):
        super().__init__(parent)
        self.providers = list(providers)
        self._workers = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        self.tbl = QTableWidget(len(self.providers), len(COLS))
        self.tbl.setHorizontalHeaderLabels(COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self.tbl.setColumnWidth(COL_NAME, 120)
        self.tbl.setColumnWidth(COL_P, 135)
        self.tbl.setColumnWidth(COL_S, 135)
        self.tbl.setColumnWidth(COL_DESC, 230)
        self.tbl.setColumnWidth(COL_MS_P, 75)
        self.tbl.setColumnWidth(COL_MS_S, 75)
        v.addWidget(self.tbl)

        hb = QHBoxLayout()
        self.btn_ping = QPushButton("测速")
        self.btn_ping.setObjectName("primaryBtn")
        self.btn_ping.clicked.connect(self.run_ping)
        self.lbl_tip = QLabel(tip)
        self.lbl_tip.setStyleSheet("color:#86868b;")
        hb.addWidget(self.btn_ping)
        hb.addWidget(self.lbl_tip)
        hb.addStretch(1)
        v.addLayout(hb)

        self._populate(tip)

    def _populate(self, tip=None):
        """按 self.providers 重建表格内容"""
        self.tbl.clearContents()
        self.tbl.setRowCount(len(self.providers))
        for r, (name, p, s, desc) in enumerate(self.providers):
            for c, val in enumerate((name, p, s or "—", desc)):
                it = QTableWidgetItem(val)
                if c in (COL_P, COL_S):
                    f = it.font()
                    f.setFamily("Menlo")
                    it.setFont(f)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tbl.setItem(r, c, it)
            self.tbl.setItem(r, COL_MS_P, QTableWidgetItem("—"))
            self.tbl.setItem(r, COL_MS_S, QTableWidgetItem("—"))
        if tip is not None:
            self.lbl_tip.setText(tip)

    def selected(self):
        r = self.tbl.currentRow()
        if r < 0 or r >= len(self.providers):
            return None
        return self.providers[r]

    def run_ping(self):
        self.btn_ping.setEnabled(False)
        self.lbl_tip.setText("测速中…")
        for r, (_n, p, s, _d) in enumerate(self.providers):
            for col, ip in ((COL_MS_P, p), (COL_MS_S, s)):
                w = Worker(_ping_ms, ip)
                w.ok.connect(lambda ms, rr=r, cc=col: _fill_cell(self.tbl, rr, cc, ms))
                w.start()
                self._workers.append(w)
        QTimer.singleShot(3200, self._ping_done)

    def _ping_done(self):
        self.btn_ping.setEnabled(True)
        self.lbl_tip.setText("测速完成（绿 <30ms，橙 <100ms，红 更慢/超时）")


class DnsTab(QWidget):
    def __init__(self, backend, log, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.log = log
        self._workers = []
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        # ---- 内页：公共 DNS / 运营商 DNS（分省） ----
        self.tabs = QTabWidget()
        self.panel_public = DnsListPanel(
            PUBLIC_DNS, "向各 DNS 发一个 ping 包（约 2 秒出结果）")
        self.tabs.addTab(self.panel_public, "公共 DNS")

        # 运营商页：省份选择条 + 列表
        self.panel_isp = DnsListPanel([], "")
        prov_bar = QWidget()
        ph = QHBoxLayout(prov_bar)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.addWidget(QLabel("省份:"))
        self.cmb_prov = QComboBox()
        self.cmb_prov.addItems(ISP_PROVINCES)
        self.cmb_prov.setCurrentIndex(0)     # 默认黑龙江
        self.cmb_prov.currentTextChanged.connect(self._load_province)
        ph.addWidget(self.cmb_prov)
        lbl = QLabel("运营商 DNS 为省内节点，实际以宽带自动下发为准，可换用公共 DNS 对照")
        lbl.setStyleSheet("color:#86868b;")
        ph.addWidget(lbl, 1)
        wrap = QWidget()
        wv = QVBoxLayout(wrap)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(6)
        wv.addWidget(prov_bar)
        wv.addWidget(self.panel_isp, 1)
        self.tabs.addTab(wrap, "运营商 DNS（分省）")
        v.addWidget(self.tabs, 1)
        self._load_province("黑龙江")

        # ---- 应用到网卡 ----
        gb2 = QGroupBox("应用到网卡（对当前标签页选中的行生效）")
        f = QHBoxLayout(gb2)
        f.addWidget(QLabel("目标网卡:"))
        self.cmb_iface = QComboBox()
        self.cmb_iface.setMinimumWidth(240)
        f.addWidget(self.cmb_iface, 1)
        btn_reload = QPushButton("刷新")
        btn_reload.clicked.connect(self.reload_ifaces)
        f.addWidget(btn_reload)
        self.btn_apply = QPushButton("设为 DNS")
        self.btn_apply.setObjectName("primaryBtn")
        self.btn_apply.clicked.connect(self._apply)
        f.addWidget(self.btn_apply)
        self.btn_clear = QPushButton("恢复自动获取")
        self.btn_clear.setToolTip("清除手动 DNS，交回 DHCP 下发")
        self.btn_clear.clicked.connect(self._clear_dns)
        f.addWidget(self.btn_clear)
        v.addWidget(gb2)

        self.reload_ifaces()

    # ---- 运营商页 ----
    def _load_province(self, province):
        self.panel_isp.providers = isp_providers(province)
        self.panel_isp._populate(
            f"{province} 三大运营商 DNS（公开资料整理，实际以宽带下发为准）")

    # ---- 网卡 ----
    def reload_ifaces(self):
        def job():
            return sort_interfaces(self.backend.list_interfaces()) or []
        w = Worker(job)
        w.ok.connect(self._set_ifaces)
        w.err.connect(lambda m: self.log(f"刷新网卡失败: {m}", "WARN"))
        w.start()
        self._workers.append(w)

    def _set_ifaces(self, ifaces):
        cur = self.cmb_iface.currentData()
        self.cmb_iface.clear()
        for i in ifaces:
            label = f"{i['service'] or i['port']}  ({i['device']})"
            if iface_is_external(i):
                label += "  [USB]"
            self.cmb_iface.addItem(label, i["service"] or i["port"])

    # ---- 测速 / 应用 ----
    def _current_panel(self) -> DnsListPanel:
        return self.panel_public if self.tabs.currentIndex() == 0 else self.panel_isp

    def _apply(self):
        panel = self._current_panel()
        prov = panel.selected()
        if not prov:
            QMessageBox.information(self, "提示", "请先在列表中选择一行 DNS（点击行）")
            return
        svc = self.cmb_iface.currentData()
        if not svc:
            QMessageBox.information(self, "提示", "请先选择目标网卡")
            return
        name, primary, secondary, _ = prov
        dns_list = [primary] + ([secondary] if secondary else [])
        self.log(f"设置 DNS: {svc} -> {', '.join(dns_list)}")

        def job():
            self.backend.set_dns(svc, dns_list)
            return True

        w = Worker(job)
        w.ok.connect(lambda _: (
            self.log(f"DNS 已生效: {svc} -> {', '.join(dns_list)}"),
            QMessageBox.information(self, "完成",
                                    f"已将 {svc} 的 DNS 设为：\n{name}\n"
                                    f"{primary}" + (f"\n{secondary}" if secondary else ""))))
        w.err.connect(lambda m: (self.log(f"设置 DNS 失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "设置失败",
                                     f"{m}\n\n若弹出授权框请允许；或在托盘菜单开启免密授权。")))
        w.start()
        self._workers.append(w)

    def _clear_dns(self):
        svc = self.cmb_iface.currentData()
        if not svc:
            return
        ret = QMessageBox.question(self, "恢复自动获取",
                                   f"清除 {svc} 的手动 DNS，恢复为自动获取（DHCP 下发）？",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return

        def job():
            self.backend.set_dns(svc, [])
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self.log(f"已清除手动 DNS: {svc}（恢复自动获取）"))
        w.err.connect(lambda m: (self.log(f"清除 DNS 失败: {m}", "ERROR"),
                                 QMessageBox.warning(self, "操作失败", m)))
        w.start()
        self._workers.append(w)

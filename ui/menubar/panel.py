"""Network Control 弹出面板：菜单栏网络控制中心

结构：头部（标题 + 总体状态胶囊 + 设置）/ 滚动区（网卡卡片 + DHCP 行 + IP 方案）
     / 方案确认条 / 底部工具栏（主窗口 · DNS 测速 · DHCP · 设置 · 退出）

关键实现
- 定位：优先用 QSystemTrayIcon.geometry() 锚定菜单栏图标，无效时回退鼠标位置
- 网卡：按 service|device 稳定标识做增量同步，不销毁重建 → 展开态与滚动位置保留
- 状态：见 ui/menubar/status.py，只描述接口/地址事实，不臆测互联网连通性
"""
import datetime
import ipaddress
import time

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from core import applog
from .. import icons
from . import material
from .status import GROUP_TITLE, classify_iface, overall, summary
from .widgets import (AdapterCard, ElidedLabel, PresetChip, SectionLabel,
                      StatusPill)

PANEL_WIDTH = 380
PANEL_MIN_H = 236
PANEL_RADIUS = 13
MENUBAR_GAP = 6          # 面板顶部与菜单栏图标底部间距
EDGE_MARGIN = 8


# ============================ QSS ============================
def panel_qss(dark: bool) -> str:
    t = {
        "text": "#1D1D1F" if not dark else "#F5F5F7",
        "text2": "#86868B" if not dark else "#98989D",
        "text3": "#AEAEB2" if not dark else "#6E6E73",
        "surface": "#FFFFFF" if not dark else "#2C2C2E",
        "surface2": "#F2F2F4" if not dark else "#323234",
        "hover": "#E9E9EE" if not dark else "#3A3A3C",
        "hover_soft": "rgba(0,0,0,10)" if not dark else "rgba(255,255,255,14)",
        "sep": "#D2D2D7" if not dark else "#3A3A3C",
        "sep_soft": "#E8E8ED" if not dark else "#333335",
        # 卡片描边降到很轻：靠间距与底色分层，不再画一圈重线
        "card_border": "rgba(0,0,0,18)" if not dark else "rgba(255,255,255,22)",
        "accent": "#007AFF" if not dark else "#0A84FF",
        "accent_soft": "#EAF3FF" if not dark else "#12304F",
        "ok": "#1F9254" if not dark else "#32D74B",
        "warn": "#B26A00" if not dark else "#FFD60A",
        "err": "#D93A30" if not dark else "#FF453A",
        "warn_soft": "#FFF6E5" if not dark else "#3A2F10",
    }
    return f"""
#ncPanel, #ncPanel QWidget {{ color: {t['text']}; font-size: 13px; }}
#ncPanel QLabel {{ background: transparent; }}
#ncTitle {{ font-size: 15px; font-weight: 700; letter-spacing: -0.2px; }}
#ncSub {{ font-size: 11px; color: {t['text2']}; }}
#ncPanel QPushButton {{ font-size: 12px; }}
#logo {{ background: {t['accent']}; border-radius: 8px; }}

#pill {{ background: {t['surface2']}; border-radius: 9px; }}
#pillDot {{ font-size: 8px; color: {t['text3']}; }}
#pillText {{ font-size: 11px; font-weight: 600; color: {t['text2']}; }}
#pill[kind="ok"] #pillDot, #pill[kind="ok"] #pillText {{ color: {t['ok']}; }}
#pill[kind="warn"] #pillDot, #pill[kind="warn"] #pillText {{ color: {t['warn']}; }}
#pill[kind="err"] #pillDot, #pill[kind="err"] #pillText {{ color: {t['err']}; }}
#pill[kind="info"] #pillDot, #pill[kind="info"] #pillText {{ color: {t['accent']}; }}

#iconBtn {{ background: transparent; border: none; border-radius: 7px; padding: 4px; }}
#iconBtn:hover {{ background: {t['hover']}; }}

#panelSection {{
    font-size: 11px; font-weight: 600; color: {t['text2']}; letter-spacing: 0.4px;
}}
#sectionCount {{ font-size: 11px; color: {t['text3']}; font-weight: 500; }}

#staleBar {{ background: {t['warn_soft']}; border-radius: 8px; }}
#staleText {{ font-size: 11.5px; color: {t['warn']}; font-weight: 500; }}

#adapterCard {{
    background: {t['surface']}; border: 1px solid {t['card_border']};
    border-radius: 9px;
}}
#adapterHead {{ background: transparent; border-radius: 9px; }}
#adapterHead:hover {{ background: {t['hover_soft']}; }}
#adapterName {{ font-size: 12.5px; font-weight: 600; }}
#adapterSub {{ font-size: 10.5px; color: {t['text2']}; }}
#adapterIp {{
    font-family: "SF Mono", Menlo, monospace; font-size: 12px; font-weight: 600;
}}
#adapterIp[empty="true"] {{ color: {t['text3']}; font-size: 11px; font-weight: 400; }}
#adapterMeta {{ font-size: 10px; color: {t['text2']}; }}

#adapterDetail {{ background: transparent; }}
#copyField {{ background: transparent; border-radius: 6px; }}
#copyField:hover {{ background: {t['surface2']}; }}
#fieldLabel {{ font-size: 11px; color: {t['text2']}; }}
#fieldValue {{ font-family: "SF Mono", Menlo, monospace; font-size: 11.5px; }}
#fieldValue[empty="true"] {{ color: {t['text3']}; }}
#fieldEmpty {{ font-size: 11px; color: {t['text3']}; padding: 2px 2px; }}

#dhcpRow {{ background: {t['surface2']}; border-radius: 8px; }}
#dhcpText {{ font-size: 11.5px; color: {t['text2']}; }}
#dhcpGo {{ font-size: 11px; color: {t['accent']}; }}

#emptyHint {{ font-size: 11.5px; color: {t['text3']}; }}

#presetChip {{
    background: {t['surface']}; border: 1px solid {t['card_border']}; border-radius: 9px;
}}
#presetChip:hover {{ border-color: {t['accent']}; background: {t['surface2']}; }}
#presetChip[applied="true"] {{ border: 1px solid {t['accent']}; background: {t['accent_soft']}; }}
#chipName {{ font-size: 12px; font-weight: 600; }}
#chipSub {{ font-size: 10.5px; color: {t['text2']}; }}
#chipBadge {{
    font-size: 9.5px; font-weight: 600; color: {t['accent']};
    background: rgba(0,122,255,0.12); border-radius: 4px; padding: 1px 4px;
}}

#confirmBar {{ background: {t['surface2']}; border-radius: 9px; }}
#confirmName {{ font-size: 12px; font-weight: 600; }}
#confirmMeta {{ font-size: 10.5px; color: {t['text2']}; }}
#confirmAddr {{ font-family: "SF Mono", Menlo, monospace; font-size: 10.5px;
                color: {t['text']}; }}
#confirmMsg {{ font-size: 11px; color: {t['warn']}; }}
#ghostBtn {{
    background: transparent; border: none; border-radius: 6px;
    color: {t['text2']}; padding: 4px 10px;
}}
#ghostBtn:hover {{ background: {t['hover']}; color: {t['text']}; }}
#ghostBtn:disabled {{ color: {t['text3']}; }}
#primaryBtn {{
    background: {t['accent']}; color: #FFFFFF; border: none; border-radius: 6px;
    padding: 4px 12px; font-weight: 600;
}}
#primaryBtn:disabled {{ background: {t['sep']}; color: {t['text3']}; }}

#footer {{ border-top: 1px solid {t['sep_soft']}; }}
#footerBtn {{
    background: transparent; border: none; border-radius: 7px;
    color: {t['text2']}; padding: 4px 5px;
}}
#footerBtn:hover {{ background: {t['hover']}; color: {t['text']}; }}
#footerBtn:disabled {{ color: {t['text3']}; }}

#toastLabel {{
    background: rgba(0,0,0,0.78); color: #FFFFFF; border-radius: 8px;
    font-size: 11.5px; padding: 6px 12px;
}}
"""


# ============================ 面板 ============================
class Panel(QWidget):
    open_main = Signal()
    open_settings = Signal()
    open_dns = Signal()
    open_dhcp = Signal()
    open_iface = Signal(str)              # 在主窗口里定位到某个网卡
    apply_preset_requested = Signal(dict)
    quit_requested = Signal()

    def __init__(self, state, popup: bool = True):
        # popup=False 仅用于自动化截图：后台进程的 Qt.Popup 会被 macOS 立即
        # 收回，无法成像；Qt.Tool 窗口渲染路径完全一致（同一控件同一 QSS）。
        flags = (Qt.Popup | Qt.FramelessWindowHint) if popup else \
                (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        super().__init__(None, flags)
        self.setObjectName("ncPanel")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(PANEL_WIDTH)
        self.state = state
        self._dark = False
        self._style_dark = None
        self._cards_dark = False
        self._expanded = set()             # 保持展开的网卡 key（service|device）
        self._cards = {}                   # key → AdapterCard
        self._labels = []                  # 分组标题控件
        self._seq = None                   # 当前布局顺序签名
        self._presets_sig = None
        self._chips = []
        self._confirm_preset = None
        self._applying = False
        self._anchor = None
        self._anchor_rect = None
        self._last_hide_ts = 0.0
        self._footer_compact = False
        self._footer_items = []

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 11, 12, 9)
        self._root.setSpacing(8)

        self._build_head()
        self._build_stale()
        self._build_scroll()
        self._build_confirm()
        self._build_footer()
        self._build_toast()

        self._spinner_angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(70)
        self._spinner_timer.timeout.connect(self._spin)

        self._apply_theme(False)

    # ---------------------------------------------------------- 构建
    def _logo_pix(self) -> QPixmap:
        """蓝色圆角底 + 白色节点图标（QSS 背景 QLabel 不生效，直接绘制）"""
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

        dpr = self.devicePixelRatioF() or 2.0
        size = 30
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, size - 1, size - 1, 8, 8)
        p.fillPath(path, QColor("#007AFF" if not self._dark else "#0A84FF"))
        icon = icons.pixmap("nodes", "#FFFFFF", 16)
        icon.setDevicePixelRatio(dpr)
        w = icon.width() / dpr
        h = icon.height() / dpr
        p.drawPixmap(QPointF((size - w) / 2, (size - h) / 2), icon)
        p.end()
        pm.setDevicePixelRatio(dpr)
        return pm

    def _build_head(self):
        self._head_w = QWidget()
        head = QHBoxLayout(self._head_w)
        head.setContentsMargins(1, 0, 1, 0)
        head.setSpacing(9)

        self.logo = QLabel()
        self.logo.setPixmap(self._logo_pix())
        self.logo.setFixedSize(30, 30)
        self.logo.setAlignment(Qt.AlignCenter)
        head.addWidget(self.logo)

        box = QVBoxLayout()
        box.setSpacing(0)
        t1 = QLabel("Network Control")
        t1.setObjectName("ncTitle")
        box.addWidget(t1)
        self.lbl_sub = ElidedLabel("正在读取网络状态…", mode=Qt.ElideRight)
        self.lbl_sub.setObjectName("ncSub")
        box.addWidget(self.lbl_sub)
        head.addLayout(box)
        head.addStretch(1)

        self.pill = StatusPill()
        head.addWidget(self.pill, 0, Qt.AlignVCenter)

        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("iconBtn")
        self.btn_settings.setIcon(icons.icon("settings", "#86868B", 15))
        self.btn_settings.setFixedSize(26, 26)
        self.btn_settings.setToolTip("打开设置")
        self.btn_settings.clicked.connect(self.open_settings)
        head.addWidget(self.btn_settings, 0, Qt.AlignVCenter)
        self._root.addWidget(self._head_w)

    def _build_stale(self):
        self.stale_bar = QFrame()
        self.stale_bar.setObjectName("staleBar")
        sh = QHBoxLayout(self.stale_bar)
        sh.setContentsMargins(10, 5, 10, 5)
        self.stale_text = QLabel("")
        self.stale_text.setObjectName("staleText")
        self.stale_text.setWordWrap(True)
        sh.addWidget(self.stale_text)
        self.stale_bar.hide()
        self._root.addWidget(self.stale_bar)

    def _build_scroll(self):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QWidget#scrollBody{background:transparent;}")
        body = QWidget()
        body.setObjectName("scrollBody")
        self.body_v = QVBoxLayout(body)
        self.body_v.setContentsMargins(0, 0, 0, 0)
        self.body_v.setSpacing(7)
        self.scroll.setWidget(body)
        self._root.addWidget(self.scroll, 1)

        # 网卡分组标题
        sec = QHBoxLayout()
        sec.setContentsMargins(1, 0, 1, 0)
        sec.setSpacing(6)
        self.lbl_adapters = SectionLabel("网卡")
        sec.addWidget(self.lbl_adapters)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("sectionCount")
        sec.addWidget(self.lbl_count)
        sec.addStretch(1)
        self.spinner = QLabel()
        self.spinner.setFixedSize(14, 14)
        self.spinner.hide()
        sec.addWidget(self.spinner)
        self.body_v.addLayout(sec)

        self.adapters_box = QVBoxLayout()
        self.adapters_box.setSpacing(5)
        self.body_v.addLayout(self.adapters_box)

        self.empty_adapters = QLabel("未检测到网络服务")
        self.empty_adapters.setObjectName("emptyHint")
        self.empty_adapters.setAlignment(Qt.AlignCenter)
        self.empty_adapters.hide()
        self.body_v.addWidget(self.empty_adapters)

        # DHCP 行
        self.dhcp_row = QFrame()
        self.dhcp_row.setObjectName("dhcpRow")
        self.dhcp_row.setCursor(Qt.PointingHandCursor)
        self.dhcp_row.setToolTip("打开 DHCP 服务页")
        dh = QHBoxLayout(self.dhcp_row)
        dh.setContentsMargins(10, 6, 10, 6)
        dh.setSpacing(8)
        self.dhcp_icon = QLabel()
        self.dhcp_icon.setFixedSize(14, 14)
        dh.addWidget(self.dhcp_icon)
        self.dhcp_text = ElidedLabel("DHCP 服务：—", mode=Qt.ElideRight)
        self.dhcp_text.setObjectName("dhcpText")
        dh.addWidget(self.dhcp_text, 1)
        dhcp_go = QLabel("打开 ›")
        dhcp_go.setObjectName("dhcpGo")
        dh.addWidget(dhcp_go)
        self.dhcp_row.mouseReleaseEvent = lambda e: self.open_dhcp.emit()
        self.body_v.addWidget(self.dhcp_row)

        # 方案
        self.lbl_presets = SectionLabel("IP 方案")
        self.body_v.addWidget(self.lbl_presets)

        self.presets_grid_box = QWidget()
        self.presets_grid = QGridLayout(self.presets_grid_box)
        self.presets_grid.setContentsMargins(0, 0, 0, 0)
        self.presets_grid.setHorizontalSpacing(5)
        self.presets_grid.setVerticalSpacing(5)
        self.body_v.addWidget(self.presets_grid_box)

        self.empty_presets = QLabel("暂无方案记录\n在主窗口「网卡管理」中保存后，可在这里一键切换")
        self.empty_presets.setObjectName("emptyHint")
        self.empty_presets.setAlignment(Qt.AlignCenter)
        self.empty_presets.setStyleSheet("padding: 8px 0;")
        self.body_v.addWidget(self.empty_presets)

    def _build_confirm(self):
        self.confirm_bar = QFrame()
        self.confirm_bar.setObjectName("confirmBar")
        v = QVBoxLayout(self.confirm_bar)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(3)

        self.confirm_name = QLabel("")
        self.confirm_name.setObjectName("confirmName")
        v.addWidget(self.confirm_name)

        self.confirm_meta = ElidedLabel("")
        self.confirm_meta.setObjectName("confirmMeta")
        v.addWidget(self.confirm_meta)

        self.confirm_addr = QLabel("")
        self.confirm_addr.setObjectName("confirmAddr")
        self.confirm_addr.setWordWrap(True)
        v.addWidget(self.confirm_addr)

        self.confirm_msg = QLabel("")
        self.confirm_msg.setObjectName("confirmMsg")
        self.confirm_msg.setWordWrap(True)
        self.confirm_msg.hide()
        v.addWidget(self.confirm_msg)

        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(6)
        row.addStretch(1)
        self.btn_no = QPushButton("取消")
        self.btn_no.setObjectName("ghostBtn")
        self.btn_no.setCursor(Qt.PointingHandCursor)
        self.btn_no.clicked.connect(self._cancel_confirm)
        row.addWidget(self.btn_no)
        self.btn_yes = QPushButton("应用配置")
        self.btn_yes.setObjectName("primaryBtn")
        self.btn_yes.setCursor(Qt.PointingHandCursor)
        self.btn_yes.clicked.connect(self._do_confirm)
        row.addWidget(self.btn_yes)
        v.addLayout(row)

        self.confirm_bar.hide()
        self._root.addWidget(self.confirm_bar)

    def _build_footer(self):
        self._footer_w = QFrame()
        self._footer_w.setObjectName("footer")
        fh = QHBoxLayout(self._footer_w)
        fh.setContentsMargins(2, 7, 2, 0)
        fh.setSpacing(1)

        self._footer_btn(fh, "window", "主窗口", self.open_main)
        self._footer_btn(fh, "dns", "DNS 测速", self.open_dns)
        self._footer_btn(fh, "dhcp", "DHCP", self.open_dhcp)
        fh.addStretch(1)
        self._footer_btn(fh, "settings", "设置", self.open_settings)
        self._footer_btn(fh, "x", "退出", self.quit_requested)
        self._root.addWidget(self._footer_w)

    def _build_toast(self):
        self.toast = QLabel(self)
        self.toast.setObjectName("toastLabel")
        self.toast.setWordWrap(True)
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)

    def _footer_btn(self, layout, icon_key, text, sig):
        btn = QPushButton()
        btn.setObjectName("footerBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("iconKey", icon_key)
        btn.setIcon(icons.icon(icon_key, "#8E8E93", 14))
        btn.setIconSize(QSize(14, 14))
        btn.setText(text)
        btn.setToolTip(text)
        btn.setAccessibleName(text)
        btn.clicked.connect(sig.emit)
        layout.addWidget(btn)
        self._footer_items.append((btn, text))
        return btn

    # ---------------------------------------------------------- 主题
    def _apply_theme(self, dark: bool):
        self._dark = dark
        if self._style_dark != dark:
            self._style_dark = dark
            self.setStyleSheet(panel_qss(dark))
            for btn, _ in self._footer_items:
                key = btn.property("iconKey")
                if key:
                    btn.setIcon(icons.icon(key, "#8E8E93", 14))
        if self._cards_dark != dark:
            self._cards_dark = dark
            self.logo.setPixmap(self._logo_pix())
            for c in self._cards.values():
                c._dark = dark
                c._render_head()
                c._set_chevron(c.expanded)
        self.update()

    # ---------------------------------------------------------- 轻提示
    def show_toast(self, text: str, kind: str = "ok"):
        self.toast.setText(text)
        self.toast.setFixedWidth(min(PANEL_WIDTH - 56, max(180, self.toast.sizeHint().width())))
        self.toast.adjustSize()
        self.toast.move(max(8, (self.width() - self.toast.width()) // 2),
                        max(12, self.height() - self.toast.height() - 52))
        self.toast.show()
        self.toast.raise_()
        self._toast_timer.start(2000)

    def _hide_toast(self):
        self.toast.hide()

    # ---------------------------------------------------------- 复制
    def _copy_feedback(self, label: str, value: str):
        ok = False
        try:
            cb = QApplication.clipboard()
            cb.setText(value)
            ok = cb.text() == value
        except Exception as exc:
            applog.exception("Panel 复制", exc)
        if not ok:
            applog.warn(f"复制失败：{label}")
            self.show_toast("复制失败：剪贴板不可用", "err")
            return
        short = value if len(value) <= 26 else value[:24] + "…"
        self.show_toast(f"已复制 {label}：{short}")

    def copy_summary(self, svc: str):
        snap = self.state.snapshot()
        ifc = next((i for i in snap.get("ifaces") or []
                    if (i.get("service") or i.get("device")) == svc), None)
        if not ifc:
            self.show_toast("复制失败：网卡已不存在", "err")
            return
        d = (snap.get("detail") or {}).get(svc, {})
        status = {"up": "已连接", "down": "未连接", "absent": "未插入",
                  "disabled": "已禁用"}.get(classify_iface(ifc), "未知")
        mask = ifc.get("mask") or ""
        try:
            plen = f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}', strict=False).prefixlen}"
        except Exception:
            plen = ""
        aliases = d.get("aliases") or []
        mode = {"static": "手动配置", "dhcp": "DHCP 自动"}.get(d.get("mode"), "未知")
        lines = [
            f"【{ifc.get('service') or svc}】({ifc.get('device') or svc}) {status}",
            f"主 IP:     {(ifc.get('ipv4') or '—')}{plen if ifc.get('ipv4') else ''}",
            f"子网掩码:  {mask or '—'}",
            f"默认网关:  {ifc.get('router') or '—'}",
            f"DNS:       {', '.join(d.get('dns') or []) or '自动获取'}",
            f"MAC 地址:  {ifc.get('mac') or '—'}",
            f"配置方式:  {mode}",
        ]
        if aliases:
            lines.append("附加 IP:   " + ", ".join(aliases))
        if d.get("ipv6"):
            lines.append("IPv6:      " + "  ".join(d["ipv6"]))
        if d.get("link"):
            lines.append("链路速率:  " + d["link"])
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"采集时间:   {stamp}" + ("（数据已过期）" if snap.get("stale") else ""))
        try:
            QApplication.clipboard().setText("\n".join(lines))
            self.show_toast("已复制网卡配置摘要")
        except Exception as exc:
            applog.exception("Panel 复制摘要", exc)
            self.show_toast("复制失败：剪贴板不可用", "err")

    # ---------------------------------------------------------- 状态驱动
    def update_state(self, snap: dict):
        snap = snap or {}
        ifaces = snap.get("ifaces") or []
        detail = snap.get("detail") or {}

        self.lbl_sub.setRawText(summary(snap))

        if snap.get("refreshing"):
            self.spinner.show()
            if not self._spinner_timer.isActive():
                self._spinner_timer.start()
        else:
            self.spinner.hide()
            self._spinner_timer.stop()

        text, kind = overall(snap)
        self.pill.set_kind(kind, text)

        # 过期横幅
        if snap.get("stale"):
            ts = (datetime.datetime.fromtimestamp(snap["ts"]).strftime("%H:%M")
                  if snap.get("ts") else "—")
            reason = (snap.get("error") or "刷新失败").strip()
            self.stale_text.setText(f"数据已过期 · 上次成功 {ts} · {reason}")
            if not self.stale_bar.isVisible():
                self.stale_bar.show()
                self._relayout_soon()
        elif self.stale_bar.isVisible():
            self.stale_bar.hide()
            self._relayout_soon()

        # DHCP
        running = bool(snap.get("dhcp_running"))
        st = snap.get("dhcp_state") or {}
        extra = ""
        if running:
            cfg = st.get("config") or {}
            leases = st.get("leases") or {}
            if cfg.get("start"):
                extra = f" · {cfg.get('start')}~{cfg.get('end')}"
            if leases:
                extra += f" · 租约 {len(leases)}"
        self.dhcp_text.setRawText(
            f"DHCP 服务：{'运行中' if running else '未运行'}{extra}")
        self.dhcp_icon.setPixmap(icons.pixmap(
            "dhcp", "#1F9254" if running else "#8E8E93", 14))

        self.lbl_count.setText(str(len(ifaces)))
        self._sync_adapters(ifaces, detail)
        self._sync_presets(snap.get("presets") or [], ifaces, detail)
        self._relayout_soon()

    # ---------------------------------------------------------- 网卡列表（增量）
    def _sync_adapters(self, ifaces, detail):
        by_key = {}
        for i in ifaces:
            by_key[f"{i.get('service') or ''}|{i.get('device') or ''}"] = i

        groups = {k: [] for k in GROUP_TITLE}
        for i in ifaces:
            groups[classify_iface(i)].append(i)
        present = [k for k in ("up", "down", "absent", "disabled", "unknown")
                   if groups.get(k)]

        desired = []
        for gkey in ("up", "down", "absent", "disabled", "unknown"):
            rows = groups.get(gkey) or []
            if not rows:
                continue
            if len(present) > 1:
                desired.append(("label", GROUP_TITLE[gkey]))
            for i in rows:
                desired.append(("card", f"{i.get('service') or ''}|{i.get('device') or ''}"))

        # 内容更新（原地，不重建）
        for key, ifc in by_key.items():
            d = detail.get(ifc.get("service") or ifc.get("device") or "") or {}
            card = self._cards.get(key)
            if card is None:
                card = AdapterCard(ifc, d, self._dark)
                card.copy_requested.connect(self.copy_summary)
                card.copy_value.connect(self._copy_feedback)
                card.open_in_main.connect(self.open_iface)
                self._cards[key] = card
                if key in self._expanded:
                    card.set_expanded(True, animate=False)
            else:
                card.update_data(ifc, d)

        # 结构变化才动布局（顺序 / 分组）
        seq = tuple(desired)
        if seq != self._seq:
            self._seq = seq
            self._relayout_adapters(desired)

        # 消失的网卡
        for key in [k for k in self._cards if k not in by_key]:
            card = self._cards.pop(key)
            self._expanded.discard(key)
            card.setParent(None)
            card.deleteLater()

        self.empty_adapters.setVisible(not ifaces)

    def _relayout_adapters(self, desired):
        while self.adapters_box.count():
            self.adapters_box.takeAt(0)
        for lb in self._labels:
            lb.setParent(None)
            lb.deleteLater()
        self._labels = []
        for item in desired:
            if item[0] == "label":
                lb = SectionLabel(item[1])
                lb.setStyleSheet("padding-left:2px;")
                self._labels.append(lb)
                self.adapters_box.addWidget(lb)
            else:
                card = self._cards.get(item[1])
                if card is not None:
                    self.adapters_box.addWidget(card)
                    card.show()

    # ---------------------------------------------------------- 方案
    @staticmethod
    def _applied_presets(presets, ifaces, detail):
        result = set()
        by_svc = {(i.get("service") or i.get("device")): i for i in ifaces}
        for idx, p in enumerate(presets):
            svc = p.get("service")
            ifc = by_svc.get(svc)
            if not ifc:
                continue
            d = detail.get(svc, {})
            if p.get("mode") == "static":
                ok = (ifc.get("ipv4") == p.get("ip")
                      and (ifc.get("mask") or "") == (p.get("mask") or ""))
            else:
                ok = d.get("mode") == "dhcp"
            if ok and p.get("dns"):
                ok = list(d.get("dns") or []) == list(p["dns"])
            if ok:
                result.add(idx)
        return result

    def _sync_presets(self, presets, ifaces, detail):
        applied = self._applied_presets(presets, ifaces, detail)
        sig = tuple((p.get("name"), p.get("service"), p.get("mode"), p.get("ip"),
                     p.get("mask"), p.get("router"), tuple(p.get("dns") or ()))
                    for p in presets)
        if sig != self._presets_sig:
            self._presets_sig = sig
            while self.presets_grid.count():
                item = self.presets_grid.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
            self._chips = []
            for idx, p in enumerate(presets):
                chip = PresetChip(p, idx in applied)
                chip.clicked.connect(self._preset_clicked)
                self.presets_grid.addWidget(chip, idx // 2, idx % 2)
                self._chips.append(chip)
        else:
            for idx, chip in enumerate(self._chips):
                chip.set_applied(idx in applied)
        self.presets_grid_box.setVisible(bool(presets))
        self.empty_presets.setVisible(not presets)

    def _preset_clicked(self, chip: PresetChip):
        if self._applying:
            return
        self._confirm_preset = chip.preset
        self._fill_confirm(chip.preset)
        self.confirm_bar.show()
        self._relayout_soon()

    def _fill_confirm(self, p: dict):
        svc = p.get("service") or "—"
        static = p.get("mode") == "static"
        mode = "手动 IP" if static else "自动 DHCP"
        self.confirm_name.setText(f"应用方案「{p.get('name') or '未命名'}」")
        self.confirm_meta.setRawText(f"{svc} · {mode}")
        parts = []
        if static:
            ip = p.get("ip") or ""
            plen = ""
            try:
                if p.get("mask"):
                    plen = ("/" + str(ipaddress.IPv4Network(
                        f"0.0.0.0/{p['mask']}", strict=False).prefixlen))
            except Exception:
                plen = ""
            parts.append(f"{(ip or '—')}{plen}")
            if p.get("router"):
                parts.append(f"网关 {p['router']}")
        if p.get("dns"):
            parts.append("DNS " + ", ".join(p["dns"]))
        self.confirm_addr.setText(" · ".join(parts) if parts else "自动获取地址与 DNS")
        self.confirm_msg.hide()
        self.confirm_msg.setText("")
        self.btn_yes.setText("应用配置")
        self.btn_yes.setEnabled(True)
        self.btn_no.setEnabled(True)

    def _cancel_confirm(self):
        if self._applying:
            return
        self._confirm_preset = None
        self.confirm_bar.hide()
        self._relayout_soon()

    def _do_confirm(self):
        p = self._confirm_preset
        if not p or self._applying:
            return
        self._applying = True
        self.btn_yes.setEnabled(False)
        self.btn_no.setEnabled(False)
        self.btn_yes.setText("应用中…")
        self.confirm_msg.setText("正在下发配置，完成后会自动核对实际状态…")
        self.confirm_msg.show()
        self._relayout_soon()
        self.apply_preset_requested.emit(dict(p))

    def preset_apply_end(self, ok: bool, msg: str, kind: str = "ok"):
        """由主窗口回调：配置下发 / 校验结束（ok=False 时保留确认条显示原因）"""
        self._applying = False
        self.btn_yes.setEnabled(True)
        self.btn_no.setEnabled(True)
        self.btn_yes.setText("应用配置")
        if ok:
            self._confirm_preset = None
            self.confirm_bar.hide()
        else:
            self.confirm_msg.setText(msg)
            self.confirm_msg.show()
        self.show_toast(msg, kind)
        self._relayout_soon()

    # ---------------------------------------------------------- 尺寸 / 定位
    def _relayout_soon(self):
        QTimer.singleShot(0, self._relayout)

    def _screen(self):
        rect = self._anchor_rect
        if rect is not None and rect.isValid() and rect.width() > 0:
            scr = QApplication.screenAt(rect.center())
            if scr is not None:
                return scr
        if self._anchor is not None:
            scr = QApplication.screenAt(self._anchor)
            if scr is not None:
                return scr
        return QApplication.primaryScreen()

    def _chrome_height(self) -> int:
        m = self._root.contentsMargins()
        h = m.top() + m.bottom()
        h += self._head_w.sizeHint().height()
        h += self._footer_w.sizeHint().height()
        h += self._root.spacing() * 2
        if self.stale_bar.isVisible():
            h += self.stale_bar.sizeHint().height() + self._root.spacing()
        if self.confirm_bar.isVisible():
            h += self.confirm_bar.sizeHint().height() + self._root.spacing()
        return h

    def _relayout(self):
        body = self.scroll.widget()
        if body is None:
            return
        body.adjustSize()
        scr = self._screen()
        avail = scr.availableGeometry() if scr else QRect(0, 0, 1440, 900)
        chrome = self._chrome_height()
        max_h = min(int(avail.height() * 0.80), avail.height() - 20)
        want = chrome + body.sizeHint().height() + 4
        h = max(PANEL_MIN_H, min(want, max_h))
        self.scroll.setFixedHeight(max(110, h - chrome))
        if h != self.height() or self.width() != PANEL_WIDTH:
            self.resize(PANEL_WIDTH, h)
        self._fit_footer()
        self._place()

    def _fit_footer(self):
        """宽度不足时退化为纯图标 + tooltip，避免底部拥挤

        macOS 原生按钮 sizeHint 虚高（内边距估算过大），直接用会导致
        380px 下误判拥挤；这里按字体实测宽度估算。
        """
        avail = self.width() - 24
        fm = self._footer_items[0][0].fontMetrics()
        need = 8 + sum(fm.horizontalAdvance(t) + 14 + 4 + 12
                       for _, t in self._footer_items)
        compact = need > avail
        if compact == self._footer_compact:
            return
        self._footer_compact = compact
        for btn, text in self._footer_items:
            if compact:
                btn.setText("")
                btn.setFixedWidth(34)
            else:
                btn.setText(text)
                btn.setMinimumWidth(0)
                btn.setMaximumWidth(16777215)

    def _place(self):
        scr = self._screen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        rect = self._anchor_rect
        w, h = self.width(), self.height()

        if rect is not None and rect.isValid() and rect.width() > 0 and rect.height() > 0:
            cx = rect.center().x()
            top = max(rect.bottom() + MENUBAR_GAP, avail.top() + 4)
        else:
            pos = self._anchor
            if pos is None:
                from PySide6.QtGui import QCursor
                pos = QCursor.pos()
            cx = pos.x()
            top = avail.top() + MENUBAR_GAP

        x = cx - w // 2
        x = max(avail.left() + EDGE_MARGIN, min(x, avail.right() - w - EDGE_MARGIN + 1))
        y = top
        bottom_limit = avail.bottom() - 4
        if y + h > bottom_limit:
            y = max(avail.top() + 4, bottom_limit - h)
        self.move(x, y)

    def _spin(self):
        from PySide6.QtGui import QTransform
        self._spinner_angle = (self._spinner_angle + 30) % 360
        pm = icons.pixmap("refresh", "#8E8E93", 13)
        self.spinner.setPixmap(
            pm.transformed(QTransform().rotate(self._spinner_angle), Qt.SmoothTransformation))

    # ---------------------------------------------------------- 显示 / 关闭
    def show_at(self, cursor_pos=None, anchor_rect=None):
        self._anchor = cursor_pos
        self._anchor_rect = anchor_rect
        self._apply_theme(_panel_dark())
        self.update_state(self.state.snapshot())
        self._relayout()
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
        # 打开时若数据偏旧就补一次采集（复用同一个采集循环，不新建轮询）
        try:
            self.state.refresh_if_older(2.0)
        except Exception as exc:
            applog.exception("Panel 打开时刷新", exc)

    def hideEvent(self, e):
        self._last_hide_ts = time.time()
        self._applying = False
        self._confirm_preset = None
        self.confirm_bar.hide()
        self._expanded = {k for k, c in self._cards.items() if c.expanded}
        self._spinner_timer.stop()
        self._toast_timer.stop()
        self.toast.hide()
        super().hideEvent(e)

    def paintEvent(self, e):
        material.paint_panel_background(self, self._dark, PANEL_RADIUS)

    def toggle_at(self, cursor_pos=None, anchor_rect=None):
        if self.isVisible():
            self.close()
            return
        if time.time() - self._last_hide_ts < 0.35:
            return
        self.show_at(cursor_pos, anchor_rect)


def _panel_dark() -> bool:
    try:
        from .. import theme
        mgr = theme.current()
        return bool(mgr and mgr.dark)
    except Exception:
        return False

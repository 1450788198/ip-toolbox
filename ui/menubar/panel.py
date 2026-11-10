"""Network Control 弹出面板：菜单栏网络控制中心

Qt.Popup 无边框窗口 + 原生 NSVisualEffectView 材质（降级为自绘半透明底）。
布局：头部（标题+总体状态+设置）/ 滚动区（网卡分组列表 + IP 方案两列）/
底部工具栏（主窗口 / 网络诊断 / 设置 / 退出）。
"""
import datetime
import ipaddress

from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect,
                               QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from core import settings
from .. import icons
from . import material
from .widgets import (AdapterCard, CopyField, PresetChip, SectionLabel, StatusPill)

PANEL_WIDTH = 380
PANEL_MIN_H = 220
PANEL_RADIUS = 12


# ============================ QSS ============================
def panel_qss(dark: bool) -> str:
    t = {
        "text": "#1D1D1F" if not dark else "#F5F5F7",
        "text2": "#86868B" if not dark else "#98989D",
        "text3": "#AEAEB2" if not dark else "#6E6E73",
        "surface": "#FFFFFF" if not dark else "#2C2C2E",
        "surface2": "#F2F2F4" if not dark else "#323234",
        "hover": "#E9E9EE" if not dark else "#3A3A3C",
        "sep": "#D2D2D7" if not dark else "#3A3A3C",
        "sep_soft": "#E8E8ED" if not dark else "#333335",
        "accent": "#007AFF" if not dark else "#0A84FF",
        "accent_soft": "#E3F0FF" if not dark else "#0E3357",
        "ok": "#30A46C" if not dark else "#32D74B",
        "warn": "#C77700" if not dark else "#FFD60A",
        "err": "#D93A30" if not dark else "#FF453A",
        "warn_soft": "#FFF4E0" if not dark else "#3A2F10",
    }
    return f"""
#ncPanel, #ncPanel QWidget {{ color: {t['text']}; font-size: 13px; }}
#ncPanel QLabel {{ background: transparent; }}
#ncTitle {{ font-size: 15px; font-weight: 700; }}
#ncSub {{ font-size: 11px; color: {t['text2']}; }}
#ncPanel QPushButton {{ font-size: 12px; }}

#pill {{ background: {t['surface2']}; border-radius: 9px; }}
#pillDot {{ font-size: 8px; color: {t['text3']}; }}
#pillText {{ font-size: 11px; font-weight: 600; color: {t['text2']}; }}
#pill[kind="ok"] #pillDot {{ color: {t['ok']}; }}
#pill[kind="ok"] #pillText {{ color: {t['ok']}; }}
#pill[kind="warn"] #pillDot {{ color: {t['warn']}; }}
#pill[kind="warn"] #pillText {{ color: {t['warn']}; }}
#pill[kind="err"] #pillDot {{ color: {t['err']}; }}
#pill[kind="err"] #pillText {{ color: {t['err']}; }}
#pill[kind="info"] #pillDot {{ color: {t['accent']}; }}
#pill[kind="info"] #pillText {{ color: {t['accent']}; }}

#iconBtn {{
    background: transparent; border: none; border-radius: 7px; padding: 4px;
}}
#iconBtn:hover {{ background: {t['hover']}; }}

#panelSection {{
    font-size: 11px; font-weight: 600; color: {t['text2']}; letter-spacing: 0.4px;
}}
#staleBar, #confirmBar {{
    background: {t['warn_soft']}; border-radius: 8px;
}}
#staleText, #confirmText {{ font-size: 11.5px; color: {t['warn']}; font-weight: 500; }}

#adapterCard {{
    background: {t['surface']}; border: 1px solid {t['sep_soft']}; border-radius: 10px;
}}
#adapterHead {{ background: transparent; border-radius: 10px; }}
#adapterHead:hover {{ background: {t['surface2']}; }}
#adapterName {{ font-size: 13px; font-weight: 600; }}
#adapterSub {{ font-size: 11px; color: {t['text2']}; }}
#adapterIp {{
    font-family: "SF Mono", Menlo, monospace; font-size: 12px; font-weight: 600;
}}
#adapterMeta {{ font-size: 10px; color: {t['text2']}; }}

#adapterDetail {{ background: transparent; }}
#copyField {{ background: {t['surface2']}; border: none; border-radius: 6px; }}
#copyField:hover {{ background: {t['hover']}; }}
#fieldLabel {{ font-size: 11px; color: {t['text2']}; }}
#fieldValue {{ font-family: "SF Mono", Menlo, monospace; font-size: 11.5px; }}

#dhcpRow {{ background: {t['surface2']}; border-radius: 8px; }}
#dhcpText {{ font-size: 11.5px; color: {t['text2']}; }}

#presetChip {{
    background: {t['surface']}; border: 1px solid {t['sep']}; border-radius: 9px;
}}
#presetChip:hover {{ border-color: {t['text3']}; background: {t['surface2']}; }}
#presetChip[applied="true"] {{ border: 1.5px solid {t['accent']}; background: {t['accent_soft']}; }}
#chipName {{ font-size: 12px; font-weight: 600; }}
#chipSub {{ font-size: 10.5px; color: {t['text2']}; }}

#footer {{
    border-top: 1px solid {t['sep_soft']};
}}
#footerBtn {{
    background: transparent; border: none; border-radius: 7px;
    color: {t['text2']}; padding: 5px 10px;
}}
#footerBtn:hover {{ background: {t['hover']}; color: {t['text']}; }}
#footerBtn:disabled {{ color: {t['text3']}; }}

#toastLabel {{
    background: rgba(0,0,0,0.75); color: #FFFFFF; border-radius: 8px;
    font-size: 12px; padding: 6px 12px;
}}
"""


# ============================ 面板 ============================
class Panel(QWidget):
    open_main = Signal()
    open_settings = Signal()
    open_diagnostics = Signal()
    open_dhcp = Signal()
    apply_preset_requested = Signal(dict)
    quit_requested = Signal()

    def __init__(self, state):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("ncPanel")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(PANEL_WIDTH)
        self.state = state
        self._dark = False
        self._vibrancy = False
        self._expanded = set()          # 保持展开的网卡 key
        self._sig = None                # 上次网卡签名
        self._presets_sig = None
        self._confirm_preset = None
        self._last_hide_ts = 0.0

        self.setStyleSheet(panel_qss(False))

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)

        # ---- 头部 ----
        head = QHBoxLayout()
        head.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(self._logo_pix())
        logo.setFixedSize(30, 30)
        logo.setAlignment(Qt.AlignCenter)
        logo.setObjectName("logo")
        logo.setStyleSheet(
            "background:#007AFF; border-radius:8px;")
        head.addWidget(logo)
        box = QVBoxLayout()
        box.setSpacing(0)
        t1 = QLabel("Network Control")
        t1.setObjectName("ncTitle")
        box.addWidget(t1)
        t2 = QLabel("IP 工具箱 · 专业网络运维")
        t2.setObjectName("ncSub")
        box.addWidget(t2)
        head.addLayout(box)
        head.addStretch(1)
        self.pill = StatusPill()
        head.addWidget(self.pill)
        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("iconBtn")
        self.btn_settings.setIcon(icons.icon("settings", "#86868B", 15))
        self.btn_settings.setFixedSize(26, 26)
        self.btn_settings.setToolTip("打开设置")
        self.btn_settings.clicked.connect(self.open_settings)
        head.addWidget(self.btn_settings)
        root.addLayout(head)

        # ---- 过期横幅 ----
        self.stale_bar = QFrame()
        self.stale_bar.setObjectName("staleBar")
        sh = QHBoxLayout(self.stale_bar)
        sh.setContentsMargins(10, 5, 10, 5)
        self.stale_text = QLabel("")
        self.stale_text.setObjectName("staleText")
        sh.addWidget(self.stale_text)
        self.stale_bar.hide()
        root.addWidget(self.stale_bar)

        # ---- 滚动区 ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;} "
                                  "QWidget#scrollBody{background:transparent;}")
        body = QWidget()
        body.setObjectName("scrollBody")
        self.body_v = QVBoxLayout(body)
        self.body_v.setContentsMargins(0, 0, 0, 0)
        self.body_v.setSpacing(8)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        sec_adapter = QHBoxLayout()
        self.lbl_adapters = SectionLabel("网卡")
        sec_adapter.addWidget(self.lbl_adapters)
        sec_adapter.addStretch(1)
        self.spinner = QLabel()
        self.spinner.setStyleSheet("color:#86868B;")
        self.spinner.hide()
        sec_adapter.addWidget(self.spinner)
        self.body_v.addLayout(sec_adapter)

        self.adapters_box = QVBoxLayout()
        self.adapters_box.setSpacing(6)
        self.body_v.addLayout(self.adapters_box)

        self.dhcp_row = QFrame()
        self.dhcp_row.setObjectName("dhcpRow")
        self.dhcp_row.setCursor(Qt.PointingHandCursor)
        dh = QHBoxLayout(self.dhcp_row)
        dh.setContentsMargins(10, 6, 10, 6)
        dh.setSpacing(8)
        self.dhcp_icon = QLabel()
        self.dhcp_icon.setPixmap(icons.pixmap("dhcp", "#86868B", 14))
        dh.addWidget(self.dhcp_icon)
        self.dhcp_text = QLabel("DHCP 服务：—")
        self.dhcp_text.setObjectName("dhcpText")
        dh.addWidget(self.dhcp_text)
        dh.addStretch(1)
        dhcp_go = QLabel("打开 ›")
        dhcp_go.setObjectName("dhcpGo")
        dhcp_go.setStyleSheet("color:#007AFF; font-size:11px;")
        dh.addWidget(dhcp_go)
        self.dhcp_row.mouseReleaseEvent = lambda e: self.open_dhcp.emit()
        self.body_v.addWidget(self.dhcp_row)

        self.lbl_presets = SectionLabel("IP 方案")
        self.body_v.addWidget(self.lbl_presets)

        self.presets_grid_box = QWidget()
        self.presets_grid = QGridLayout(self.presets_grid_box)
        self.presets_grid.setContentsMargins(0, 0, 0, 0)
        self.presets_grid.setSpacing(6)
        self.body_v.addWidget(self.presets_grid_box)

        self.empty_presets = QLabel("暂无方案 · 在主窗口「网卡管理」中保存")
        self.empty_presets.setObjectName("dhcpText")
        self.empty_presets.setAlignment(Qt.AlignCenter)
        self.empty_presets.setStyleSheet("color:#AEAEB2; font-size:11.5px;")
        self.body_v.addWidget(self.empty_presets)

        # ---- 确认条 ----
        self.confirm_bar = QFrame()
        self.confirm_bar.setObjectName("confirmBar")
        ch = QHBoxLayout(self.confirm_bar)
        ch.setContentsMargins(10, 7, 10, 7)
        ch.setSpacing(8)
        self.confirm_text = QLabel("")
        self.confirm_text.setObjectName("confirmText")
        ch.addWidget(self.confirm_text, 1)
        btn_no = QPushButton("取消")
        btn_no.setObjectName("footerBtn")
        btn_no.clicked.connect(self._cancel_confirm)
        ch.addWidget(btn_no)
        self.btn_yes = QPushButton("切换")
        self.btn_yes.setStyleSheet(
            "background:#007AFF;color:#FFF;border:none;border-radius:6px;"
            "padding:4px 12px;font-weight:600;")
        self.btn_yes.clicked.connect(self._do_confirm)
        ch.addWidget(self.btn_yes)
        self.confirm_bar.hide()
        root.addWidget(self.confirm_bar)

        # ---- 底部工具栏 ----
        footer = QFrame()
        footer.setObjectName("footer")
        fh = QHBoxLayout(footer)
        fh.setContentsMargins(4, 7, 4, 2)
        fh.setSpacing(2)
        self._footer_btn(fh, "window", "主窗口", self.open_main)
        self._footer_btn(fh, "diagnose", "网络诊断", self.open_diagnostics)
        fh.addStretch(1)
        self._footer_btn(fh, "settings", "设置", self.open_settings)
        self._footer_btn(fh, "x", "退出", self.quit_requested)
        root.addWidget(footer)

        # ---- 面板内轻提示 ----
        self.toast = QLabel(self)
        self.toast.setObjectName("toastLabel")
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._fade_toast)

        self._spinner_angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._spin)

    # ---------- 小工具 ----------
    def _logo_pix(self):
        pm = icons.pixmap("nodes", "#FFFFFF", 18)
        return pm

    def _footer_btn(self, layout, icon_key, text, sig):
        btn = QPushButton(f" {text}")
        btn.setObjectName("footerBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setIcon(icons.icon(icon_key, "#86868B", 13))
        btn.clicked.connect(lambda: sig.emit() if hasattr(sig, "emit") else sig())
        layout.addWidget(btn)
        return btn

    def _spin(self):
        from PySide6.QtGui import QTransform
        self._spinner_angle = (self._spinner_angle + 30) % 360
        pm = icons.pixmap("refresh", "#86868B", 14)
        self.spinner.setPixmap(
            pm.transformed(QTransform().rotate(self._spinner_angle), Qt.SmoothTransformation))

    # ---------- 状态驱动 ----------
    def update_state(self, snap: dict):
        dark = self._dark
        ifaces = snap.get("ifaces") or []
        detail = snap.get("detail") or {}

        # 总体状态
        if snap.get("refreshing"):
            self.pill.set_kind("info", "正在刷新")
            self.spinner.show()
            if not self._spinner_timer.isActive():
                self._spinner_timer.start()
        else:
            self.spinner.hide()
            self._spinner_timer.stop()
            has_ip = [i for i in ifaces if i.get("ipv4")]
            up_no_ip = [i for i in ifaces
                        if i.get("status") == "up" and not i.get("ipv4")]
            if snap.get("stale"):
                self.pill.set_kind("warn", "数据已过期")
            elif not ifaces:
                self.pill.set_kind("muted", "未检测到网卡")
            elif has_ip:
                if snap.get("elevation_ok") is False:
                    self.pill.set_kind("warn", "正常 · 权限不足")
                elif up_no_ip:
                    self.pill.set_kind("warn", "部分网卡断开")
                else:
                    self.pill.set_kind("ok", "网络正常")
            elif up_no_ip:
                self.pill.set_kind("err", "网络异常")
            else:
                self.pill.set_kind("err", "网络未连接")

        # 过期横幅
        if snap.get("stale"):
            ts = datetime.datetime.fromtimestamp(
                snap.get("ts") or 0).strftime("%H:%M") if snap.get("ts") else "—"
            self.stale_text.setText(
                f"数据已过期（上次成功 {ts}）· {snap.get('error') or '刷新失败'}")
            self.stale_bar.show()
        else:
            self.stale_bar.hide()

        # DHCP 行
        running = snap.get("dhcp_running")
        self.dhcp_text.setText(f"DHCP 服务：{'运行中' if running else '未运行'}")
        self.dhcp_icon.setPixmap(icons.pixmap(
            "dhcp", "#30A46C" if running else "#86868B", 14))

        # 网卡列表（签名一致则不重建，避免闪烁）
        sig = tuple(
            (i.get("service"), i.get("device"), i.get("ipv4"), i.get("mask"),
             i.get("router"), i.get("status"), i.get("mac"),
             (detail.get(i.get("service") or "") or {}).get("mode"),
             tuple((detail.get(i.get("service") or "") or {}).get("aliases") or ()),
             (detail.get(i.get("service") or "") or {}).get("link"),
             tuple((detail.get(i.get("service") or "") or {}).get("ipv6") or ()),
             tuple((detail.get(i.get("service") or "") or {}).get("dns") or ()),
             ) for i in ifaces)
        if sig != self._sig:
            self._sig = sig
            self._rebuild_adapters(ifaces, detail, dark)

        self.lbl_adapters.setText(f"网卡 · {len(ifaces)}")

        # 方案
        presets = snap.get("presets") or []
        psig = tuple((p.get("name"), p.get("service"), p.get("mode"), p.get("ip"),
                      p.get("mask"), p.get("router"), tuple(p.get("dns") or ()))
                     for p in presets)
        applied_map = self._applied_presets(presets, ifaces, detail)
        if psig != self._presets_sig or applied_map != getattr(self, "_applied_map", None):
            self._presets_sig = psig
            self._applied_map = applied_map
            self._rebuild_presets(presets, applied_map)

        self._relayout_soon()

    # ---------- 网卡列表 ----------
    def _rebuild_adapters(self, ifaces, detail, dark):
        while self.adapters_box.count():
            item = self.adapters_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        groups = {"up": [], "down": [], "absent": []}
        for i in ifaces:
            groups.setdefault(i.get("status") or "down", []).append(i)
        order = [("up", "已连接"), ("down", "未连接"), ("absent", "未插入")]
        for key, title in order:
            rows = groups.get(key) or []
            if not rows:
                continue
            if len(groups) > 1:
                self.adapters_box.addWidget(SectionLabel(title))
            for ifc in rows:
                svc = ifc.get("service") or ifc.get("device") or ""
                card = AdapterCard(ifc, detail.get(svc, {}), dark)
                card.copy_requested.connect(self.copy_summary)
                card.open_in_main.connect(self._open_iface_main)
                if svc in self._expanded:
                    card.set_expanded(True, animate=False)
                self.adapters_box.addWidget(card)

        if not ifaces:
            empty = QLabel("未检测到网卡")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:#AEAEB2; font-size:12px; padding: 14px 0;")
            self.adapters_box.addWidget(empty)

    # ---------- 方案 ----------
    @staticmethod
    def _applied_presets(presets, ifaces, detail):
        """判断每个方案当前是否已应用（与网卡实际状态比对）"""
        result = set()
        by_svc = {}
        for i in ifaces:
            by_svc[i.get("service")] = i
        for idx, p in enumerate(presets):
            ifc = by_svc.get(p.get("service"))
            if not ifc:
                continue
            d = detail.get(p.get("service"), {})
            if p.get("mode") == "static":
                ok = (ifc.get("ipv4") == p.get("ip")
                      and (ifc.get("mask") or "") == (p.get("mask") or ""))
            else:
                ok = d.get("mode") == "dhcp"
            if ok and p.get("dns"):
                ok = (d.get("dns") or []) == list(p["dns"])
            if ok:
                result.add(idx)
        return result

    def _rebuild_presets(self, presets, applied_map):
        while self.presets_grid.count():
            item = self.presets_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for idx, p in enumerate(presets):
            chip = PresetChip(p, idx in applied_map)
            chip.clicked.connect(self._preset_clicked)
            self.presets_grid.addWidget(chip, idx // 2, idx % 2)
        self.presets_grid_box.setVisible(bool(presets))
        self.empty_presets.setVisible(not presets)
        self.lbl_presets.setVisible(bool(presets))

    def _preset_clicked(self, chip: PresetChip):
        p = chip.preset
        if getattr(self, "_confirm_preset", None) is p:
            return
        svc = p.get("service") or "—"
        mode = "手动 IP" if p.get("mode") == "static" else "自动 DHCP"
        target = p.get("ip") or mode
        self._confirm_preset = p
        self.confirm_text.setText(
            f"将「{p.get('name')}」应用到 {svc}？目标 {target}")
        self.confirm_bar.show()
        self._relayout_soon()

    def _cancel_confirm(self):
        self._confirm_preset = None
        self.confirm_bar.hide()
        self._relayout_soon()

    def _do_confirm(self):
        p = self._confirm_preset
        self._cancel_confirm()
        if not p:
            return
        self.show_toast("正在切换…", "info")
        self.apply_preset_requested.emit(dict(p))

    # ---------- 复制 ----------
    def _copy_feedback(self, label: str, value: str):
        QApplication.clipboard().setText(value)
        short = value if len(value) <= 28 else value[:26] + "…"
        self.show_toast(f"已复制 {label}：{short}")

    def copy_summary(self, svc: str):
        snap = self.state.snapshot()
        ifc = next((i for i in snap.get("ifaces") or []
                    if (i.get("service") or i.get("device")) == svc), None)
        if not ifc:
            return
        d = (snap.get("detail") or {}).get(svc, {})
        status = {"up": "已连接", "down": "未连接", "absent": "未插入"}.get(
            ifc.get("status"), "未知")
        mask = ifc.get("mask") or ""
        try:
            plen = f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}', strict=False).prefixlen}"
        except Exception:
            plen = ""
        lines = [
            f"【{ifc.get('service') or svc}】({ifc.get('device') or svc}) {status}",
            f"IP:        {(ifc.get('ipv4') or '—')}{plen if ifc.get('ipv4') else ''}",
            f"子网掩码:  {mask or '—'}",
            f"默认网关:  {ifc.get('router') or '—'}",
            f"DNS:       {', '.join(d.get('dns') or []) or '自动获取'}",
            f"MAC 地址:  {ifc.get('mac') or '—'}",
        ]
        if d.get("ipv6"):
            lines.append(f"IPv6:      {'  '.join(d['ipv6'])}")
        aliases = d.get("aliases") or []
        lines.append(f"附加 IP:   {', '.join(aliases) if aliases else '无'}")
        lines.append(f"配置方式:  "
                     f"{'手动配置' if d.get('mode') == 'static' else 'DHCP 自动'}")
        if d.get("link"):
            lines.append(f"链路速率:  {d['link']}")
        lines.append(f"复制时间:   {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)
        self.show_toast("已复制网卡配置摘要")

    def _open_iface_main(self, svc: str):
        self.open_main.emit()
        try:
            win = QApplication.activeWindow()
            if win is not None and hasattr(win, "_open_iface"):
                win._open_iface(svc)
        except Exception:
            pass

    # ---------- 轻提示 ----------
    def show_toast(self, text: str, kind: str = "ok"):
        self.toast.setText(text)
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2,
                        self.height() - self.toast.height() - 58)
        self.toast.show()
        self.toast.raise_()
        self._toast_timer.start(1800)

    def _fade_toast(self):
        self.toast.hide()

    # ---------- 尺寸/位置 ----------
    def _relayout_soon(self):
        QTimer.singleShot(0, self._relayout)

    def _relayout(self):
        body = self.scroll.widget()
        if body is None:
            return
        body.adjustSize()
        anchor = getattr(self, "_anchor", None) or QCursor_pos()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        avail_h = screen.availableGeometry().height() if screen else 900
        max_h = int(avail_h * 0.72)
        content_h = body.sizeHint().height() + 130
        h = max(PANEL_MIN_H, min(content_h, max_h))
        self.scroll.setFixedHeight(h - 24)
        self.resize(PANEL_WIDTH, h)
        self._place()

    def _place(self):
        anchor = getattr(self, "_anchor", None) or QCursor_pos()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = anchor.x() - self.width() // 2
        x = max(avail.left() + 8, min(x, avail.right() - self.width() - 8))
        y = avail.top() + 6
        self.move(x, y)

    # ---------- 显示 / 关闭 ----------
    def show_at(self, global_pos):
        self._anchor = global_pos
        self._dark = _panel_dark()
        self.setStyleSheet(panel_qss(self._dark))
        self._sig = None
        self._presets_sig = None
        self.update_state(self.state.snapshot())
        self.adjustSize()
        self._relayout()
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            if not getattr(self, "_vibrancy", False):
                self._vibrancy = material.attach_vibrancy(self, self._dark,
                                                          PANEL_RADIUS)
                self.update()
            if not material.reduce_motion():
                self._animate_open()

    def _animate_open(self):
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        # 只对内容做透明度渐入（窗口整体透明度在部分系统上会造成材质闪烁）
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(130)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._open_anim = anim

    def hideEvent(self, e):
        import time
        self._last_hide_ts = time.time()
        self._cancel_confirm()
        self._expanded = set()
        for r in _iter_cards(self):
            if r._expanded:
                self._expanded.add(r.ifc.get("service") or r.ifc.get("device"))
        super().hideEvent(e)

    def paintEvent(self, e):
        material.paint_panel_background(self, self._dark, PANEL_RADIUS,
                                        vibrancy_ok=self._vibrancy)

    def toggle_at(self, global_pos):
        import time
        if self.isVisible():
            self.close()
        elif time.time() - self._last_hide_ts > 0.35:
            self.show_at(global_pos)


def _iter_cards(panel):
    box = panel.adapters_box
    for i in range(box.count()):
        w = box.itemAt(i).widget()
        if isinstance(w, AdapterCard):
            yield w


def QCursor_pos():
    from PySide6.QtGui import QCursor
    return QCursor.pos()


def _panel_dark() -> bool:
    try:
        from .. import theme
        mgr = theme.current()
        return bool(mgr and mgr.dark)
    except Exception:
        return False

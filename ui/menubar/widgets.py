"""Network Control 面板子组件：可复制字段、状态胶囊、网卡行、方案芯片

设计要点
- 网卡卡片支持原地增量更新（update_data），不销毁重建 → 展开状态与滚动位置天然保留
- 详情字段固定顺序、按需显示，主 IPv4 / 附加 IPv4 / IPv6 分层明确
- 所有值均为等宽字体，点击整行复制，悬停有明确反馈
"""
import ipaddress

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import icons

# ---- 视觉常量：全面板统一，避免各组件各写一套 ----
DOT_W = 9              # 状态圆点占位宽
ICON_SIZE = 16         # 网卡类型图标
CHEVRON_SIZE = 14
FIELD_LABEL_W = 48     # 详情字段左标签宽
ACCENT = "#007AFF"


def _prefix(mask: str) -> str:
    try:
        return f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}', strict=False).prefixlen}"
    except Exception:
        return ""


# ---------------- 状态胶囊 ----------------
class StatusPill(QFrame):
    """总体网络状态胶囊：圆点 + 文字（文字过长时自动省略，不撑破头部）"""

    KIND = {"ok": "ok", "warn": "warn", "err": "err", "info": "info", "muted": "muted"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pill")
        h = QHBoxLayout(self)
        h.setContentsMargins(9, 3, 10, 3)
        h.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setObjectName("pillDot")
        self.dot.setFixedWidth(DOT_W)
        self.dot.setAlignment(Qt.AlignCenter)
        self.text = QLabel("—")
        self.text.setObjectName("pillText")
        self.text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        h.addWidget(self.dot)
        h.addWidget(self.text, 1)
        self.set_kind("muted", "—")

    def set_kind(self, kind: str, text: str):
        if self.text.text() == text and self.property("kind") == self.KIND.get(kind):
            return
        self.text.setText(text)
        # 固定胶囊宽度：头部空间不足时由副标题（可省略）让位，状态文字永远完整
        self.text.setMinimumWidth(self.text.sizeHint().width())
        self.setProperty("kind", self.KIND.get(kind, "info"))
        self.style().unpolish(self)
        self.style().polish(self)
        self.setToolTip(text)


# ---------------- 可复制字段 ----------------
class CopyField(QFrame):
    """标签 + 等宽值，整行可点复制；hover 时复制图标提亮，值底色变化由 QSS 负责"""

    copied = Signal(str, str)          # label, value

    def __init__(self, label: str, value: str = "", parent=None,
                 wrap: bool = False, copyable: bool = True):
        super().__init__(parent)
        self.setObjectName("copyField")
        self._value = ""
        self._copyable = copyable
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)
        self._label = QLabel(label)
        self._label.setObjectName("fieldLabel")
        self._label.setFixedWidth(FIELD_LABEL_W)
        h.addWidget(self._label)
        self.value = QLabel(value or "—")
        self.value.setObjectName("fieldValue")
        f = self.value.font()
        f.setFamily("SF Mono")
        self.value.setFont(f)
        self.value.setTextInteractionFlags(Qt.NoTextInteraction)
        if wrap:
            self.value.setWordWrap(True)
        else:
            self.value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        h.addWidget(self.value, 1)
        self._icon = QLabel()
        self._icon.setFixedSize(14, 14)
        self._icon.setAlignment(Qt.AlignCenter)
        h.addWidget(self._icon)
        self._icon.setVisible(copyable)
        if copyable:
            self.setCursor(Qt.PointingHandCursor)
        self._paint_icon(False)
        self.set_value(value)

    # ---- 值 ----
    def set_value(self, text: str):
        text = (text or "").strip()
        if text == self._value:
            return
        self._value = text
        self.value.setText(text or "—")
        self.value.setProperty("empty", not bool(text))
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)
        if self._copyable:
            self.setToolTip("点击复制" if self._value else "无内容")

    def value_text(self) -> str:
        return self._value

    # ---- 悬停反馈 ----
    def _paint_icon(self, hover: bool):
        if not self._copyable:
            self._icon.clear()
            return
        self._icon.setPixmap(icons.pixmap("copy", ACCENT if hover else "#B0B0B5", 12))

    def enterEvent(self, e):
        if self._copyable and self._value:
            self._paint_icon(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._paint_icon(False)
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._value and self._copyable:
            self.copied.emit(self._label.text(), self._value)
        super().mouseReleaseEvent(e)


# ---------------- 分组小标题 ----------------
class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("panelSection")


# ---------------- 省略号标签 ----------------
class ElidedLabel(QLabel):
    """宽度不足时省略显示，tooltip 显示全文

    mode：IP/地址类用 ElideMiddle（保留首尾），说明文字用 ElideRight。
    """

    def __init__(self, text: str = "", parent=None,
                 mode: Qt.TextElideMode = Qt.ElideMiddle):
        super().__init__(parent)
        self._raw = ""
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setRawText(text)

    def setRawText(self, text: str):
        text = text or ""
        if text == self._raw:
            return
        self._raw = text
        self.setToolTip(self._raw)
        self._apply()

    def rawText(self) -> str:
        return self._raw

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def _apply(self):
        fm = self.fontMetrics()
        elided = fm.elidedText(self._raw, self._mode, max(10, self.width()))
        QLabel.setText(self, elided)


# ---------------- 网卡卡片 ----------------
class AdapterCard(QFrame):
    """一张网卡：折叠头行 + 可展开详情（字段级复制 + 摘要复制）

    支持 update_data() 原地刷新：不重建控件，展开状态与滚动位置不受影响。
    """

    copy_requested = Signal(str)              # 复制整卡摘要（参数：服务名）
    open_in_main = Signal(str)                # 在主窗口打开
    copy_value = Signal(str, str)             # 复制单个字段（label, value）

    # 详情字段顺序（固定）：(key, 标签, 是否换行, 是否可复制)
    FIELDS = [
        ("ip", "IPv4", False, True),
        ("mask", "掩码", False, True),
        ("gw", "网关", False, True),
        ("dns", "DNS", True, True),
    ]
    TAIL_FIELDS = [
        ("ipv6", "IPv6", True, True),
        ("mac", "MAC", False, True),
        ("mode", "配置", False, False),
        ("link", "链路", False, True),
    ]

    def __init__(self, ifc: dict, detail: dict, dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("adapterCard")
        self.ifc = dict(ifc or {})
        self.detail = dict(detail or {})
        self._dark = bool(dark)
        self._expanded = False
        self._fields = {}      # key → QWidget(CopyField / 空态标签)
        self._alias_count = -1

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ---- 折叠头 ----
        self.head = QWidget()
        self.head.setObjectName("adapterHead")
        self.head.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(self.head)
        h.setContentsMargins(9, 7, 9, 7)
        h.setSpacing(8)

        self.dot = QLabel("●")
        self.dot.setFixedWidth(DOT_W)
        self.dot.setAlignment(Qt.AlignCenter)
        self.dot.setStyleSheet("font-size:9px;")
        h.addWidget(self.dot)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(self.icon_lbl)

        box = QVBoxLayout()
        box.setSpacing(1)
        self.name = ElidedLabel(self.ifc.get("service") or self.ifc.get("port") or "—")
        self.name.setObjectName("adapterName")
        box.addWidget(self.name)
        self.sub = ElidedLabel("")
        self.sub.setObjectName("adapterSub")
        box.addWidget(self.sub)
        h.addLayout(box, 1)

        right = QVBoxLayout()
        right.setSpacing(1)
        self.ip = QLabel()
        self.ip.setObjectName("adapterIp")
        self.ip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right.addWidget(self.ip)
        self.meta = QLabel()
        self.meta.setObjectName("adapterMeta")
        self.meta.setAlignment(Qt.AlignRight)
        right.addWidget(self.meta)
        h.addLayout(right, 0)

        self.chevron = QLabel()
        self.chevron.setFixedSize(CHEVRON_SIZE, CHEVRON_SIZE)
        self.chevron.setAlignment(Qt.AlignCenter)
        h.addWidget(self.chevron)

        v.addWidget(self.head)

        # ---- 展开详情 ----
        self.detail_box = QWidget()
        self.detail_box.setObjectName("adapterDetail")
        dv = QVBoxLayout(self.detail_box)
        dv.setContentsMargins(9, 0, 9, 9)
        dv.setSpacing(3)
        self._grid = QVBoxLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(3)
        dv.addLayout(self._grid)
        self.detail_box.setVisible(False)
        self.detail_box.setMaximumHeight(0)
        v.addWidget(self.detail_box)

        self.head.mouseReleaseEvent = self._toggle

        self._render_head()
        self._set_chevron(False)

    # ---------- 键 / 状态 ----------
    @property
    def key(self) -> str:
        return f"{self.ifc.get('service') or ''}|{self.ifc.get('device') or ''}"

    @property
    def expanded(self) -> bool:
        return self._expanded

    # ---------- 头部渲染 ----------
    def _kind(self):
        try:
            from core.netinfo import iface_kind
            return iface_kind(self.ifc)
        except Exception as exc:
            from core import applog
            applog.exception("AdapterCard._kind", exc)
            return "other"

    def _dot_color(self):
        from .status import classify_iface
        return {"up": "#30A46C", "down": "#B0B0B5", "absent": "#E5A000",
                "disabled": "#B0B0B5"}.get(classify_iface(self.ifc), "#B0B0B5")

    def _render_head(self):
        kind = self._kind()
        self.dot.setStyleSheet(f"color:{self._dot_color()}; font-size:9px;")
        icon_key = {"wifi": "wifi", "usb": "usb", "thunderbolt": "bolt",
                    "bluetooth": "bt", "bridge": "bridge", "vpn": "shield",
                    "ethernet": "ethernet"}.get(kind, "ethernet")
        icon_color = "#1D1D1F" if not self._dark else "#E8E8ED"
        self.icon_lbl.setPixmap(icons.pixmap(icon_key, icon_color, 15))

        self.name.setRawText(self.ifc.get("service") or self.ifc.get("port") or "—")

        bits = [self.ifc.get("device") or "—"]
        link = self.detail.get("link") or ""
        if link and self.ifc.get("status") == "up":
            bits.append(link)
        bits.append({"wifi": "Wi-Fi", "usb": "USB", "thunderbolt": "雷雳",
                     "bluetooth": "蓝牙", "bridge": "桥接", "vpn": "VPN",
                     "ethernet": "以太网"}.get(kind, "网卡"))
        self.sub.setRawText(" · ".join(bits))

        ip = self.ifc.get("ipv4") or ""
        plen = _prefix(self.ifc.get("mask") or "") if ip else ""
        self.ip.setText(f"{ip}{plen}" if ip else "未分配 IP")
        self.ip.setProperty("empty", not bool(ip))
        self.ip.style().unpolish(self.ip)
        self.ip.style().polish(self.ip)

        mode = {"static": "手动", "dhcp": "DHCP"}.get(self.detail.get("mode"), "—")
        aliases = self.detail.get("aliases") or []
        parts = [mode]
        if aliases:
            parts.append(f"附加 {len(aliases)}")
        self.meta.setText(" · ".join(parts))

    # ---------- 增量更新（关键：不重建控件）----------
    def update_data(self, ifc: dict, detail: dict):
        self.ifc = dict(ifc or {})
        self.detail = dict(detail or {})
        self._render_head()
        if self._expanded:
            self._fill_fields()
            self.detail_box.setMaximumHeight(self.detail_box.sizeHint().height())

    def _set_chevron(self, expanded: bool):
        from PySide6.QtGui import QTransform
        color = "#86868B" if not self._dark else "#98989D"
        pm = icons.pixmap("chevron", color, 12)
        if not expanded:
            pm = pm.transformed(QTransform().rotate(-90), Qt.SmoothTransformation)
        self.chevron.setPixmap(pm)

    # ---------- 展开 ----------
    def _toggle(self, e):
        if e.button() != Qt.LeftButton:
            return
        self.set_expanded(not self._expanded)

    def set_expanded(self, on: bool, animate: bool = True):
        if on == self._expanded:
            return
        self._expanded = on
        if on:
            self._fill_fields()
        self._set_chevron(on)
        self.detail_box.setVisible(on)
        if on:
            target = self.detail_box.sizeHint().height()
            self.detail_box.setMaximumHeight(0 if animate else target)
            if animate and not self._reduce_motion():
                anim = QPropertyAnimation(self.detail_box, b"maximumHeight", self)
                anim.setDuration(140)
                anim.setStartValue(0)
                anim.setEndValue(target)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.start(QPropertyAnimation.DeleteWhenStopped)
                self._anim = anim
            else:
                self.detail_box.setMaximumHeight(target)
        else:
            self.detail_box.setMaximumHeight(0)
        w = self.window()
        if hasattr(w, "_relayout_soon"):
            w._relayout_soon()

    @staticmethod
    def _reduce_motion():
        try:
            from .material import reduce_motion
            return reduce_motion()
        except Exception:
            return False

    # ---------- 详情字段 ----------
    def _make_field(self, key, label, wrap, copyable):
        f = CopyField(label, "", wrap=wrap, copyable=copyable)
        f.copied.connect(lambda lab, val: self.copy_value.emit(lab, val))
        self._fields[key] = f
        return f

    def _fill_fields(self):
        """构建/刷新详情字段：字段集合固定，附加 IP 按数量动态增删"""
        aliases = list(self.detail.get("aliases") or [])
        order = []

        for key, label, wrap, copyable in self.FIELDS:
            if key not in self._fields:
                self._make_field(key, label, wrap, copyable)
            order.append(self._fields[key])

        # 附加 IPv4：每个地址独立一行，可单独复制
        if self._alias_count >= 0:
            for idx in range(self._alias_count, -1, -1):
                if idx < len(aliases):
                    continue
                f = self._fields.pop(f"alias{idx}", None)
                if f is not None:
                    self._grid.removeWidget(f)
                    f.setParent(None)
                    f.deleteLater()
        for idx in range(len(aliases)):
            key = f"alias{idx}"
            if key not in self._fields:
                self._make_field(key, f"附加{idx + 1}", False, True)
            order.append(self._fields[key])
        self._alias_count = len(aliases)

        for key, label, wrap, copyable in self.TAIL_FIELDS:
            if key not in self._fields:
                self._make_field(key, label, wrap, copyable)
            order.append(self._fields[key])

        # 顺序（重新插入即可排序）
        for f in order:
            self._grid.removeWidget(f)
        for f in order:
            self._grid.addWidget(f)

        # 写值
        ifc, d = self.ifc, self.detail
        ip = ifc.get("ipv4") or ""
        self._fields["ip"].set_value(f"{ip}{_prefix(ifc.get('mask') or '')}" if ip else "")
        self._fields["mask"].set_value(ifc.get("mask") or "")
        self._fields["gw"].set_value(ifc.get("router") or "")
        dns = [x for x in (d.get("dns") or []) if x]
        self._fields["dns"].set_value(", ".join(dns))
        for idx, addr in enumerate(aliases):
            f = self._fields.get(f"alias{idx}")
            if f:
                f.set_value(addr)
        ipv6 = [x for x in (d.get("ipv6") or []) if x and not x.lower().startswith("fe80")]
        self._fields["ipv6"].set_value("  ·  ".join(ipv6))
        self._fields["mac"].set_value(ifc.get("mac") or "")
        mode = {"static": "手动配置", "dhcp": "DHCP 自动"}.get(d.get("mode"), "")
        self._fields["mode"].set_value(mode)
        link = (d.get("link") or "") if ifc.get("status") == "up" else ""
        self._fields["link"].set_value(link)

        for key, f in list(self._fields.items()):
            if key == "empty":
                continue
            f.setVisible(bool(f.value_text()))

        # 无 IP 时给出明确空态
        if not ip:
            if "empty" not in self._fields:
                lb = QLabel("该网卡当前没有 IPv4 地址")
                lb.setObjectName("fieldEmpty")
                self._fields["empty"] = lb
                self._grid.addWidget(lb)
            self._fields["empty"].setVisible(True)
        elif "empty" in self._fields:
            self._fields["empty"].setVisible(False)

    # ---------- 右键 ----------
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        svc = self.ifc.get("service") or self.ifc.get("device")
        d = self.detail
        act_sum = menu.addAction("复制网卡配置摘要")
        menu.addSeparator()
        act_ip = menu.addAction("复制主 IP")
        act_ip.setEnabled(bool(self.ifc.get("ipv4")))
        aliases = d.get("aliases") or []
        if aliases:
            sub = menu.addMenu("复制附加 IP")
            for addr in aliases:
                a = sub.addAction(addr)
                a.triggered.connect(lambda _=False, v=addr: self.copy_value.emit("附加 IP", v))
        act_gw = menu.addAction("复制默认网关")
        act_gw.setEnabled(bool(self.ifc.get("router")))
        act_dns = menu.addAction("复制 DNS")
        act_dns.setEnabled(bool(d.get("dns")))
        menu.addSeparator()
        act_open = menu.addAction("在主窗口中打开")
        chosen = menu.exec(e.globalPos())
        if chosen is act_sum:
            self.copy_requested.emit(svc)
        elif chosen is act_ip and self.ifc.get("ipv4"):
            self.copy_value.emit("IP", self.ifc["ipv4"])
        elif chosen is act_gw and self.ifc.get("router"):
            self.copy_value.emit("网关", self.ifc["router"])
        elif chosen is act_dns and d.get("dns"):
            self.copy_value.emit("DNS", ", ".join(d.get("dns") or []))
        elif chosen is act_open:
            self.open_in_main.emit(svc)


# ---------------- 方案芯片 ----------------
class PresetChip(QFrame):
    """两列方案芯片：名称 + 目标信息；已应用时高亮并带「当前」标记"""

    clicked = Signal(object)          # self

    def __init__(self, preset: dict, applied: bool, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.setObjectName("presetChip")
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self.name = ElidedLabel(preset.get("name") or "未命名方案")
        self.name.setObjectName("chipName")
        top.addWidget(self.name, 1)
        self.badge = QLabel("当前")
        self.badge.setObjectName("chipBadge")
        top.addWidget(self.badge, 0)
        v.addLayout(top)
        mode = "手动" if preset.get("mode") == "static" else "DHCP"
        target = preset.get("ip") or mode
        self.sub = ElidedLabel(f"{preset.get('service') or '—'} · {target}")
        self.sub.setObjectName("chipSub")
        v.addWidget(self.sub)
        self._applied = None
        self.set_applied(applied)

    def set_applied(self, applied: bool):
        applied = bool(applied)
        self.badge.setVisible(applied)
        if applied == self._applied:
            return
        self._applied = applied
        self.setProperty("applied", applied)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self)

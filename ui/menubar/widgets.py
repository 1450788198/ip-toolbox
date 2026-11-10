"""Network Control 面板子组件：可复制字段、状态胶囊、网卡行、方案芯片"""
import ipaddress

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import icons


def _prefix(mask: str) -> str:
    try:
        return f"/{ipaddress.IPv4Network(f'0.0.0.0/{mask}', strict=False).prefixlen}"
    except Exception:
        return ""


# ---------------- 状态胶囊 ----------------
class StatusPill(QFrame):
    """总体网络状态胶囊：圆点 + 文字"""

    KIND = {"ok": "ok", "warn": "warn", "err": "err", "info": "info", "muted": "muted"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pill")
        h = QHBoxLayout(self)
        h.setContentsMargins(9, 3, 10, 3)
        h.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setObjectName("pillDot")
        self.text = QLabel("—")
        self.text.setObjectName("pillText")
        h.addWidget(self.dot)
        h.addWidget(self.text)
        self.set_kind("muted", "—")

    def set_kind(self, kind: str, text: str):
        self.text.setText(text)
        self.setProperty("kind", self.KIND.get(kind, "info"))
        self.style().unpolish(self)
        self.style().polish(self)


# ---------------- 可复制字段 ----------------
class CopyField(QFrame):
    """标签 + 等宽值，点击复制；hover 高亮"""

    copied = Signal(str, str)          # label, value

    def __init__(self, label: str, value: str = "—", parent=None, wrap: bool = False):
        super().__init__(parent)
        self.setObjectName("copyField")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击复制")
        self._value = ""
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)
        lb = QLabel(label)
        lb.setObjectName("fieldLabel")
        lb.setFixedWidth(52)
        h.addWidget(lb)
        self.value = QLabel(value or "—")
        self.value.setObjectName("fieldValue")
        f = self.value.font()
        f.setFamily("SF Mono")
        f.setFamily("Menlo")
        self.value.setFont(f)
        if wrap:
            self.value.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.NoTextInteraction)
        h.addWidget(self.value, 1)
        self._icon = QLabel()
        self._icon.setPixmap(icons.pixmap("copy", "#86868B", 13))
        self._icon.setFixedSize(14, 14)
        h.addWidget(self._icon)
        self.set_value(value)

    def set_value(self, text: str):
        self._value = text or ""
        self.value.setText(self._value or "—")
        self.value.setVisible(bool(self._value))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._value:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._value)
            self.copied.emit(self.value.text(), self._value)
        super().mouseReleaseEvent(e)


# ---------------- 分组小标题 ----------------
class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("panelSection")


# ---------------- 省略号标签 ----------------
class ElidedLabel(QLabel):
    """宽度不足时自动省略（中间省略），tooltip 显示全文"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._raw = text or ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._apply()

    def setRawText(self, text: str):
        self._raw = text or ""
        self.setToolTip(self._raw)
        self._apply()

    def rawText(self) -> str:
        return self._raw

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def _apply(self):
        fm = self.fontMetrics()
        elided = fm.elidedText(self._raw, Qt.ElideMiddle, max(10, self.width()))
        QLabel.setText(self, elided)


# ---------------- 网卡行 ----------------
class AdapterCard(QFrame):
    """一张网卡：折叠头行 + 可展开详情（全部字段可复制）"""

    copy_requested = Signal(str)           # 复制摘要
    open_in_main = Signal(str)             # 在主窗口打开该网卡

    def __init__(self, ifc: dict, detail: dict, dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("adapterCard")
        self.ifc = ifc
        self.detail = detail or {}
        self._dark = dark
        self._expanded = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.head = QWidget()
        self.head.setObjectName("adapterHead")
        self.head.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(self.head)
        h.setContentsMargins(9, 8, 9, 8)
        h.setSpacing(8)

        kind = self._kind()
        dot_color = {"up": "#30A46C", "down": "#AEAEB2", "absent": "#E5A000"}.get(
            ifc.get("status"), "#AEAEB2")
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{dot_color}; font-size:9px;")
        dot.setFixedWidth(8)
        h.addWidget(dot)

        icon_key = {"wifi": "wifi", "usb": "usb", "thunderbolt": "bolt",
                    "bluetooth": "bt", "bridge": "bridge", "vpn": "shield",
                    "ethernet": "ethernet"}.get(kind, "ethernet")
        icon_color = "#1D1D1F" if not dark else "#E8E8ED"
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_key, icon_color, 15))
        ic.setFixedSize(16, 16)
        ic.setAlignment(Qt.AlignCenter)
        h.addWidget(ic)

        box = QVBoxLayout()
        box.setSpacing(1)
        name = ElidedLabel(ifc.get("service") or ifc.get("port") or "—")
        name.setObjectName("adapterName")
        box.addWidget(name)
        sub_bits = [ifc.get("device") or "—"]
        link = self.detail.get("link") or ""
        if link and ifc.get("status") == "up":
            sub_bits.append(link)
        kind_txt = {"wifi": "Wi-Fi", "usb": "USB", "thunderbolt": "雷雳",
                    "bluetooth": "蓝牙", "bridge": "桥接", "vpn": "VPN",
                    "ethernet": "以太网"}.get(kind, "网卡")
        sub_bits.append(kind_txt)
        sub = ElidedLabel(" · ".join(sub_bits))
        sub.setObjectName("adapterSub")
        box.addWidget(sub)
        h.addLayout(box, 1)

        right = QVBoxLayout()
        right.setSpacing(1)
        ip = QLabel(ifc.get("ipv4") or "无 IP")
        ip.setObjectName("adapterIp")
        ip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right.addWidget(ip)
        mode = self.detail.get("mode")
        aliases = self.detail.get("aliases") or []
        meta = {"static": "手动", "dhcp": "DHCP"}.get(mode, "—")
        if aliases:
            meta += f" +{len(aliases)}"
        meta_lbl = QLabel(meta)
        meta_lbl.setObjectName("adapterMeta")
        meta_lbl.setAlignment(Qt.AlignRight)
        right.addWidget(meta_lbl)
        h.addLayout(right, 0)

        self.chevron = QLabel()
        self._set_chevron(False)
        h.addWidget(self.chevron)

        v.addWidget(self.head)

        # ---- 展开详情 ----
        self.detail_box = QWidget()
        self.detail_box.setObjectName("adapterDetail")
        dv = QVBoxLayout(self.detail_box)
        dv.setContentsMargins(10, 2, 10, 10)
        dv.setSpacing(4)
        self._fields = []
        self._grid_holder = QWidget()
        self._grid = QVBoxLayout(self._grid_holder)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        dv.addWidget(self._grid_holder)
        self.detail_box.setVisible(False)
        self.detail_box.setMaximumHeight(0)
        v.addWidget(self.detail_box)

        self.head.mouseReleaseEvent = self._toggle

    # ---------- 构建/更新 ----------
    def _kind(self):
        try:
            from core.netinfo import iface_kind
            return iface_kind(self.ifc)
        except Exception:
            return "other"

    def _set_chevron(self, expanded: bool):
        rot = "chevronDown" if expanded else "chevron"
        color = "#86868B" if not self._dark else "#98989D"
        pm = icons.pixmap(rot, color, 13)
        if rot == "chevron":
            from PySide6.QtGui import QTransform
            pm = pm.transformed(QTransform().rotate(-90), Qt.SmoothTransformation)
        self.chevron.setPixmap(pm)
        self.chevron.setFixedSize(14, 14)
        self.chevron.setAlignment(Qt.AlignCenter)

    def _toggle(self, e):
        if e.button() != Qt.LeftButton:
            return
        self.set_expanded(not self._expanded)

    def set_expanded(self, on: bool, animate: bool = True):
        if on == self._expanded:
            return
        self._expanded = on
        if on and self._grid.count() == 0:
            self._fill_detail()
        self._set_chevron(on)
        self.detail_box.setVisible(on)
        if on:
            target = self.detail_box.sizeHint().height()
            self.detail_box.setMaximumHeight(0)
            if animate and not self._reduce_motion():
                anim = QPropertyAnimation(self.detail_box, b"maximumHeight", self)
                anim.setDuration(150)
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

    def _field(self, label, value, wrap=False):
        f = CopyField(label, value, wrap=wrap)
        f.copied.connect(lambda text, val, lab=label: self.window()._copy_feedback(lab, val))
        self._grid.addWidget(f)
        return f

    def _fill_detail(self):
        ifc, d = self.ifc, self.detail
        if ifc.get("ipv4"):
            self._field("IP", f"{ifc['ipv4']}{_prefix(ifc.get('mask') or '')}")
        self._field("掩码", ifc.get("mask") or "—")
        self._field("网关", ifc.get("router") or "—")
        dns = d.get("dns") or []
        self._field("DNS", ", ".join(dns) if dns else "自动获取", wrap=True)
        mac = ifc.get("mac") or "—"
        f = self._field("MAC", mac)
        if mac != "—":
            f.setCursor(Qt.PointingHandCursor)
        ipv6 = d.get("ipv6") or []
        if ipv6:
            self._field("IPv6", "  ·  ".join(ipv6), wrap=True)
        mode = {"static": "手动配置", "dhcp": "DHCP 自动"}.get(d.get("mode"), "—")
        self._field("配置", mode)
        aliases = d.get("aliases") or []
        self._field("附加IP", ", ".join(aliases) if aliases else "无", wrap=True)
        if d.get("link") and ifc.get("status") == "up":
            self._field("链路", d["link"])

    # ---------- 右键 ----------
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        svc = self.ifc.get("service") or self.ifc.get("device")
        act_sum = menu.addAction("复制网卡配置摘要")
        act_ip = menu.addAction("复制 IP 地址")
        menu.addSeparator()
        act_open = menu.addAction("在主窗口中打开")
        chosen = menu.exec(e.globalPos())
        if chosen is act_sum:
            self.copy_requested.emit(svc)
        elif chosen is act_ip:
            if self.ifc.get("ipv4"):
                self.window()._copy_feedback("IP", self.ifc["ipv4"])
        elif chosen is act_open:
            self.open_in_main.emit(svc)


# ---------------- 方案芯片 ----------------
class PresetChip(QFrame):
    """两列方案芯片：名称 + 目标信息；applied 高亮"""

    clicked = Signal(object)          # self

    def __init__(self, preset: dict, applied: bool, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.setObjectName("presetChip")
        if applied:
            self.setProperty("applied", True)
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 7, 10, 7)
        v.setSpacing(1)
        name = QLabel(preset.get("name") or "未命名方案")
        name.setObjectName("chipName")
        v.addWidget(name)
        mode = "手动" if preset.get("mode") == "static" else "DHCP"
        target = preset.get("ip") or mode
        sub = ElidedLabel(f"{preset.get('service') or '—'} · {target}")
        sub.setObjectName("chipSub")
        v.addWidget(sub)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self)

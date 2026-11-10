"""网卡管理：左侧网卡列表 + 右侧分组详情（基本信息 / IPv4 / 多 IP / 方案）

- 所有耗时操作走 Worker，不阻塞 UI
- 应用配置前强制展示变更预览
- 修改前保存原始配置，可恢复
"""
import ipaddress
import json
import os

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QFrame)

from core import history, presets as preset_store, settings
from core.dhcp_controller import app_data_dir
from core.netbase import iface_is_external, normalize_mask, sort_interfaces
from ..common import Worker
from ..components import Card, FormGrid, PageHeader, Segmented, StatusBadge
from ..dialogs import AliasDialog, BulkAliasDialog, ChangePreview, PresetDialog, confirm


# ---------------- 快照（原始配置） ----------------
def _snap_path() -> str:
    return os.path.join(app_data_dir(), "iface_snapshots.json")


def load_snapshots() -> dict:
    try:
        with open(_snap_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_snapshot(service: str, snap: dict):
    data = load_snapshots()
    data[service] = snap
    try:
        with open(_snap_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class AdapterRow(QWidget):
    """左侧网卡列表行：状态点 + 名称 + 设备/类型 + 当前 IP（名称过长自动省略）"""

    def __init__(self, ifc, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._raw_name = ifc.get("service") or ifc.get("port") or "—"
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 7, 10, 7)
        h.setSpacing(9)
        dot = QLabel("●")
        color = {"up": "#30A46C", "down": "#AEAEB2", "absent": "#E5A000"}.get(
            ifc.get("status"), "#AEAEB2")
        dot.setStyleSheet(f"color:{color}; font-size:11px;")
        dot.setFixedWidth(9)
        h.addWidget(dot, 0, Qt.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(2)
        self._name = QLabel(self._raw_name)
        self._name.setObjectName("value")
        self._name.setToolTip(self._raw_name)
        box.addWidget(self._name)
        sub = QLabel(ifc.get("device") + (" · USB" if iface_is_external(ifc) else " · 内置"))
        sub.setObjectName("hint")
        box.addWidget(sub)
        h.addLayout(box, 1)
        ip = QLabel(ifc.get("ipv4") or "无 IP")
        ip.setObjectName("monoSmall")
        h.addWidget(ip, 0, Qt.AlignRight | Qt.AlignVCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        fm = self._name.fontMetrics()
        self._name.setText(fm.elidedText(self._raw_name, Qt.ElideRight,
                                         max(60, self._name.width())))


class NetworkPage(QWidget):
    ifaces_changed = Signal(list)

    def __init__(self, backend, log, notify, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.log = log
        self.notify = notify
        self.ifaces = []
        self.current = None
        self._workers = []
        self._auto = False
        self._snapshots = load_snapshots()
        self._dns_cache = []
        self._mode_current = ""
        self._seg_touched = False
        self._build()
        # 网卡列表数据由共享 NetworkState 统一调度（见 apply_state）

    # ---------------- 共享状态 ----------------
    def apply_state(self, snap: dict):
        """NetworkState 更新回调：只在数据变化时重建列表"""
        ifaces = snap.get("ifaces") or []
        if snap.get("refreshing") and not ifaces:
            return
        self._filled(list(ifaces))

    def _apply_interval(self):
        pass  # 刷新节奏由 NetworkState 统一调度

    def reload_settings(self):
        self._load_snapshot_if_stale()

    def _load_snapshot_if_stale(self):
        pass

    def on_show(self):
        self.refresh()

    def refresh(self):
        self._auto = False
        if self.state is not None:
            self.state.refresh()      # 更新后经 apply_state 回填
        else:
            self._start_load()

    def _auto_refresh(self):
        self._auto = True
        if self.state is not None:
            self.state.refresh()
        else:
            self._start_load()

    # ---------------- UI ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(14)

        self.header = PageHeader("网卡管理", "选择左侧网卡，右侧修改配置并预览后应用")
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.header.add_action(self.btn_refresh)
        self.badge_global = StatusBadge("检测中", "muted")
        self.header.add_action(self.badge_global)
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setSpacing(16)

        # ---- 左：网卡列表 ----
        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(272)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 12, 10, 10)
        lv.setSpacing(8)
        lt = QLabel("网卡")
        lt.setObjectName("sectionTitle")
        lt.setContentsMargins(6, 0, 0, 0)
        lv.addWidget(lt)
        self.list = QListWidget()
        self.list.setObjectName("adapterList")
        self.list.setSpacing(2)
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.currentRowChanged.connect(self._row_changed)
        lv.addWidget(self.list, 1)
        self.lbl_count = QLabel("—")
        self.lbl_count.setObjectName("hint")
        self.lbl_count.setContentsMargins(6, 0, 0, 0)
        lv.addWidget(self.lbl_count)
        body.addWidget(left)

        # ---- 右：详情 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("root")
        self.detail = QVBoxLayout(inner)
        self.detail.setContentsMargins(0, 0, 6, 0)
        self.detail.setSpacing(16)
        scroll.setWidget(inner)
        body.addWidget(scroll, 1)
        root.addLayout(body, 1)

        self._build_basic()
        self._build_ipv4()
        self._build_alias()
        self._build_presets()
        self.detail.addStretch(1)

    def _build_basic(self):
        card = Card("基本信息", "来自 networksetup / ifconfig 的实时状态")
        self.badge_iface = StatusBadge("", "muted")
        card.add_action(self.badge_iface)
        self.btn_toggle = QPushButton("禁用网卡")
        self.btn_toggle.clicked.connect(self._toggle_iface)
        card.add_action(self.btn_toggle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        self._kv = {}
        fields = [("服务名称", 0, 0), ("设备接口", 0, 1), ("硬件端口", 0, 2),
                  ("MAC 地址", 1, 0), ("当前 IP", 1, 1), ("默认网关", 1, 2),
                  ("链路速率", 2, 0), ("连接状态", 2, 1), ("类型", 2, 2)]
        for label, r, c in fields:
            lb = QLabel(label)
            lb.setObjectName("hint")
            val = QLabel("—")
            val.setObjectName("value")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            val.setWordWrap(True)
            grid.addWidget(lb, r, c)
            grid.addWidget(val, r + 3, c)
            self._kv[label] = val
        for c in range(3):
            grid.setColumnStretch(c, 1)
        card.add_layout(grid)
        self.detail.addWidget(card)

    def _build_ipv4(self):
        card = Card("IPv4 配置", "修改后先预览变更，确认后才会写入系统")
        self.seg_mode = Segmented(["手动配置", "自动 DHCP"])
        self.seg_mode.changed.connect(self._seg_changed)
        card.add_action(self.seg_mode)

        self.form = FormGrid(2)
        self.ed_ip = QLineEdit()
        self.ed_ip.setPlaceholderText("192.168.1.100")
        self.ed_mask = QLineEdit()
        self.ed_mask.setPlaceholderText("255.255.255.0 或 24")
        self.ed_gw = QLineEdit()
        self.ed_gw.setPlaceholderText("192.168.1.1")
        self.ed_dns = QLineEdit()
        self.ed_dns.setPlaceholderText("多个用逗号分隔，留空表示自动获取")
        self.form.add_pair("IP 地址", self.ed_ip, "子网掩码", self.ed_mask)
        self.form.add_pair("默认网关", self.ed_gw, "DNS", self.ed_dns)
        card.add(self.form)

        self.lbl_ipv4_hint = QLabel("应用前会展示变更预览；修改前的配置会保存，可随时恢复。")
        self.lbl_ipv4_hint.setObjectName("hint")
        self.lbl_ipv4_hint.setWordWrap(True)
        card.add(self.lbl_ipv4_hint)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_preview = QPushButton("预览变更")
        self.btn_preview.clicked.connect(lambda: self._apply(force_preview=True))
        self.btn_apply = QPushButton("应用配置")
        self.btn_apply.setProperty("variant", "primary")
        self.btn_apply.clicked.connect(lambda: self._apply())
        self.btn_revert = QPushButton("恢复原始配置")
        self.btn_revert.setProperty("variant", "ghost")
        self.btn_revert.clicked.connect(self._revert)
        actions.addWidget(self.btn_preview)
        actions.addWidget(self.btn_apply)
        actions.addStretch(1)
        actions.addWidget(self.btn_revert)
        card.add_layout(actions)
        self.card_ipv4 = card
        self.detail.addWidget(card)

    def _build_alias(self):
        card = Card("多 IP 管理", "同一网卡追加多个地址，不影响主 IP")
        self.tbl_alias = QTableWidget(0, 2)
        self.tbl_alias.setHorizontalHeaderLabels(["附加 IP 地址", "类型"])
        self.tbl_alias.verticalHeader().setVisible(False)
        self.tbl_alias.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_alias.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_alias.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_alias.verticalHeader().setDefaultSectionSize(30)
        hdr = self.tbl_alias.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_alias.setMinimumHeight(132)
        card.add(self.tbl_alias, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        for text, slot in (("添加 IP", self._add_alias), ("批量添加", self._bulk_alias),
                           ("删除选中", self._del_alias), ("清空附加 IP", self._clear_alias)):
            btn = QPushButton(text)
            if text in ("删除选中", "清空附加 IP"):
                btn.setProperty("variant", "danger")
            btn.clicked.connect(slot)
            actions.addWidget(btn)
        actions.addStretch(1)
        card.add_layout(actions)
        self.detail.addWidget(card)

    def _build_presets(self):
        card = Card("IP 方案", "保存常用组合，一键切换（托盘菜单也可切换）")
        self.tbl_preset = QTableWidget(0, 4)
        self.tbl_preset.setHorizontalHeaderLabels(["名称", "网卡", "方式", "IP / 掩码"])
        self.tbl_preset.verticalHeader().setVisible(False)
        self.tbl_preset.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_preset.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_preset.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_preset.verticalHeader().setDefaultSectionSize(30)
        hdr = self.tbl_preset.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tbl_preset.setMinimumHeight(126)
        card.add(self.tbl_preset, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_preset_save = QPushButton("保存当前配置为方案")
        self.btn_preset_save.clicked.connect(self._save_preset)
        self.btn_preset_apply = QPushButton("应用方案")
        self.btn_preset_apply.setProperty("variant", "primary")
        self.btn_preset_apply.clicked.connect(self._apply_preset)
        self.btn_preset_del = QPushButton("删除方案")
        self.btn_preset_del.setProperty("variant", "danger")
        self.btn_preset_del.clicked.connect(self._delete_preset)
        actions.addWidget(self.btn_preset_save)
        actions.addStretch(1)
        actions.addWidget(self.btn_preset_apply)
        actions.addWidget(self.btn_preset_del)
        card.add_layout(actions)
        self.detail.addWidget(card)

    # ---------------- 刷新（数据由 apply_state 注入） ----------------
    def _start_load(self):
        """无共享状态时的兜底：直接读后端"""
        if any(w.isRunning() for w in self._workers):
            return
        if not self._auto:
            self.btn_refresh.setEnabled(False)
        w = Worker(self.backend.list_interfaces)
        w.ok.connect(self._filled)
        w.err.connect(self._load_err)
        w.start()
        self._workers.append(w)

    def _filled(self, ifaces):
        self.btn_refresh.setEnabled(True)
        ifaces = sort_interfaces(ifaces)
        old_sig = [(i.get("device"), i.get("ipv4"), i.get("status")) for i in self.ifaces]
        new_sig = [(i.get("device"), i.get("ipv4"), i.get("status")) for i in ifaces]
        self.ifaces = ifaces
        self.badge_global.set_state(f"{len(ifaces)} 个网卡", "ok" if ifaces else "warn")
        self.lbl_count.setText(f"共 {len(ifaces)} 个 · 每 {settings.get('refresh_interval')} 秒自动检测")

        keep = self.current.get("service") if self.current else settings.get("default_iface")
        self.list.blockSignals(True)
        self.list.clear()
        for i in ifaces:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 50))
            item.setData(Qt.UserRole, i.get("service") or i.get("port"))
            self.list.addItem(item)
            self.list.setItemWidget(item, AdapterRow(i))

        idx = 0
        for r, i in enumerate(ifaces):
            if keep and (i.get("service") == keep or i.get("port") == keep):
                idx = r
                break
        if ifaces:
            self.list.setCurrentRow(idx)
        self.list.blockSignals(False)

        if ifaces:
            selected = ifaces[idx]
            same = (self.current and self.current.get("service") == selected.get("service"))
            if not same:
                self._row_changed(idx)
            elif self.current:
                # 同一网卡：只更新状态信息，不重建表单（避免覆盖正在输入的内容）
                self.current = selected
                self._fill_basic(selected)
        else:
            self.current = None
        self._fill_presets()
        if self.ifaces != getattr(self, "_last_emitted", None):
            self._last_emitted = self.ifaces
            self.ifaces_changed.emit(ifaces)
        if not self._auto:
            self.log(f"网卡列表已刷新，共 {len(ifaces)} 个接口", "INFO")

    def _load_err(self, msg):
        self.btn_refresh.setEnabled(True)
        self.badge_global.set_state("读取失败", "err")
        if not self._auto:
            self.notify(f"读取网卡失败：{msg}", "err")
        self.log(f"读取网卡失败: {msg}", "ERROR")

    # ---------------- 选择网卡 ----------------
    def select_service(self, service: str):
        for r in range(self.list.count()):
            if self.list.item(r).data(Qt.UserRole) == service:
                self.list.setCurrentRow(r)
                return

    def _row_changed(self, row):
        if row < 0 or row >= len(self.ifaces):
            return
        ifc = self.ifaces[row]
        self.current = ifc
        self._seg_touched = False
        self._fill_basic(ifc)
        self._fill_form(ifc)
        self._load_aliases()

    def _fill_basic(self, ifc):
        self._kv["服务名称"].setText(ifc.get("service") or "—")
        self._kv["设备接口"].setText(ifc.get("device") or "—")
        self._kv["硬件端口"].setText(ifc.get("port") or "—")
        self._kv["MAC 地址"].setText(ifc.get("mac") or "—")
        self._kv["当前 IP"].setText(ifc.get("ipv4") or "未获取")
        self._kv["默认网关"].setText(ifc.get("router") or "—")
        status, state = {"up": ("已连接", "ok"), "down": ("断开", "warn"),
                         "absent": ("未插入", "warn")}.get(ifc.get("status"), ("未知", "muted"))
        self.badge_iface.set_state(status, state)
        self._kv["连接状态"].setText(status)
        self._kv["类型"].setText("外置 / USB" if iface_is_external(ifc) else "内置")
        enabled = ifc.get("enabled")
        self.btn_toggle.setText("禁用网卡" if enabled is not False else "启用网卡")
        self.btn_toggle.setEnabled(enabled is not None)
        self.btn_toggle.setProperty("variant", "danger" if enabled is not False else "primary")
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)
        self._kv["链路速率"].setText("读取中…")
        self._load_rate(ifc.get("device"))

    def _load_rate(self, device):
        if not device or not hasattr(self.backend, "link_info"):
            self._kv["链路速率"].setText("—")
            return

        def job():
            return self.backend.link_info(device)
        w = Worker(job)
        w.ok.connect(lambda text: self._kv["链路速率"].setText(text or "—"))
        w.err.connect(lambda _: self._kv["链路速率"].setText("—"))
        w.start()
        self._workers.append(w)

    def _fill_form(self, ifc):
        self.seg_mode.blockSignals(True)
        self.seg_mode.set_index(0 if self._mode_current == "static" else 1)
        self.seg_mode.blockSignals(False)
        self.ed_ip.setText(ifc.get("ipv4") or "")
        self.ed_mask.setText(ifc.get("mask") or "")
        self.ed_gw.setText(ifc.get("router") or "")
        self._load_mode(ifc)
        self._load_dns(ifc)
        self._mode_changed(self.seg_mode.index(), initial=True)

    def _load_mode(self, ifc):
        svc = ifc.get("service")
        if not svc or not hasattr(self.backend, "ip_mode"):
            self._mode_current = "static" if ifc.get("ipv4") else "dhcp"
            return

        def job():
            return self.backend.ip_mode(svc)

        w = Worker(job)
        w.ok.connect(self._mode_loaded)
        w.start()
        self._workers.append(w)

    def _mode_loaded(self, mode):
        self._mode_current = mode or "static"
        if not self._seg_touched:
            self.seg_mode.blockSignals(True)
            self.seg_mode.set_index(0 if self._mode_current == "static" else 1)
            self.seg_mode.blockSignals(False)
            self._mode_changed(self.seg_mode.index())

    def _load_dns(self, ifc):
        svc = ifc.get("service") or ifc.get("port")
        if not svc:
            return

        def job():
            return self.backend.get_dns(svc)

        w = Worker(job)
        w.ok.connect(self._dns_loaded)
        w.err.connect(lambda _: self._dns_loaded([]))
        w.start()
        self._workers.append(w)

    def _dns_loaded(self, dns):
        self._dns_cache = list(dns or [])
        self.ed_dns.setText(", ".join(self._dns_cache))

    def _mode_changed(self, idx, initial=False):
        manual = idx == 0
        for w in (self.ed_ip, self.ed_mask, self.ed_gw):
            w.setEnabled(manual)
        self.btn_preview.setEnabled(manual)
        self.lbl_ipv4_hint.setText(
            "应用前会展示变更预览；修改前的配置会保存，可随时恢复。"
            if manual else
            "自动 DHCP：应用后由路由器下发地址，手动填写的 IP 不会生效。")

    def _seg_changed(self, idx):
        self._seg_touched = True
        self._mode_changed(idx)

    # ---------------- 附加 IP ----------------
    def _load_aliases(self):
        if not self.current:
            return
        dev = self.current.get("device")

        def job():
            if hasattr(self.backend, "device_exists") and not self.backend.device_exists(dev):
                return []
            return self.backend.list_alias_ips(dev)

        w = Worker(job)
        w.ok.connect(self._fill_aliases)
        w.err.connect(lambda m: self._fill_aliases([]))
        w.start()
        self._workers.append(w)

    def _fill_aliases(self, aliases):
        self.tbl_alias.setRowCount(0)
        for ip in aliases or []:
            r = self.tbl_alias.rowCount()
            self.tbl_alias.insertRow(r)
            it = QTableWidgetItem(ip)
            f = it.font()
            f.setFamily("Menlo")
            it.setFont(f)
            self.tbl_alias.setItem(r, 0, it)
            self.tbl_alias.setItem(r, 1, QTableWidgetItem("ifconfig alias"))

    def _device_ok(self) -> bool:
        ifc = self.current
        if not ifc:
            self.notify("请先选择网卡", "warn")
            return False
        if ifc.get("status") == "absent":
            self.notify(f"接口 {ifc.get('device')} 不存在——USB 网卡未插入", "err")
            return False
        if hasattr(self.backend, "device_exists") and not self.backend.device_exists(ifc["device"]):
            self.notify(f"接口 {ifc['device']} 不存在——请先插好网卡", "err")
            return False
        return True

    def _add_alias(self):
        if not self._device_ok():
            return
        dlg = AliasDialog(self, self.current["device"])
        while True:
            if not dlg.exec():
                return
            try:
                ip, mask = dlg.values()
                break
            except ValueError as e:
                dlg.err.setText(str(e))
                continue
        dev = self.current["device"]

        def job():
            self.backend.add_alias_ip(dev, ip, mask)
            return True
        w = Worker(job)
        w.ok.connect(lambda _: self._alias_done(f"已添加附加 IP {ip}", "添加附加 IP",
                                                f"{dev} +{ip}/{mask}"))
        w.err.connect(lambda m: self.notify(f"添加失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _alias_done(self, text, action, after):
        history.record(action, self.current.get("service", "") if self.current else "",
                       "", after, "成功", "")
        self.notify(text)
        self._load_aliases()
        self.refresh()

    def _bulk_alias(self):
        if not self._device_ok():
            return
        dlg = BulkAliasDialog(self, self.current["device"])
        if not dlg.exec():
            return
        try:
            rows = dlg.values()
        except ValueError as e:
            self.notify(str(e), "err")
            return
        dev = self.current["device"]

        def job():
            ok, failed = 0, []
            for ip, mask in rows:
                try:
                    self.backend.add_alias_ip(dev, ip, mask)
                    ok += 1
                except Exception as e:
                    failed.append(f"{ip}: {e}")
            return ok, failed

        w = Worker(job)
        w.ok.connect(self._bulk_done)
        w.err.connect(lambda m: self.notify(f"批量添加失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _bulk_done(self, result):
        ok, failed = result
        history.record("批量添加附加 IP", self.current.get("service", "") if self.current else "",
                       "", f"成功 {ok} 个", "成功" if not failed else "部分失败",
                       "；".join(failed[:3]))
        self.notify(f"已添加 {ok} 个附加 IP" + (f"，失败 {len(failed)} 个" if failed else ""),
                    "ok" if not failed else "warn")
        self._load_aliases()
        self.refresh()

    def _del_alias(self):
        row = self.tbl_alias.currentRow()
        if row < 0:
            self.notify("请先选中要删除的附加 IP", "warn")
            return
        ip = self.tbl_alias.item(row, 0).text()
        if not self._device_ok():
            return
        if not confirm(self, "删除附加 IP", f"确定从接口 {self.current['device']} 删除 {ip} 吗？",
                       "删除", danger=True):
            return
        dev = self.current["device"]

        def job():
            self.backend.remove_alias_ip(dev, ip)
            return True
        w = Worker(job)
        w.ok.connect(lambda _: self._alias_done(f"已删除附加 IP {ip}", "删除附加 IP", f"{dev} -{ip}"))
        w.err.connect(lambda m: self.notify(f"删除失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _clear_alias(self):
        if not self._device_ok():
            return
        aliases = [self.tbl_alias.item(r, 0).text() for r in range(self.tbl_alias.rowCount())]
        if not aliases:
            self.notify("当前没有附加 IP", "info")
            return
        if not confirm(self, "清空附加 IP",
                       f"将删除 {self.current['device']} 上的 {len(aliases)} 个附加地址，是否继续？",
                       "全部删除", danger=True):
            return
        dev = self.current["device"]

        def job():
            for ip in aliases:
                self.backend.remove_alias_ip(dev, ip)
            return len(aliases)
        w = Worker(job)
        w.ok.connect(lambda n: self._alias_done(f"已清空 {n} 个附加 IP", "清空附加 IP",
                                               f"{dev} 删除 {n} 个别名"))
        w.err.connect(lambda m: self.notify(f"清空失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    # ---------------- 主 IP ----------------
    def _changes(self) -> list:
        """对比当前系统配置与表单，返回 [(项目, 前, 后)]"""
        ifc = self.current
        if not ifc:
            return []
        changes = []
        if self.seg_mode.index() == 0:
            try:
                mask = normalize_mask(self.ed_mask.text())
            except ValueError as e:
                raise ValueError(f"子网掩码有误：{e}")
            ip = self.ed_ip.text().strip()
            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                raise ValueError("IP 地址格式无效")
            gw = self.ed_gw.text().strip()
            if gw:
                try:
                    ipaddress.IPv4Address(gw)
                except ValueError:
                    raise ValueError("网关格式无效")
            if ip != (ifc.get("ipv4") or ""):
                changes.append(("IP 地址", ifc.get("ipv4") or "", ip))
            if mask != (ifc.get("mask") or ""):
                changes.append(("子网掩码", ifc.get("mask") or "", mask))
            if gw != (ifc.get("router") or ""):
                changes.append(("默认网关", ifc.get("router") or "", gw))
        else:
            if self._mode_current != "dhcp":
                changes.append(("配置方式", "手动", "自动 DHCP"))
        dns_new = [x.strip() for x in self.ed_dns.text().replace("，", ",").split(",") if x.strip()]
        dns_old = [x.strip() for x in (self._dns_cache or [])]
        if dns_new != dns_old:
            changes.append(("DNS", ", ".join(dns_old) or "自动", ", ".join(dns_new) or "自动"))
        return changes

    def _apply(self, force_preview: bool = False):
        if not self.current:
            self.notify("请先选择网卡", "warn")
            return
        ifc = self.current
        if ifc.get("status") == "absent":
            self.notify("网卡未插入，无法应用配置", "err")
            return
        try:
            changes = self._changes()
        except ValueError as e:
            self.notify(str(e), "err")
            return
        if not changes:
            self.notify("配置没有变化", "info")
            return
        svc = ifc.get("service") or ifc.get("port")
        if not ChangePreview(self, svc, changes,
                             "应用后会立即生效；原始配置已保存，可在本页恢复。").exec():
            return
        mode = "static" if self.seg_mode.index() == 0 else "dhcp"
        try:
            mask = normalize_mask(self.ed_mask.text()) if mode == "static" else ""
        except ValueError as e:
            self.notify(str(e), "err")
            return
        ip = self.ed_ip.text().strip() if mode == "static" else ""
        gw = self.ed_gw.text().strip() if mode == "static" else ""
        dns = [x.strip() for x in self.ed_dns.text().replace("，", ",").split(",") if x.strip()]
        before = (f"{ifc.get('ipv4') or '无 IP'} {ifc.get('mask') or ''} "
                  f"网关 {ifc.get('router') or '—'} DNS {', '.join(self._dns_cache or []) or '自动'}")

        # 修改前保存原始快照（仅首次，避免覆盖最早的原始配置）
        if svc not in self._snapshots:
            save_snapshot(svc, {
                "mode": "static" if ifc.get("ipv4") else "dhcp",
                "ip": ifc.get("ipv4") or "", "mask": ifc.get("mask") or "",
                "router": ifc.get("router") or "", "dns": list(self._dns_cache or []),
            })
            self._snapshots = load_snapshots()

        def job():
            if mode == "static":
                self.backend.set_static_ip(svc, ip, mask, gw)
            else:
                self.backend.set_dhcp(svc)
            self.backend.set_dns(svc, dns)
            return True

        self.btn_apply.setEnabled(False)
        w = Worker(job)
        w.ok.connect(lambda _: self._apply_done(svc, mode, ip, mask, gw, dns, before))
        w.err.connect(lambda m: self._apply_err(m))
        w.start()
        self._workers.append(w)

    def _apply_done(self, svc, mode, ip, mask, gw, dns, before):
        self.btn_apply.setEnabled(True)
        after = (f"{ip} {mask} 网关 {gw or '—'} DNS {', '.join(dns) or '自动'}"
                 if mode == "static" else f"DHCP 自动获取，DNS {', '.join(dns) or '自动'}")
        history.record("修改 IPv4 配置", svc, before, after, "成功", "")
        self.notify("配置已生效")
        self.refresh()

    def _apply_err(self, msg):
        self.btn_apply.setEnabled(True)
        history.record("修改 IPv4 配置",
                       self.current.get("service", "") if self.current else "",
                       "", "", "失败", str(msg)[:200])
        self.notify(f"应用失败：{msg}", "err")

    def _revert(self):
        if not self.current:
            return
        svc = self.current.get("service") or self.current.get("port")
        snap = load_snapshots().get(svc)
        if not snap:
            self.notify("没有保存过该网卡的原始配置", "info")
            return
        detail = (f"{snap.get('ip') or 'DHCP'} {snap.get('mask') or ''} "
                  f"网关 {snap.get('router') or '—'}")
        if not confirm(self, "恢复原始配置", f"将把「{svc}」恢复为：\n{detail}\n\n是否继续？",
                       "恢复"):
            return

        def job():
            if snap.get("mode") == "static" and snap.get("ip"):
                self.backend.set_static_ip(svc, snap["ip"], snap.get("mask") or "255.255.255.0",
                                           snap.get("router") or "")
            else:
                self.backend.set_dhcp(svc)
            if snap.get("dns") is not None:
                self.backend.set_dns(svc, snap.get("dns") or [])
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._revert_done(svc, detail))
        w.err.connect(lambda m: self.notify(f"恢复失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _revert_done(self, svc, detail):
        history.record("恢复原始配置", svc, "当前配置", detail, "成功", "")
        self.notify("已恢复原始配置")
        self.refresh()

    # ---------------- 启停网卡 ----------------
    def _toggle_iface(self):
        if not self.current:
            return
        svc = self.current.get("service") or self.current.get("port")
        enable = self.current.get("enabled") is False
        action = "启用" if enable else "禁用"
        if not confirm(self, f"{action}网卡", f"确定要{action}「{svc}」吗？", action,
                       danger=not enable):
            return

        def job():
            self.backend.enable_interface(svc, enable)
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._toggle_done(svc, action))
        w.err.connect(lambda m: self.notify(f"{action}失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _toggle_done(self, svc, action):
        history.record(f"{action}网卡", svc, "", "", "成功", "")
        self.notify(f"已{action}「{svc}」")
        self.refresh()

    # ---------------- 方案 ----------------
    def _fill_presets(self):
        presets = preset_store.load_presets()
        self.tbl_preset.setRowCount(0)
        for p in presets:
            r = self.tbl_preset.rowCount()
            self.tbl_preset.insertRow(r)
            vals = [p.get("name", ""), p.get("service", ""),
                    "手动" if p.get("mode") == "static" else "DHCP",
                    f"{p.get('ip', '')}/{p.get('mask', '')}" if p.get("mode") == "static" else "—"]
            for c, v in enumerate(vals):
                self.tbl_preset.setItem(r, c, QTableWidgetItem(str(v)))

    def _save_preset(self):
        if not self.current:
            self.notify("请先选择网卡", "warn")
            return
        services = [(f"{i.get('service') or i.get('port')} ({i.get('device')})",
                     i.get("service") or i.get("port")) for i in self.ifaces]
        data = {
            "service": self.current.get("service") or self.current.get("port"),
            "mode": "static" if self.seg_mode.index() == 0 else "dhcp",
            "ip": self.ed_ip.text().strip(),
            "mask": self.ed_mask.text().strip(),
            "router": self.ed_gw.text().strip(),
            "dns": [x.strip() for x in self.ed_dns.text().replace("，", ",").split(",") if x.strip()],
        }
        dlg = PresetDialog(self, services, data)
        if not dlg.exec():
            return
        try:
            p = dlg.result_preset()
        except ValueError as e:
            self.notify(str(e), "err")
            return
        err = preset_store.validate_preset(p)
        if err:
            self.notify(err, "err")
            return
        items = preset_store.load_presets()
        items.append(p)
        preset_store.save_presets(items)
        history.record("保存 IP 方案", p["service"], "", p["name"], "成功", "")
        self.notify(f"方案「{p['name']}」已保存")
        self._fill_presets()

    def _apply_preset(self):
        row = self.tbl_preset.currentRow()
        presets = preset_store.load_presets()
        if row < 0 or row >= len(presets):
            self.notify("请先选中一个方案", "warn")
            return
        p = presets[row]
        if not confirm(self, "应用方案",
                       f"将「{p['name']}」应用到「{p['service']}」？\n"
                       f"{p.get('ip') or 'DHCP'} {p.get('mask') or ''}", "应用"):
            return

        def job():
            if p.get("mode") == "static":
                self.backend.set_static_ip(p["service"], p.get("ip", ""),
                                           p.get("mask", "255.255.255.0"),
                                           p.get("router", ""))
            else:
                self.backend.set_dhcp(p["service"])
            if p.get("dns"):
                self.backend.set_dns(p["service"], p["dns"])
            return True

        w = Worker(job)
        w.ok.connect(lambda _: self._preset_applied(p))
        w.err.connect(lambda m: self.notify(f"应用失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _preset_applied(self, p):
        history.record("应用 IP 方案", p["service"], "", p["name"], "成功", "")
        self.notify(f"已应用「{p['name']}」")
        self.refresh()

    def _delete_preset(self):
        row = self.tbl_preset.currentRow()
        presets = preset_store.load_presets()
        if row < 0 or row >= len(presets):
            self.notify("请先选中一个方案", "warn")
            return
        p = presets[row]
        if not confirm(self, "删除方案", f"删除方案「{p['name']}」？此操作不可恢复。",
                       "删除", danger=True):
            return
        presets.pop(row)
        preset_store.save_presets(presets)
        self.notify("方案已删除")
        self._fill_presets()

    # -------- DNS 缓存（用于计算变更） --------
    _dns_cache = None

    def _set_dns_cache(self, dns):
        self._dns_cache = list(dns or [])

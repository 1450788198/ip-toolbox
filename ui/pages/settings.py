"""设置：外观、自动刷新、默认网卡、启动选项、Touch ID 与免密授权、关于"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QVBoxLayout)

from core import history, settings
from core.netbase import IS_MAC, sort_interfaces
from ..common import Worker
from ..components import Card, Segmented, StatusBadge
from ..dialogs import confirm
from .base import ScrollPage

VERSION = "1.1.1"
APPEARANCE = ["system", "light", "dark"]


class SettingsPage(ScrollPage):
    settings_applied = Signal()

    def __init__(self, backend, log, notify, parent=None):
        super().__init__("设置", "外观、刷新频率、默认网卡与安全授权")
        self.backend = backend
        self.log = log
        self.notify = notify
        self._workers = []
        self.cfg = settings.load()
        self._build()
        self._load_states()

    # ---------------- UI ----------------
    def _build(self):
        # ---- 外观 ----
        look = Card("外观", "浅色 / 深色跟随系统，或手动指定")
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel("主题"))
        self.seg_theme = Segmented(["跟随系统", "浅色", "深色"])
        self.seg_theme.set_index(APPEARANCE.index(self.cfg.get("appearance", "system")))
        self.seg_theme.changed.connect(self._theme_changed)
        row.addWidget(self.seg_theme)
        row.addStretch(1)
        look.add_layout(row)
        hint = QLabel("深色模式会同步应用到表格、输入框、菜单与状态栏。")
        hint.setObjectName("hint")
        look.add(hint)
        self.body.addWidget(look)

        # ---- 通用 ----
        general = Card("通用", "自动检测网卡与启动行为")
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel("自动刷新间隔"))
        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(2, 30)
        self.sp_interval.setValue(int(self.cfg.get("refresh_interval") or 4))
        self.sp_interval.setSuffix(" 秒")
        self.sp_interval.setMinimumWidth(96)
        self.sp_interval.valueChanged.connect(self._interval_changed)
        row.addWidget(self.sp_interval)
        row.addStretch(1)
        general.add_layout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(QLabel("默认网卡"))
        self.cmb_default = QComboBox()
        self.cmb_default.setMinimumWidth(300)
        self.cmb_default.addItem("自动（优先外置网卡）", "")
        self.cmb_default.currentIndexChanged.connect(self._default_changed)
        row2.addWidget(self.cmb_default)
        row2.addStretch(1)
        general.add_layout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(12)
        row3.addWidget(QLabel("菜单栏图标"))
        self.cmb_menubar = QComboBox()
        self.cmb_menubar.addItem("网络节点图标", "icon")
        self.cmb_menubar.addItem("连接状态", "status")
        self.cmb_menubar.addItem("当前 IP 网段", "ip")
        self.cmb_menubar.addItem("当前网卡", "iface")
        cur = self.cfg.get("menu_bar_icon", "icon")
        self.cmb_menubar.setCurrentIndex(
            max(0, self.cmb_menubar.findData(cur)))
        self.cmb_menubar.setMinimumWidth(160)
        self.cmb_menubar.currentIndexChanged.connect(self._menubar_changed)
        row3.addWidget(self.cmb_menubar)
        row3.addStretch(1)
        general.add_layout(row3)

        self.chk_min = QCheckBox("启动时只驻留菜单栏（不显示主窗口）")
        self.chk_min.setChecked(bool(self.cfg.get("start_minimized")))
        self.chk_min.toggled.connect(
            lambda v: self._save("start_minimized", v))
        general.add(self.chk_min)

        self.chk_confirm = QCheckBox("危险操作前二次确认（删除路由 / 清空附加 IP 等）")
        self.chk_confirm.setChecked(bool(self.cfg.get("confirm_dangerous", True)))
        self.chk_confirm.toggled.connect(
            lambda v: self._save("confirm_dangerous", v))
        general.add(self.chk_confirm)
        self.body.addWidget(general)

        # ---- 安全与权限 ----
        sec = Card("安全与权限", "Touch ID 解锁与 sudoers 白名单授权")
        r1 = QHBoxLayout()
        r1.setSpacing(10)
        r1.addWidget(QLabel("Touch ID"))
        self.badge_touch = StatusBadge("检测中", "muted")
        r1.addWidget(self.badge_touch)
        r1.addStretch(1)
        self.btn_touch = QPushButton("测试指纹")
        self.btn_touch.clicked.connect(self._test_touch)
        r1.addWidget(self.btn_touch)
        sec.add_layout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(10)
        r2.addWidget(QLabel("免密授权"))
        self.badge_elev = StatusBadge("检测中", "muted")
        r2.addWidget(self.badge_elev)
        r2.addStretch(1)
        self.btn_enable = QPushButton("开启免密")
        self.btn_enable.setProperty("variant", "primary")
        self.btn_enable.clicked.connect(self._enable_elev)
        self.btn_revoke = QPushButton("撤销授权")
        self.btn_revoke.setProperty("variant", "danger")
        self.btn_revoke.clicked.connect(self._revoke_elev)
        r2.addWidget(self.btn_enable)
        r2.addWidget(self.btn_revoke)
        sec.add_layout(r2)

        note = QLabel("原理：写入 /etc/sudoers.d/ip-toolbox 命令白名单，仅放行 "
                      "networksetup / ifconfig / route，之后修改网卡、路由、DHCP 不再弹密码。"
                      "删除该文件即可撤销。")
        note.setObjectName("hint")
        note.setWordWrap(True)
        sec.add(note)
        self.body.addWidget(sec)

        # ---- 关于 ----
        about = Card("关于", f"IP 工具箱 v{VERSION}")
        info = QLabel(
            "面向网络运维与现场交付的 macOS 原生 IP 工具：多 IP 配置、路由管理、"
            "内置 DHCP 服务、子网计算与 VLSM 划分、国内分省运营商 DNS 测速。\n\n"
            "开源地址：https://github.com/1450788198/ip-toolbox\n"
            "License：MIT　·　技术栈：Python + PySide6")
        info.setObjectName("hint")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        about.add(info)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_hist = QPushButton("查看操作记录")
        btn_hist.clicked.connect(lambda: self._goto_history())
        row.addWidget(btn_hist)
        about.add_layout(row)
        self.body.addWidget(about)

    # ---------------- 状态 ----------------
    def on_show(self):
        self._load_states()

    def _load_states(self):
        from core.biometric import biometry_available
        from core.elevation import is_installed

        def job():
            touch = biometry_available() if IS_MAC else False
            elev = is_installed() if IS_MAC else False
            if getattr(self, "state", None) is not None and self.state.ifaces():
                ifaces = self.state.ifaces()
            else:
                ifaces = sort_interfaces(self.backend.list_interfaces())
            return touch, elev, ifaces

        w = Worker(job)
        w.ok.connect(self._states)
        w.err.connect(lambda _: self._states((False, False, [])))
        w.start()
        self._workers.append(w)

    def _states(self, data):
        touch, elev, ifaces = data
        self.badge_touch.set_state("可用" if touch else "不可用", "ok" if touch else "muted")
        self.btn_touch.setEnabled(bool(touch))
        self.badge_elev.set_state("已开启" if elev else "未开启", "ok" if elev else "warn")
        self.btn_enable.setEnabled(not elev)
        self.btn_revoke.setEnabled(bool(elev))

        current = self.cfg.get("default_iface") or ""
        self.cmb_default.blockSignals(True)
        self.cmb_default.clear()
        self.cmb_default.addItem("自动（优先外置网卡）", "")
        for i in ifaces:
            label = f"{i.get('service') or i.get('port')} ({i.get('device')})"
            self.cmb_default.addItem(label, i.get("service") or i.get("port"))
        idx = self.cmb_default.findData(current)
        self.cmb_default.setCurrentIndex(max(0, idx))
        self.cmb_default.blockSignals(False)

    # ---------------- 保存 ----------------
    def _save(self, key, value):
        self.cfg[key] = value
        settings.set_value(key, value)
        self.settings_applied.emit()

    def _theme_changed(self, idx):
        mode = APPEARANCE[idx]
        self._save("appearance", mode)
        from .. import theme
        theme.current().apply(mode)

    def _interval_changed(self, value):
        self._save("refresh_interval", int(value))

    def _default_changed(self, _idx):
        self._save("default_iface", self.cmb_default.currentData() or "")

    def _menubar_changed(self, _idx):
        self._save("menu_bar_icon", self.cmb_menubar.currentData() or "icon")

    def _goto_history(self):
        win = self.window()
        if hasattr(win, "go_to"):
            win.go_to("history")

    # ---------------- 安全操作 ----------------
    def _test_touch(self):
        from core.biometric import authenticate
        self.btn_touch.setEnabled(False)

        def job():
            ok, err = authenticate("测试 Touch ID")
            return ok, err

        w = Worker(job)
        w.ok.connect(self._touch_result)
        w.err.connect(lambda m: (self.btn_touch.setEnabled(True),
                                 self.notify(f"指纹验证失败：{m}", "err")))
        w.start()
        self._workers.append(w)

    def _touch_result(self, result):
        self.btn_touch.setEnabled(True)
        ok, err = result
        if ok:
            self.notify("Touch ID 验证通过")
        else:
            self.notify(f"验证未通过：{err or '已取消'}", "err")

    def _enable_elev(self):
        if not IS_MAC:
            self.notify("免密授权仅支持 macOS", "info")
            return
        from core.elevation import install

        def job():
            return install()

        w = Worker(job)
        w.ok.connect(lambda _: self._elev_done(True))
        w.err.connect(lambda m: self.notify(f"授权失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _revoke_elev(self):
        if not confirm(self, "撤销免密授权",
                       "将删除 /etc/sudoers.d/ip-toolbox，之后每次操作会重新弹授权框。",
                       "撤销", danger=True):
            return
        from core.elevation import uninstall

        w = Worker(uninstall)
        w.ok.connect(lambda _: self._elev_done(False))
        w.err.connect(lambda m: self.notify(f"撤销失败：{m}", "err"))
        w.start()
        self._workers.append(w)

    def _elev_done(self, enabled):
        self._load_states()
        history.record("免密授权", "", "未开启" if enabled else "已开启",
                       "已开启" if enabled else "未开启", "成功", "设置页操作")
        self.notify("免密授权已开启" if enabled else "免密授权已撤销")

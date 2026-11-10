"""统一网络状态（Network State）：主窗口与菜单栏面板共享的唯一数据源

- 只有一个采集循环，避免主窗口/面板各自重复执行 ifconfig / networksetup
- 采集在后台线程执行，UI 线程零阻塞；失败时保留上一次有效数据并标记过期
- 任何消费方调用 refresh() 都合并为一次采集（防抖）
"""
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import settings
from .netbase import sort_interfaces


def _dhcp_running():
    try:
        from .dhcp_controller import DhcpController
        return bool(DhcpController().is_running())
    except Exception:
        return False


def _dhcp_state():
    try:
        from .dhcp_controller import DhcpController
        return DhcpController().read_state()
    except Exception:
        return {}


def _elevation_ok():
    try:
        from .elevation import is_installed
        return bool(is_installed())
    except Exception:
        return None


class NetworkState(QObject):
    updated = Signal(dict)          # snapshot（含 stale / refreshing 标记）
    refresh_started = Signal()
    _collected = Signal(object)     # (data, err) 内部：后台线程 → 主线程

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self._busy = False
        self._pending = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._collected.connect(self._on_collected)
        self._snap = {
            "ts": 0.0,              # 上次成功采集时间
            "stale": False,         # 上次采集失败 → 数据过期
            "error": "",
            "refreshing": False,
            "ifaces": [],
            "detail": {},           # svc → {mode,dns,aliases,ipv6,link}
            "dhcp_running": False,
            "dhcp_state": {},
            "elevation_ok": None,
            "presets": [],
        }

    # ---------- 对外查询 ----------
    def snapshot(self) -> dict:
        return self._snap

    def ifaces(self) -> list:
        return self._snap.get("ifaces") or []

    def detail(self, svc: str) -> dict:
        return (self._snap.get("detail") or {}).get(svc, {})

    # ---------- 采集调度 ----------
    def start(self):
        interval = max(3, int(settings.get("refresh_interval") or 4))
        self._timer.start(interval * 1000)
        self.refresh()

    def set_interval(self, seconds: int):
        seconds = max(3, int(seconds))
        if self._timer.isActive():
            self._timer.start(seconds * 1000)

    def stop(self):
        self._timer.stop()

    def refresh(self):
        """请求一次采集；正在采集时只置位 pending，不并发"""
        if self._busy:
            self._pending = True
            return
        self._busy = True
        self._snap["refreshing"] = True
        self.updated.emit(dict(self._snap))
        self.refresh_started.emit()

        def work():
            try:
                data, err = self._collect(), ""
            except Exception as e:            # 采集失败：保留旧数据
                data, err = None, str(e) or e.__class__.__name__
            self._collected.emit((data, err))  # 自动排队回主线程

        threading.Thread(target=work, daemon=True).start()

    def _on_collected(self, payload):
        data, err = payload
        if data is None:
            self._snap["stale"] = True
            self._snap["error"] = err
        else:
            self._snap.update(data)
            self._snap["stale"] = False
            self._snap["error"] = ""
        self._snap["refreshing"] = False
        self._busy = False
        self.updated.emit(dict(self._snap))
        if self._pending:                     # 采集期间有新请求 → 立即补一轮
            self._pending = False
            self.refresh()

    # ---------- 实际采集 ----------
    def _collect(self) -> dict:
        b = self.backend
        ifaces = sort_interfaces(b.list_interfaces())
        detail = {}
        for i in ifaces:
            svc, dev = i.get("service") or "", i.get("device") or ""
            d = {"mode": "", "dns": [], "aliases": [], "ipv6": [], "link": ""}
            if svc and hasattr(b, "ip_mode"):
                try:
                    d["mode"] = b.ip_mode(svc)
                except Exception:
                    pass
            if svc:
                try:
                    d["dns"] = b.get_dns(svc)
                except Exception:
                    pass
            if i.get("ipv4") and dev:
                try:
                    d["aliases"] = b.list_alias_ips(dev)
                except Exception:
                    pass
                try:
                    d["link"] = b.link_info(dev)
                except Exception:
                    pass
            if dev:
                try:
                    from .netinfo import ipv6_addresses
                    d["ipv6"] = ipv6_addresses(dev)
                except Exception:
                    pass
            detail[svc or dev] = d
        return {
            "ts": time.time(),
            "ifaces": ifaces,
            "detail": detail,
            "dhcp_running": _dhcp_running(),
            "dhcp_state": _dhcp_state(),
            "elevation_ok": _elevation_ok(),
            "presets": self._presets(),
        }

    @staticmethod
    def _presets() -> list:
        try:
            from . import presets
            return presets.load_presets()
        except Exception:
            return []

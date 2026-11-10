"""真机视觉验证：按真实托盘图标位置弹出面板并截屏

用于交付截图（浅色 / 深色 / 多网卡 / 多 IP），同时打印实际定位数值。

运行：
  .venv/bin/python tests/capture_real.py light docs/v1.1.1/panel-light.png
  .venv/bin/python tests/capture_real.py dark  docs/v1.1.1/panel-dark.png

截图方式：screencapture 全屏 → 按面板几何裁剪（Retina 下乘 dpr）。
屏幕锁定或无录屏权限时会输出提示，不伪造截图。
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

THEME = sys.argv[1] if len(sys.argv) > 1 else "light"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/panel.png"
SCENARIO = sys.argv[3] if len(sys.argv) > 3 else "single"
ACTIONS = (sys.argv[4].split(",") if len(sys.argv) > 4 else [])


def ifc(svc, dev, status="up", ip="10.0.0.2", mask="255.255.255.0",
        router="10.0.0.1", enabled=True):
    return {"service": svc, "device": dev, "port": dev, "status": status,
            "ipv4": ip, "mask": mask, "router": router, "mac": "f0:18:98:aa:bb:cc",
            "enabled": enabled}


SINGLE = dict(
    ifaces=[ifc("Wi-Fi", "en0", ip="10.200.254.89", mask="255.255.254.0",
                router="10.200.254.1")],
    detail={"Wi-Fi": {"mode": "dhcp", "dns": ["223.6.6.6", "114.114.114.114"],
                      "aliases": [], "ipv6": ["2408:8207:1234::5/64"], "link": ""}},
    presets=[{"name": "公司 DHCP", "service": "Wi-Fi", "mode": "dhcp", "ip": "",
              "mask": "", "router": "", "dns": []},
             {"name": "家里固定", "service": "Wi-Fi", "mode": "static",
              "ip": "192.168.50.176", "mask": "255.255.255.0",
              "router": "192.168.50.1", "dns": ["223.6.6.6"]}],
)

MULTI = dict(
    ifaces=[ifc("Wi-Fi", "en0", ip="10.200.254.89", mask="255.255.254.0",
                router="10.200.254.1"),
            ifc("USB 10/100/1G/2.5G LAN", "en5", ip="192.168.2.99"),
            ifc("USB-C LAN", "en7", status="down", ip="", mask="", router="")],
    detail={
        "Wi-Fi": {"mode": "dhcp", "dns": ["223.6.6.6", "114.114.114.114"],
                  "aliases": [], "ipv6": ["2408:8207:1234::5/64"], "link": ""},
        "USB 10/100/1G/2.5G LAN": {"mode": "static",
                                   "dns": ["218.30.19.40", "61.139.2.69"],
                                   "aliases": ["192.168.2.100", "192.168.2.101"],
                                   "ipv6": [], "link": "1000baseT 全双工"},
        "USB-C LAN": {"mode": "static", "dns": [], "aliases": [],
                      "ipv6": [], "link": ""},
    },
    presets=[{"name": "华为 iBMC", "service": "USB 10/100/1G/2.5G LAN",
              "mode": "static", "ip": "192.168.2.99", "mask": "255.255.255.0",
              "router": "192.168.2.1", "dns": []},
             {"name": "客户现场 A", "service": "USB 10/100/1G/2.5G LAN",
              "mode": "static", "ip": "172.16.10.20", "mask": "255.255.255.0",
              "router": "172.16.10.1", "dns": ["218.30.19.40"]}],
)


class DummyState:
    def __init__(self, s):
        self._s = s

    def snapshot(self):
        return self._s

    def refresh_if_older(self, seconds=2.0):
        pass


def main():
    app = QApplication(sys.argv[:1])
    from ui import theme
    from ui.menubar.panel import Panel

    theme.install(app, THEME)

    data = dict(SINGLE if SCENARIO == "single" else MULTI)
    data.update({"ts": 1.0, "stale": False, "error": "", "refreshing": False,
                 "dhcp_running": True,
                 "dhcp_state": {"config": {"start": "192.168.50.100",
                                           "end": "192.168.50.200"},
                                "leases": {"a": 1, "b": 2, "c": 3}},
                 "elevation_ok": True, "routes": []})

    tray = QSystemTrayIcon(app.style().standardIcon(
        app.style().StandardPixmap.SP_ComputerIcon), app)
    tray.show()

    panel = Panel(DummyState(data), popup=False)

    def shoot():
        # 后台进程的 Qt.Popup 会被 macOS 立即收回；真实使用中面板总是由
        # 用户点击菜单栏图标（激活应用）后弹出，这里模拟同样的前台状态。
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception as exc:
            print(f"WARN 激活进程失败：{exc}")
        geo = tray.geometry()
        rect = geo if (geo.isValid() and geo.width() > 0) else None
        print(f"tray.geometry={geo}  valid={geo.isValid()}")
        panel.show_at(None, rect)
        panel._relayout()
        # 交互动作（真实点击路径）：展开网卡 / 打开方案确认条
        if "expand" in ACTIONS:
            from ui.menubar.widgets import AdapterCard
            for c in panel.findChildren(AdapterCard):
                if (c.detail.get("aliases") or []) and not c.expanded:
                    c.set_expanded(True, animate=False)
        if "confirm" in ACTIONS and panel._chips:
            panel._preset_clicked(panel._chips[0])
        panel._relayout()
        print(f"panel.geometry={panel.geometry()}  visible={panel.isVisible()}")
        QTimer.singleShot(500, lambda: print("500ms 后仍可见:", panel.isVisible()))
        QTimer.singleShot(900, capture)

    def capture():
        os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
        full = "/tmp/_fullscreen.png"
        subprocess.run(["screencapture", "-x", full], check=False)
        try:
            from PySide6.QtGui import QImage
            img = QImage(full)
            if img.isNull():
                raise RuntimeError("读取系统截图失败（可能缺少录屏权限）")
            scr = app.primaryScreen()
            dpr = scr.devicePixelRatio()
            g = panel.frameGeometry()
            pad = 26
            # 截图含菜单栏：从屏幕顶部开始裁，便于交付「菜单栏 + 面板」上下文
            x0 = max(0, int((g.x() - pad) * dpr))
            y0 = 0
            x1 = min(img.width(), int((g.right() + pad) * dpr))
            y1 = min(img.height(), int((g.bottom() + pad) * dpr))
            crop = img.copy(x0, y0, x1 - x0, y1 - y0)
            crop.save(OUT)
            # 亮度检查：全黑说明屏幕锁定，不可作为交付截图
            gray = crop.convertToFormat(QImage.Format_Grayscale8)
            mx = 0
            for y in range(0, gray.height(), 40):
                for x in range(0, gray.width(), 40):
                    mx = max(mx, gray.pixelColor(x, y).red())
            print(f"captured -> {OUT}  region=({x0},{y0},{x1 - x0},{y1 - y0})  亮度峰值={mx}")
            if mx < 20:
                print("WARN 屏幕疑似锁定（截图近乎全黑），此图不可作为交付截图")
        except Exception as exc:
            print(f"ERROR 截图失败：{exc}")
        panel.close()
        app.quit()

    QTimer.singleShot(1200, shoot)
    app.exec()


if __name__ == "__main__":
    main()

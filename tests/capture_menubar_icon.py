"""菜单栏图标真机截图：把菜单栏图标设为真实 menubar_icon 输出后截取菜单栏区域

运行：.venv/bin/python tests/capture_menubar_icon.py light ip docs/v1.1.1/menubar-icon-light-ip.png
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

THEME = sys.argv[1] if len(sys.argv) > 1 else "light"
MODE = sys.argv[2] if len(sys.argv) > 2 else "ip"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/tmp/icon.png"


def main():
    app = QApplication(sys.argv[:1])
    from ui import theme
    from ui.menubar import menubar_icon
    theme.install(app, THEME)

    snap = {"ts": 1.0, "stale": False, "refreshing": False, "routes": [],
            "ifaces": [{"service": "Wi-Fi", "device": "en0", "status": "up",
                        "ipv4": "10.200.254.89", "mask": "255.255.254.0",
                        "router": "10.200.254.1", "mac": "aa:bb:cc:dd:ee:ff",
                        "enabled": True}],
            "detail": {}, "dhcp_running": False, "dhcp_state": {},
            "elevation_ok": True, "presets": []}

    tray = QSystemTrayIcon(menubar_icon(MODE, snap), app)
    tray.show()

    def capture():
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass
        os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
        g = tray.geometry()
        print("tray.geometry:", g)
        QTimer.singleShot(400, lambda: _shot(g))

    def _shot(g):
        full = "/tmp/_menubar_full.png"
        subprocess.run(["screencapture", "-x", full], check=False)
        from PySide6.QtGui import QImage
        img = QImage(full)
        if img.isNull():
            print("ERROR 截图失败")
            app.quit(); return
        dpr = app.primaryScreen().devicePixelRatio()
        if g.isValid() and g.width() > 0:
            x0 = max(0, int((g.x() - 140) * dpr))
            x1 = min(img.width(), int((g.right() + 140) * dpr))
            crop = img.copy(x0, 0, x1 - x0, int(30 * dpr))
        else:
            crop = img.copy(0, 0, min(1200, img.width()), int(30 * dpr))
        crop.save(OUT)
        print(f"captured -> {OUT} {crop.width()}x{crop.height()}")
        app.quit()

    QTimer.singleShot(1000, capture)
    app.exec()


if __name__ == "__main__":
    main()

"""面板冒烟测试（离屏）：增量更新 / 展开保持 / 滚动保持 / 确认条 / 定位计算

运行：QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_panel_smoke.py
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    ok = bool(cond)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {extra}"))
    if not ok:
        FAILS.append(name)


def ifc(svc, dev, status="up", ip="10.0.0.2", mask="255.255.255.0",
        router="10.0.0.1", enabled=True):
    return {"service": svc, "device": dev, "port": dev, "status": status,
            "ipv4": ip, "mask": mask, "router": router, "mac": "aa:bb:cc:00:11:22",
            "enabled": enabled}


def snap(ifaces, detail=None, **kw):
    s = {"ts": 1.0, "stale": False, "error": "", "refreshing": False,
         "ifaces": ifaces, "detail": detail or {}, "dhcp_running": False,
         "dhcp_state": {}, "elevation_ok": True, "presets": [],
         "routes": []}
    s.update(kw)
    return s


class DummyState:
    def __init__(self, s):
        self._s = s

    def snapshot(self):
        return copy.deepcopy(self._s)

    def refresh_if_older(self, seconds=2.0):
        pass

    def set(self, s):
        self._s = s


def main():
    app = QApplication(sys.argv)
    from ui.menubar.panel import Panel, AdapterCard  # noqa

    ifaces = [
        ifc("Wi-Fi", "en0", ip="10.200.254.89", mask="255.255.254.0", router="10.200.254.1"),
        ifc("USB 10/100/1G/2.5G LAN", "en5", status="absent", ip="192.168.2.99"),
        ifc("USB-C LAN", "en7", ip="192.168.50.20"),
    ]
    detail = {
        "Wi-Fi": {"mode": "dhcp", "dns": ["223.6.6.6", "114.114.114.114"],
                  "aliases": [], "ipv6": ["2408:8207::1/64", "fe80::1%en0"], "link": ""},
        "USB 10/100/1G/2.5G LAN": {"mode": "static", "dns": [], "aliases": [], "ipv6": [], "link": ""},
        "USB-C LAN": {"mode": "static", "dns": ["8.8.8.8"],
                      "aliases": ["192.168.50.21", "192.168.50.22"],
                      "ipv6": [], "link": "1000baseT 全双工"},
    }
    state = DummyState(snap(ifaces, detail))
    panel = Panel(state)
    panel.show_at(None, QRect(1000, 0, 30, 38))
    app.processEvents()

    # ---- 定位：水平中心对齐图标，顶部在图标下方 ----
    scr = app.primaryScreen().availableGeometry()
    expect_cy = 1000 + 15
    expect_y = max(38 + 4, scr.top() + 4)
    expect_x = max(scr.left() + 8, min(expect_cy - panel.width() // 2,
                                       scr.right() - panel.width() - 8 + 1))
    check("定位 x 居中并夹紧", abs(panel.x() - expect_x) <= 1,
          f"got x={panel.x()} want≈{expect_x}")
    check("定位 y 在菜单栏下方", 38 <= panel.y() <= 46, f"got y={panel.y()}")
    check("定位不覆盖菜单栏", panel.y() >= 38, f"y={panel.y()}")

    cards = [w for w in panel.findChildren(AdapterCard)]
    check("网卡卡片数量", len(cards) == 3, f"got {len(cards)}")

    # ---- 展开 + 滚动位置 ----
    by_svc = {c.ifc.get("service"): c for c in cards}
    usb = by_svc["USB-C LAN"]
    usb.set_expanded(True, animate=False)
    panel._relayout()
    app.processEvents()
    check("展开生效", usb.expanded)
    check("展开后有详情字段", len([f for f in usb._fields.values() if f.isVisible()]) >= 5,
          f"visible={sum(1 for f in usb._fields.values() if f.isVisible())}")
    # 附加 IP 拆成独立行
    check("附加 IP 独立字段", "alias0" in usb._fields and "alias1" in usb._fields)

    # 制造可滚动内容，记录滚动位置
    for c in cards:
        c.set_expanded(True, animate=False)
    panel._relayout()
    app.processEvents()
    sb = panel.scroll.verticalScrollBar()
    sb.setValue(min(40, sb.maximum()))
    scroll_before = sb.value()

    # ---- 连续 30 次刷新：卡片对象必须复用 ----
    ids_before = {c.ifc.get("service"): id(c) for c in cards}
    for i in range(30):
        new_ifaces = [
            ifc("Wi-Fi", "en0", ip=f"10.200.254.{89 + (i % 5)}",
                mask="255.255.254.0", router="10.200.254.1"),
            ifc("USB 10/100/1G/2.5G LAN", "en5", status="absent", ip="192.168.2.99"),
            ifc("USB-C LAN", "en7", ip="192.168.50.20"),
        ]
        state.set(snap(new_ifaces, detail))
        panel.update_state(state.snapshot())
        app.processEvents()

    cards_now = panel.findChildren(AdapterCard)
    ids_now = {c.ifc.get("service"): id(c) for c in cards_now}
    check("30 次刷新后卡片对象复用", ids_before == ids_now,
          f"before={ids_before} now={ids_now}")
    check("30 次刷新后仍展开", all(c.expanded for c in cards_now))
    check("30 次刷新后滚动位置不变", sb.value() == scroll_before,
          f"{scroll_before} -> {sb.value()}")
    check("30 次刷新后 IP 已更新", "10.200.254.93" in by_svc["Wi-Fi"].ip.text(),
          by_svc["Wi-Fi"].ip.text())

    # ---- 附加 IP 数量变化 ----
    d2 = copy.deepcopy(detail)
    d2["USB-C LAN"]["aliases"] = ["192.168.50.21", "192.168.50.22", "192.168.50.23"]
    state.set(snap(ifaces, d2))
    panel.update_state(state.snapshot())
    app.processEvents()
    check("附加 IP 增加到 3 行", "alias2" in usb._fields)
    d2["USB-C LAN"]["aliases"] = ["192.168.50.21"]
    state.set(snap(ifaces, d2))
    panel.update_state(state.snapshot())
    app.processEvents()
    check("附加 IP 减少到 1 行", "alias1" not in usb._fields and "alias2" not in usb._fields)

    # ---- 网卡插拔 ----
    state.set(snap(ifaces[:2], detail))
    panel.update_state(state.snapshot())
    app.processEvents()
    check("拔出后卡片减少", len(panel.findChildren(AdapterCard)) == 2)
    state.set(snap(ifaces, detail))
    panel.update_state(state.snapshot())
    app.processEvents()
    check("重新插入后卡片恢复", len(panel.findChildren(AdapterCard)) == 3)

    # ---- 方案确认条 ----
    p = {"name": "华为 iBMC", "service": "USB 10/100/1G/2.5G LAN", "mode": "static",
         "ip": "192.168.2.99", "mask": "255.255.255.0", "router": "192.168.2.1",
         "dns": ["223.6.6.6"]}
    state.set(snap(ifaces, detail, presets=[p]))
    panel.update_state(state.snapshot())
    app.processEvents()
    check("方案芯片渲染", len(panel._chips) == 1)
    panel._preset_clicked(panel._chips[0])
    app.processEvents()
    check("确认条可见", panel.confirm_bar.isVisible())
    check("确认条含方案名", "华为 iBMC" in panel.confirm_name.text(), panel.confirm_name.text())
    check("确认条含网卡", "USB 10/100/1G/2.5G LAN" in panel.confirm_meta.rawText())
    check("确认条含 IP 与掩码", "192.168.2.99/24" in panel.confirm_addr.text(),
          panel.confirm_addr.text())
    check("确认条含网关与 DNS",
          "192.168.2.1" in panel.confirm_addr.text() and "223.6.6.6" in panel.confirm_addr.text(),
          panel.confirm_addr.text())

    panel._do_confirm()
    app.processEvents()
    check("执行中禁用按钮", not panel.btn_yes.isEnabled() and not panel.btn_no.isEnabled())
    check("执行中防重复点击", panel._applying)

    panel.preset_apply_end(False, "部分成功：IP 已切换，但 DNS 设置失败（权限不足）", "warn")
    app.processEvents()
    check("失败后恢复按钮", panel.btn_yes.isEnabled())
    check("失败后保留确认条", panel.confirm_bar.isVisible())
    check("失败原因可见", "DNS 设置失败" in panel.confirm_msg.text())

    panel.preset_apply_end(True, "已应用「华为 iBMC」并生效", "ok")
    app.processEvents()
    check("成功后关闭确认条", not panel.confirm_bar.isVisible())

    # ---- 深色 / 浅色切换 ----
    panel._apply_theme(True)
    app.processEvents()
    panel._apply_theme(False)
    app.processEvents()
    check("主题切换无异常", True)

    # ---- 底部入口 ----
    texts = [t for _, t in panel._footer_items]
    check("底部入口文案", texts == ["主窗口", "DNS 测速", "DHCP", "设置", "退出"], str(texts))
    check("无「网络诊断」伪装入口", all("诊断" not in t for t in texts))

    panel.close()
    print()
    if FAILS:
        print(f"{len(FAILS)} 项失败：{FAILS}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

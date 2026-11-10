"""总体网络状态判定单测（纯逻辑，无需 GUI）

运行：.venv/bin/python tests/test_status.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.menubar.status import classify_iface, overall, summary  # noqa: E402

FAILS = []


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAILS.append(name)


def ifc(**kw):
    base = {"service": "S", "device": "en0", "status": "up", "ipv4": "10.0.0.2",
            "mask": "255.255.255.0", "router": "10.0.0.1", "enabled": True,
            "mac": "aa:bb:cc:dd:ee:ff"}
    base.update(kw)
    return base


# ---------- classify_iface ----------
check("classify: up", classify_iface(ifc()), "up")
check("classify: absent", classify_iface(ifc(status="absent")), "absent")
check("classify: disabled 覆盖 up", classify_iface(ifc(enabled=False)), "disabled")
check("classify: 未知状态", classify_iface(ifc(status="")), "unknown")
check("classify: 空字典", classify_iface({}), "unknown")

# ---------- overall ----------
check("stale 优先", overall({"stale": True, "ifaces": [ifc()]}), ("数据已过期", "warn"))
check("空网卡 + 刷新中", overall({"refreshing": True}), ("正在刷新", "info"))
check("空网卡", overall({"ifaces": []}), ("未检测到网卡", "muted"))
check("全部禁用", overall({"ifaces": [ifc(enabled=False, ipv4="")]}), ("网卡已禁用", "muted"))
check("全部未插入", overall({"ifaces": [ifc(status="absent", ipv4="")]}), ("网卡未插入", "warn"))
check("接口存在但未连接", overall({"ifaces": [ifc(status="down", ipv4="")]}), ("网卡未连接", "warn"))
check("已连接但无地址", overall({"ifaces": [ifc(ipv4="")]}), ("地址配置异常", "err"))
check("部分连接（一 up 有 IP、一 up 无 IP）",
      overall({"ifaces": [ifc(), ifc(service="S2", device="en5", ipv4="")]}),
      ("部分接口已连接", "warn"))
check("接口已连接", overall({"ifaces": [ifc()]}), ("接口已连接", "ok"))
check("已连接但无免密权限",
      overall({"ifaces": [ifc()], "elevation_ok": False}),
      ("接口已连接 · 权限不足", "warn"))
check("已禁用不参与误判（up + disabled 混合）",
      overall({"ifaces": [ifc(), ifc(service="S2", device="en5", enabled=False, ipv4="")]}),
      ("接口已连接", "ok"))

# ---------- 不允许出现未经探测的「互联网」结论 ----------
texts = {overall(s)[0] for s in (
    {"ifaces": [ifc()]},
    {"ifaces": [ifc(ipv4="")]},
    {"ifaces": []},
)}
check("无「互联网」字样", any("互联网" in t for t in texts), False)

# ---------- summary ----------
check("summary 计数",
      summary({"ifaces": [ifc(), ifc(service="S2", device="en5", status="down", ipv4="")]}),
      "已连接 1 · 未连接 1")
check("summary 含附加 IP",
      summary({"ifaces": [ifc()],
               "detail": {"S": {"aliases": ["10.0.0.3", "10.0.0.4"]}}}),
      "已连接 1 · 附加 IP 2")
check("summary 无网卡", summary({"ifaces": []}), "未检测到网络服务")

print()
if FAILS:
    print(f"{len(FAILS)} 项失败：{FAILS}")
    sys.exit(1)
print("ALL PASS")

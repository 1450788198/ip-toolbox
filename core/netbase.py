"""平台检测与命令执行助手"""
import ipaddress
import os
import shlex
import subprocess
import sys

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"


def normalize_mask(text: str) -> str:
    """掩码输入归一化为点分十进制，所有掩码输入框通用。

    支持：255.255.255.0 / /24 / 24（可带首尾空格），非法输入抛 ValueError
    """
    s = (text or "").strip().lstrip("/")
    if not s:
        raise ValueError("子网掩码不能为空")
    if s.isdigit():
        p = int(s)
        if not 0 <= p <= 32:
            raise ValueError(f"前缀长度超出 0-32: /{p}")
        return str(ipaddress.IPv4Network(f"0.0.0.0/{p}").netmask)
    ipaddress.IPv4Address(s)   # 点分形式：仅校验合法性（/0 与 0.0.0.0 均支持）
    return s

# USB / 外置网卡常见标识（macOS 端口名或 Windows 描述中出现）
_USB_HINTS = ("usb", "adapter", "ax88", "rtl81", "asix", "realtek", "lan95",
              "lan78", "ue3", "ue4", "ue9", "外置")


def iface_is_external(ifc: dict) -> bool:
    """判断是否为 USB/外置/扩展网卡"""
    text = f'{ifc.get("port", "")} {ifc.get("device", "")} {ifc.get("desc", "")}'.lower()
    return any(h in text for h in _USB_HINTS)


def sort_interfaces(ifaces: list) -> list:
    """外置网卡优先，其次已连接的，再按设备名"""
    return sorted(ifaces, key=lambda i: (
        not iface_is_external(i),
        i.get("status") != "up",
        i.get("device", ""),
    ))


def classify_route(r: dict) -> str:
    """路由类型标签：默认路由 / 网段路由 / 主机路由 / 直连路由"""
    dest = r.get("destination", "")
    gw = str(r.get("gateway", ""))
    flags = r.get("flags", "")
    if dest == "default":
        return "默认路由"
    if gw.startswith("link#"):
        return "直连路由"
    if "H" in flags:
        return "主机路由"
    return "网段路由"


def is_system_route(r: dict) -> bool:
    """非现场手工路由（默认/VPN 隧道/回环/链路本地/组播/广播/直连），业务视图默认隐藏"""
    dest = r.get("destination", "")
    gw = str(r.get("gateway", ""))
    flags = r.get("flags", "")
    iface = str(r.get("iface", ""))
    if dest == "default":
        return True          # 默认路由
    if iface.startswith("utun"):
        return True          # VPN / 代理工具（节点小宝等）隧道路由
    if dest.startswith(("127.", "169.254.", "224.", "239.", "255.")):
        return True
    if gw.startswith("link#") or flags.startswith("UH"):   # 直连/接口克隆路由
        return True
    return False


def sort_routes(routes: list) -> list:
    """默认路由最前，其余按目标地址排序"""
    def key(r):
        dest = r.get("destination", "")
        if dest == "default":
            return (0, "0")
        try:
            ip = dest.split("/")[0]
            octets = ".".join(f"{int(x):03d}" for x in ip.split("."))
            prefix = dest.split("/")[1] if "/" in dest else "0"
            return (1, f"{octets}|{prefix.zfill(3)}")
        except (ValueError, IndexError):
            return (2, dest)
    return sorted(routes, key=key)


class CmdError(RuntimeError):
    pass


def _as_quote(s: str) -> str:
    """转成 AppleScript 字符串字面量：必须转义 \\ 与 "，否则 osascript 报 -2740"""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _elevated_mac(cmd: list) -> subprocess.CompletedProcess:
    """macOS 提权执行：优先免密 sudo -n（已一次性授权），否则弹系统授权框"""
    # 已安装 sudoers 白名单 → 免密直执行（sudo 无法执行时静默回退弹窗）
    try:
        p = subprocess.run(["sudo", "-n"] + cmd,
                           capture_output=True, text=True, timeout=120)
        if p.returncode == 0:
            return p
        err = (p.stderr or "").lower()
        if "a password is required" not in err and "not allowed" not in err \
                and "no tty" not in err:
            return p   # 命令本身报错（非权限问题），直接返回交上层处理
    except (PermissionError, FileNotFoundError, OSError):
        pass            # sudo 无法执行（沙箱/受限环境）→ 回退授权框
    except subprocess.TimeoutExpired:
        raise CmdError("命令执行超时")
    # 未授权 → 弹系统授权框（支持 Touch ID）
    escaped = " ".join(shlex.quote(c) for c in cmd)   # shell 层转义
    script = f"do shell script {_as_quote(escaped)} with administrator privileges"
    return subprocess.run(["osascript", "-e", script],
                          capture_output=True, text=True, timeout=120)


def _elevated_win(cmd: list) -> subprocess.CompletedProcess:
    """Windows 上通过 PowerShell UAC 弹窗提权执行命令（同步等待）"""
    ps = "Start-Process -FilePath cmd.exe -ArgumentList '/c', " \
         f"{shlex.quote(' '.join(cmd))} -Verb RunAs -Wait"
    # 注意：UAC 提权进程无法捕获输出，需靠 exitcode；调用方应先尝试普通执行
    return subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                          capture_output=True, text=True, timeout=120)


def run(cmd: list, privileged: bool = False, timeout: int = 30) -> str:
    """执行命令并返回 stdout。privileged=True 时自动提权（macOS 弹授权框）。"""
    try:
        if privileged:
            if IS_MAC and os.geteuid() != 0:
                p = _elevated_mac(cmd)
            elif IS_WIN:
                import ctypes
                if ctypes.windll.shell32.IsUserAnAdmin():
                    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                else:
                    p = _elevated_win(cmd)
                    if p.returncode != 0 and not p.stdout.strip():
                        raise CmdError("提权执行失败（用户可能取消了 UAC 弹窗）")
                    return p.stdout
            else:
                p = subprocess.run(["sudo", "-n"] + cmd, capture_output=True, text=True, timeout=timeout)
        else:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise CmdError(f"命令不存在: {e}")
    except subprocess.TimeoutExpired:
        raise CmdError("命令执行超时")
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip()
        raise CmdError(err or f"命令返回码 {p.returncode}: {' '.join(cmd)}")
    return p.stdout

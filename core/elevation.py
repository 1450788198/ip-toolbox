"""一次性授权：写入 /etc/sudoers.d 白名单，之后所有提权操作免密（sudo -n）

原理：
1. 首次授权时弹一次 macOS 系统授权框（支持 Touch ID / 密码）；
2. 用该次权限把本工具需要的命令（networksetup / ifconfig / route / 本程序解释器）
   写入 /etc/sudoers.d/ip-toolbox 白名单（%admin 组，经 visudo 校验语法）；
3. 之后所有提权操作走 `sudo -n`（非交互、不弹窗、不要密码）。

撤销：删除 /etc/sudoers.d/ip-toolbox 即可。
"""
import os
import shutil
import subprocess
import sys

from .netbase import _as_quote, run, CmdError

SUDOERS_FILE = "/etc/sudoers.d/ip-toolbox"


def _whitelisted_cmds() -> list:
    """需要免密执行的命令绝对路径（networksetup / ifconfig / route / 当前解释器）"""
    cmds = []
    for name in ("networksetup", "ifconfig", "route"):
        p = shutil.which(name)
        if p:
            cmds.append(p)
    if sys.executable and os.path.exists(sys.executable):
        cmds.append(os.path.realpath(sys.executable))
    return cmds


def sudoers_lines() -> list:
    """用 %admin 组（macOS 管理员组）而非具体用户名：GUI 登录用户必然在组内，
    且不受运行环境用户名差异影响"""
    return [
        "# 由 IP 工具箱生成：允许管理员免密执行以下命令（删除本文件即可撤销授权）",
        f"%admin ALL=(root) NOPASSWD: {', '.join(_whitelisted_cmds())}",
    ]


def is_installed() -> bool:
    """白名单是否已生效（用 sudo -n 静默测试 networksetup 权限）"""
    try:
        p = subprocess.run(["sudo", "-n", shutil.which("networksetup") or "networksetup",
                            "-listallnetworkservices"],
                           capture_output=True, text=True, timeout=10)
        return p.returncode == 0
    except Exception:
        return False


def install() -> bool:
    """弹一次系统授权框（Touch ID/密码），写入 sudoers 白名单。成功返回 True。"""
    lines = sudoers_lines()
    # 单引号内不含特殊字符（路径无单引号），printf 逐行写入
    printf_args = " ".join(f"'{l}'" for l in lines)
    shell = (f"printf '%s\\n' {printf_args} > {SUDOERS_FILE} && "
             f"chown root:wheel {SUDOERS_FILE} && chmod 440 {SUDOERS_FILE} && "
             f"/usr/sbin/visudo -cf {SUDOERS_FILE}")
    script = f"do shell script {_as_quote(shell)} with administrator privileges"
    p = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        err = (p.stderr or "").strip()
        if "User canceled" in err or "用户已取消" in err:
            raise CmdError("授权被取消")
        raise CmdError(f"授权失败: {err}")
    # visudo 校验失败时清理，避免留下坏 sudoers
    if "syntax" in (p.stdout or "").lower() and "ok" not in (p.stdout or "").lower():
        subprocess.run(["osascript", "-e",
                        f'do shell script {_as_quote(f"rm -f {SUDOERS_FILE}")} '
                        f'with administrator privileges'],
                       capture_output=True, text=True, timeout=60)
        raise CmdError("sudoers 语法校验未通过，已回滚")
    return True


def uninstall() -> bool:
    """撤销免密授权（删除白名单文件，需要一次系统授权框）"""
    if not os.path.exists(SUDOERS_FILE):
        return True
    script = f"do shell script {_as_quote(f'rm -f {SUDOERS_FILE}')} with administrator privileges"
    p = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise CmdError(f"撤销失败: {(p.stderr or '').strip()}")
    return True

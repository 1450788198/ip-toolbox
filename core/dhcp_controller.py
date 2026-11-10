"""DHCP 服务控制器（主程序侧）：负责提权启动 runner 进程、轮询状态、停止"""
import json
import os
import shlex
import subprocess
import sys
import time

from .netbase import IS_MAC, IS_WIN, run, CmdError

FROZEN = getattr(sys, "frozen", False)


def app_data_dir() -> str:
    """可写数据目录：开发模式在项目内，打包后在 ~/Library（macOS）/ %APPDATA%（Windows）"""
    if IS_MAC:
        base = os.path.expanduser("~/Library/Application Support/IP工具箱")
    elif IS_WIN:
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "IP工具箱")
    else:
        base = os.path.expanduser("~/.iptoolbox")
    os.makedirs(base, exist_ok=True)
    return base


def _app_root() -> str:
    """项目根目录（开发模式），打包模式下返回 .app 的 Contents 目录"""
    if FROZEN:
        # sys.executable = IP工具箱.app/Contents/MacOS/IP工具箱
        return os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


WORK_DIR = os.path.join(app_data_dir(), "dhcp-runtime")
# 开发模式：直接跑 dhcp_runner.py；打包模式：同一可执行加 --dhcp-runner 参数
if FROZEN:
    _runner_cmd = f'"{sys.executable}" --dhcp-runner'
else:
    _runner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dhcp_runner.py")
    _runner_cmd = f'"{sys.executable}" "{_runner_path}"'
RUNNER_ARGS = (f'{_runner_cmd} --config "{{cfg}}" --state "{{state}}" '
               f'--stop "{{stop}}" --leases "{{leases}}"')


class DhcpController:
    def __init__(self):
        os.makedirs(WORK_DIR, exist_ok=True)
        self.cfg_path = os.path.join(WORK_DIR, "config.json")
        self.state_path = os.path.join(WORK_DIR, "state.json")
        self.stop_path = os.path.join(WORK_DIR, "stop.flag")
        self.leases_path = os.path.join(WORK_DIR, "leases.json")

    def is_running(self) -> bool:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            return bool(st.get("running"))
        except Exception:
            return False

    def read_state(self) -> dict:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def start(self, cfg: dict, log_cb=None):
        """以管理员权限启动 DHCP 服务（macOS 弹授权框 / Windows 弹 UAC）"""
        if self.is_running():
            raise CmdError("DHCP 服务已在运行")
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        for p in (self.state_path, self.stop_path):
            if os.path.exists(p):
                os.remove(p)
        cmd = RUNNER_ARGS.format(cfg=self.cfg_path, state=self.state_path,
                                 stop=self.stop_path, leases=self.leases_path)
        # runner 的 stderr 落盘，崩溃时可排查（之前 DEVNULL 吞错导致只能干等超时）
        self.err_log = os.path.join(WORK_DIR, "runner-stderr.log")
        if IS_MAC:
            from .elevation import is_installed
            try:
                if is_installed():
                    # 已一次性授权：免密 sudo -n 直接后台拉起，不弹窗
                    with open(self.err_log, "ab") as ef:
                        subprocess.Popen(
                            ["sudo", "-n"] + shlex.split(cmd),
                            stdout=ef, stderr=ef,
                            start_new_session=True,
                        )
                else:
                    raise PermissionError("未授权")
            except (PermissionError, OSError):
                # 未授权或 sudo 无法执行 → 弹系统授权框（支持 Touch ID）
                from .netbase import _as_quote
                inner = (f"nohup {cmd} >> {self.err_log} 2>&1 &")
                script = f"do shell script {_as_quote(inner)} with administrator privileges"
                p = subprocess.run(["osascript", "-e", script],
                                   capture_output=True, text=True, timeout=120)
                if p.returncode != 0:
                    raise CmdError(f"授权失败或被取消: {(p.stderr or '').strip()}")
        elif IS_WIN:
            args_part = (f'--config "{self.cfg_path}" --state "{self.state_path}" '
                         f'--stop "{self.stop_path}" --leases "{self.leases_path}"')
            if FROZEN:
                ps = (f'Start-Process -FilePath "{sys.executable}" '
                      f'-ArgumentList \'--dhcp-runner {args_part}\' '
                      '-Verb RunAs -WindowStyle Hidden')
            else:
                runner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dhcp_runner.py")
                ps = (f'Start-Process -FilePath "{sys.executable}" '
                      f'-ArgumentList \'"{runner_path}" {args_part}\' '
                      '-Verb RunAs -WindowStyle Hidden')
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=120)
        # 等待服务就绪
        for _ in range(30):
            if self.is_running():
                return True
            time.sleep(0.2)
        # 超时：带上 runner 的崩溃信息（状态文件 error 字段 + stderr 日志尾部）
        detail = ""
        st = self.read_state()
        if st.get("error"):
            detail = str(st["error"])
        elif os.path.exists(self.err_log):
            try:
                with open(self.err_log, "r", encoding="utf-8", errors="replace") as f:
                    tail = f.read()[-500:].strip()
                if tail:
                    detail = tail.splitlines()[-1]
            except Exception:
                pass
        raise CmdError("DHCP 服务启动失败" + (f": {detail}" if detail else "（未在 6 秒内就绪）"))

    def stop(self):
        if IS_MAC:
            if os.path.exists(self.stop_path):
                return
            open(self.stop_path, "w").close()
        elif IS_WIN:
            run(["taskkill", "/F", "/FI", "WINDOWTITLE eq dhcp_runner*"], privileged=False) \
                if False else None
            open(self.stop_path, "w").close()
            # 兜底：按命令行匹配杀掉 runner
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                            "Where-Object {$_.CommandLine -like '*dhcp_runner.py*'} | "
                            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                           capture_output=True, text=True, timeout=30)
        # 等待退出
        for _ in range(20):
            if not self.is_running():
                break
            time.sleep(0.3)



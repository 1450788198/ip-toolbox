#!/usr/bin/env python3
"""IP 工具箱入口：网卡管理 / 多 IP / 方案切换 / 路由 / DHCP 服务

打包模式下（PyInstaller frozen），同一可执行通过 --dhcp-runner 参数
以 DHCP 服务进程模式运行（由主程序以管理员权限启动）。
"""
import sys


def ensure_privileges():
    """修改 IP/路由/DHCP 需要管理员权限。macOS 下普通用户运行，
    每次修改操作会自动弹出系统授权框；无需整体提权。"""
    pass


def main():
    # DHCP 独立进程模式（打包后由主程序提权拉起）
    if "--dhcp-runner" in sys.argv:
        sys.path.insert(0, getattr(sys, "_MEIPASS", "."))
        # 从 argv 中摘掉分发标记，避免 runner 的 argparse 误报未知参数
        sys.argv = [a for a in sys.argv if a != "--dhcp-runner"]
        from core.dhcp_runner import main as runner_main
        runner_main()
        return

    ensure_privileges()
    from ui.main_window import run_app
    run_app()


if __name__ == "__main__":
    main()

"""DHCP 独立运行进程（由主程序以管理员权限启动）

文件通信协议：
  --config <json>   配置文件路径
  --state  <json>   状态/日志输出（主程序轮询读取）
  --stop   <flag>   存在此文件即退出
"""
import argparse
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dhcp_server import DHCPServer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--stop", required=True)
    ap.add_argument("--leases", default="")
    # 忽略未知参数（打包模式下主程序会附带 --dhcp-runner 分发标记）
    args, _unknown = ap.parse_known_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["leases_file"] = args.leases

    logs = []
    log_lock = threading.Lock()
    status = {"running": True, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
              "logs": logs, "leases": {}}

    def log_cb(msg, level="INFO"):
        line = f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}"
        with log_lock:
            logs.append(line)
            del logs[:-500]  # 最多保留 500 条
        try:
            status["leases"] = {v.get("ip", ""): {"mac": v.get("mac", ""),
                                                  "expires": time.strftime("%H:%M:%S", time.localtime(v["expires"]))}
                                for v in srv.leases.values()}
        except Exception:
            pass
        _write_state()

    def _write_state():
        tmp = args.state + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False)
            os.replace(tmp, args.state)
        except Exception:
            pass

    srv = DHCPServer(cfg, log_cb)
    srv.start()

    while srv.is_alive():
        if os.path.exists(args.stop):
            srv.stop()
            break
        with log_lock:
            status["leases"] = {v.get("ip", ""): {"mac": v.get("mac", ""),
                                                  "expires": time.strftime("%H:%M:%S", time.localtime(v["expires"]))}
                                for v in srv.leases.values()}
        _write_state()
        time.sleep(1.0)

    status["running"] = False
    _write_state()
    # 清理 stop 标记
    try:
        if os.path.exists(args.stop):
            os.remove(args.stop)
    except OSError:
        pass


if __name__ == "__main__":
    # 任何崩溃都写进状态文件，便于主程序/用户排查（而不是无声退出导致超时）
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        try:
            _sp = sys.argv[sys.argv.index("--state") + 1] if "--state" in sys.argv else ""
            if _sp:
                with open(_sp, "w", encoding="utf-8") as f:
                    json.dump({"running": False, "error": f"{e}",
                               "trace": traceback.format_exc()[-2000:], "logs": [], "leases": {}},
                              f, ensure_ascii=False)
        except Exception:
            pass
        raise

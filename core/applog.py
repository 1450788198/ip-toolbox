"""统一日志：控制台 + 应用数据目录 app.log

UI 层不要用裸 `except: pass` 吞掉异常——重要异常写 WARN/ERROR 到此日志，
排查时只需看一处。日志只写结论性信息（操作、错误原因），不写入完整网络
配置（IP/MAC/DNS 列表），避免泄漏现场环境数据。
"""
import datetime
import os
import threading

_lock = threading.Lock()


def log(msg, level: str = "INFO"):
    print(f"[{level}] {msg}")
    try:
        from .dhcp_controller import app_data_dir
        path = os.path.join(app_data_dir(), "app.log")
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level}] {msg}\n")
    except Exception:
        pass          # 日志失败绝不能影响主流程


def warn(msg):
    log(msg, "WARN")


def error(msg):
    log(msg, "ERROR")


def exception(where: str, exc: BaseException):
    """记录被捕获的异常（含位置），替代裸 pass"""
    log(f"{where}: {exc.__class__.__name__}: {exc}", "WARN")

"""Touch ID 指纹验证（macOS LocalAuthentication）

优先纯指纹（LAPolicyDeviceOwnerAuthenticationWithBiometrics），
无指纹硬件时回退"指纹或密码"策略；非 macOS / 未安装框架时静默跳过。
"""
import sys


def biometry_available() -> bool:
    """本机是否有可用的生物识别（Touch ID）"""
    if sys.platform != "darwin":
        return False
    try:
        import LocalAuthentication as LA
        ctx = LA.LAContext.alloc().init()
        can, _err = ctx.canEvaluatePolicy_error_(
            LA.LAPolicyDeviceOwnerAuthenticationWithBiometrics, None)
        ctx.invalidate()
        return bool(can)
    except ImportError:
        return False
    except Exception:
        return False


def authenticate(reason: str, timeout: int = 90) -> tuple:
    """弹出系统指纹验证框（阻塞直到完成）。返回 (成功?, 错误描述)"""
    if sys.platform != "darwin":
        return True, ""
    try:
        import LocalAuthentication as LA
    except ImportError:
        return True, ""          # 框架缺失时不阻塞启动
    import threading

    ctx = LA.LAContext.alloc().init()
    done = threading.Event()
    result = {"ok": False, "err": ""}

    def _reply(success, error):
        result["ok"] = bool(success)
        if error is not None and not success:
            try:
                result["err"] = error.localizedDescription()
            except Exception:
                result["err"] = str(error)
        done.set()

    can_bio, _ = ctx.canEvaluatePolicy_error_(
        LA.LAPolicyDeviceOwnerAuthenticationWithBiometrics, None)
    policy = (LA.LAPolicyDeviceOwnerAuthenticationWithBiometrics if can_bio
              else LA.LAPolicyDeviceOwnerAuthentication)
    ctx.evaluatePolicy_localizedReason_reply_(policy, reason, _reply)
    done.wait(timeout)
    try:
        ctx.invalidate()
    except Exception:
        pass
    return result["ok"], result["err"]

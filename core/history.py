"""网络配置操作记录：本地 JSON 持久化，供「操作记录」页查看

只记录真实的配置变更（改 IP / DNS / 路由 / DHCP 等）及结果，
不做任何"一键回滚"承诺——回滚需要人工确认当前环境仍然适用。
"""
import datetime
import json
import os

_MAX_ITEMS = 500


def _path() -> str:
    from core.dhcp_controller import app_data_dir
    return os.path.join(app_data_dir(), "history.json")


def load() -> list:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list):
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(items[-_MAX_ITEMS:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def record(action: str, service: str = "", before: str = "", after: str = "",
           result: str = "成功", detail: str = "") -> dict:
    """追加一条操作记录，返回该条记录"""
    item = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "service": service,
        "before": before,
        "after": after,
        "result": result,
        "detail": detail,
    }
    items = load()
    items.append(item)
    _save(items)
    return item


def clear():
    _save([])


def copy_text(item: dict) -> str:
    """单条记录转纯文本（便于复制反馈）"""
    return (f"时间: {item.get('time', '')}\n"
            f"操作: {item.get('action', '')}\n"
            f"网卡: {item.get('service', '') or '—'}\n"
            f"结果: {item.get('result', '')}\n"
            f"变更前: {item.get('before', '') or '—'}\n"
            f"变更后: {item.get('after', '') or '—'}\n"
            f"说明: {item.get('detail', '') or '—'}")

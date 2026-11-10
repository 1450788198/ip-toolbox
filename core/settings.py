"""应用设置持久化（外观、刷新间隔、默认网卡、启动选项）"""
import json
import os

DEFAULTS = {
    "appearance": "system",       # system | light | dark
    "refresh_interval": 4,        # 秒，网卡自动刷新
    "default_iface": "",          # 网络服务名，空=自动（优先外置网卡）
    "start_minimized": False,     # 启动时只驻留菜单栏
    "confirm_dangerous": True,    # 危险操作二次确认
    "menu_bar_icon": "icon",      # 菜单栏图标：icon|status|ip|iface
}


def _path() -> str:
    from core.dhcp_controller import app_data_dir
    return os.path.join(app_data_dir(), "settings.json")


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:
        pass
    return cfg


def save(cfg: dict):
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return merged


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def set_value(key: str, value):
    cfg = load()
    cfg[key] = value
    save(cfg)
    return cfg

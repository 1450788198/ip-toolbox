"""IP 方案（预设）管理：JSON 持久化，支持一键切换静态 IP / DHCP / DNS"""
import json
import os
import sys


def _presets_file() -> str:
    """打包模式下存到用户可写目录；开发模式存项目根目录"""
    if getattr(sys, "frozen", False):
        from core.dhcp_controller import app_data_dir
        return os.path.join(app_data_dir(), "presets.json")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "presets.json")


_DEFAULT = {"presets": [], "version": 1}


def load_presets() -> list:
    try:
        with open(_presets_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("presets", [])
    except Exception:
        return []


def save_presets(presets: list):
    with open(_presets_file(), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "presets": presets}, f, ensure_ascii=False, indent=2)


def validate_preset(p: dict):
    """校验方案字段。返回错误信息，None 表示通过"""
    import ipaddress
    required = ["name", "service"]
    for k in required:
        if not p.get(k):
            return f"缺少字段: {k}"
    mode = p.get("mode", "static")
    if mode not in ("static", "dhcp"):
        return f"未知模式: {mode}"
    if mode == "static":
        if not p.get("ip"):
            return "静态模式需要填写 IP 地址"
        if not p.get("mask"):
            return "静态模式需要填写子网掩码"
    for field, label in (("ip", "IP"), ("mask", "掩码"), ("router", "网关")):
        v = p.get(field)
        if v:
            try:
                ipaddress.IPv4Address(v)
            except ValueError:
                return f"{label} 格式无效: {v}"
    return None

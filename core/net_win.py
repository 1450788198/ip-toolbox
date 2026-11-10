"""Windows 网络后端：netsh / route"""
import re
import subprocess
from .netbase import run, CmdError


class WinBackend:
    name = "Windows"

    # ---------- 网卡 ----------
    def list_interfaces(self):
        out = run(["netsh", "interface", "ipv4", "show", "interfaces"])  # 概要
        out_addr = run(["netsh", "interface", "ipv4", "show", "addresses"])
        # 解析 addresses 块（含名称、IP、掩码、网关）
        blocks = re.split(r"\n\n+", out_addr)
        ip_map = {}
        for b in blocks:
            m = re.search(r"接口[“\"](.+?)[”\"]|Interface \"(.+?)\"", b)
            if not m:
                m = re.search(r"配置接口|Configuration for interface", b)
                continue
            name = (m.group(1) or m.group(2) or "").strip()
            ipv4 = re.search(r"IP 地址: (\d+\.\d+\.\d+\.\d+)|IP Address: (\d+\.\d+\.\d+\.\d+)", b)
            mask = re.search(r"子网掩码: (\d+\.\d+\.\d+\.\d+)|Subnet Mask|子网前缀|Subnet Prefix", b)
            gw = re.search(r"默认网关: (\d+\.\d+\.\d+\.\d+)|Default Gateway: (\d+\.\d+\.\d+\.\d+)", b)
            ip_map[name] = {
                "ipv4": (ipv4.group(1) or ipv4.group(2)) if ipv4 else "",
                "mask": (mask.group(1) if mask else ""),
                "router": (gw.group(1) or gw.group(2)) if gw else "",
            }
        ifaces = []
        for line in out.splitlines():
            m = re.match(r"\s*(已启用|已禁用|Enabled|Disabled)\s+(已连接|已断开|Connected|Disconnected)\s+(本地连接|环回|Loopback)?\s*(\S.*?)\s*$", line)
            if not m:
                continue
            state, conn, _loopback, name = m.groups()
            if name in ("接口名称", "Interface Name"):
                continue
            info = ip_map.get(name, {})
            ifaces.append({
                "device": name, "port": name, "mac": "", "service": name,
                "enabled": state in ("已启用", "Enabled"),
                "ipv4": info.get("ipv4", ""), "mask": info.get("mask", ""),
                "router": info.get("router", ""),
                "status": "up" if conn in ("已连接", "Connected") else "down",
            })
        return ifaces

    def enable_interface(self, name: str, enable: bool):
        run(["netsh", "interface", "set", "interface", f"name={name}",
             f"admin={'enable' if enable else 'disable'}"], privileged=True)

    # ---------- 主 IP ----------
    def set_static_ip(self, name: str, ip: str, mask: str, router: str):
        cmd = ["netsh", "interface", "ip", "set", "address", f"name={name}",
               "static", ip, mask]
        if router:
            cmd.append(router)
        run(cmd, privileged=True)

    def set_dhcp(self, name: str):
        run(["netsh", "interface", "ip", "set", "address", f"name={name}",
             "source=dhcp"], privileged=True)

    def set_dns(self, name: str, dns_list: list):
        if dns_list:
            run(["netsh", "interface", "ip", "set", "dns", f"name={name}",
                 "static", dns_list[0]], privileged=True)
            for i, d in enumerate(dns_list[1:], start=2):
                run(["netsh", "interface", "ip", "add", "dns", f"name={name}",
                     d, f"index={i}"], privileged=True)
        else:
            run(["netsh", "interface", "ip", "set", "dns", f"name={name}",
                 "source=dhcp"], privileged=True)

    def get_dns(self, name: str) -> list:
        out = run(["netsh", "interface", "ip", "show", "dns", f"name={name}"])
        return re.findall(r"(\d+\.\d+\.\d+\.\d+)", out)

    # ---------- 别名（附加 IP）----------
    def add_alias_ip(self, name: str, ip: str, mask: str):
        run(["netsh", "interface", "ipv4", "add", "address", f"name={name}",
             ip, mask], privileged=True)

    def remove_alias_ip(self, name: str, ip: str):
        run(["netsh", "interface", "ipv4", "delete", "address",
             f"name={name}", ip], privileged=True)

    def list_alias_ips(self, name: str) -> list:
        out = run(["netsh", "interface", "ipv4", "show", "addresses", f"name={name}"])
        ips = re.findall(r"IP 地址: (\d+\.\d+\.\d+\.\d+)|IP Address: (\d+\.\d+\.\d+\.\d+)", out)
        flat = [a or b for a, b in ips]
        return flat[1:] if len(flat) > 1 else []

    # ---------- 路由 ----------
    def list_routes(self) -> list:
        out = run(["route", "print", "-4"])
        routes, in_table = [], False
        for line in out.splitlines():
            if "活动路由" in line or "Active Routes" in line:
                in_table = True
                continue
            if in_table:
                if "持久路由" in line or "Persistent Routes" in line:
                    in_table = "persistent"
                    continue
                if in_table == "persistent":
                    m = re.match(r"\s*(None|无)\s*$", line)
                    if not line.strip():
                        in_table = False
                    else:
                        parts = line.split()
                        if len(parts) >= 4 and re.match(r"^\d+\.", parts[0]):
                            routes.append({"destination": parts[0], "gateway": parts[1],
                                           "netmask": parts[2], "iface": parts[3],
                                           "flags": "", "persistent": True})
                        continue
                parts = line.split()
                if len(parts) >= 5 and re.match(r"^(\d+\.|default|0\.0\.0\.0)", parts[0]):
                    routes.append({"destination": parts[0], "gateway": parts[1],
                                   "netmask": parts[2], "iface": parts[3],
                                   "metric": parts[4], "flags": "", "persistent": False})
        return routes

    def add_route(self, dest: str, gateway: str, netmask: str = "",
                  iface: str = "", persistent: bool = False):
        cmd = ["route", "add"]
        cmd.append(dest if "/" not in dest else dest.split("/")[0])
        cmd.append(netmask or "255.255.255.255")
        cmd.append(gateway)
        if iface:
            cmd += ["if", iface]
        if persistent:
            cmd.append("-p")
        run(cmd, privileged=True)

    def delete_route(self, dest: str, gateway: str = "", iface: str = ""):
        run(["route", "delete", dest], privileged=True)

    # ---------- DHCP ----------
    def interface_ip(self, name: str) -> str:
        for ifc in self.list_interfaces():
            if ifc["device"] == name:
                return ifc["ipv4"]
        return ""


def get_backend():
    from .netbase import IS_MAC, IS_WIN
    if IS_MAC:
        return MacBackend()
    if IS_WIN:
        return WinBackend()
    raise CmdError("不支持的平台")

"""macOS 网络后端：networksetup / ifconfig / route"""
import ipaddress
import re
from .netbase import run, CmdError


class MacBackend:
    name = "macOS"

    # ---------- 网卡 ----------
    def list_interfaces(self):
        """返回 [{device, port, mac, service, enabled, ipv4, mask, router, status}]

        以 networksetup 网络服务为准（与系统设置"网络"面板一致）。
        service = 网络服务名（如 "USB 10/100/1G/2.5G LAN"，networksetup 命令用它）
        port    = 硬件端口名（如 "Ethernet Adapter (en2)"）
        无服务绑定的接口（雷雳/桥接）service 为空，UI 默认隐藏。
        """
        # 1) 服务 → 设备（listnetworkserviceorder 给出真实的 服务名/设备 映射）
        services = []   # [(service_name, device)]
        try:
            order = run(["networksetup", "-listnetworkserviceorder"])
            for m in re.finditer(
                    r"\(\d+\)\s*(.+?)\n\s*\(Hardware Port: (.+?), Device: ([^)]+)\)",
                    order):
                name, port_name, dev = (m.group(i).strip() for i in (1, 2, 3))
                services.append((name, port_name, dev))
        except CmdError:
            services = []

        # 2) 设备 → MAC（来自硬件端口表）
        macs = {}
        try:
            out = run(["networksetup", "-listallhardwareports"])
            for b in re.split(r"\n\n", out.strip()):
                dev = re.search(r"Device: (\S+)", b)
                mac = re.search(r"Ethernet Address: (\S+)", b)
                if dev:
                    macs[dev.group(1)] = mac.group(1) if mac else ""
        except CmdError:
            pass

        ifaces = []
        for name, port_name, dev in services:
            if not dev or dev == "*" or not dev.startswith("en"):
                continue  # VPN/PPP 等无物理设备的服务跳过
            ifaces.append({
                "device": dev,
                "port": port_name,
                "service": name,
                "mac": macs.get(dev, ""),
                "enabled": None, "ipv4": "", "mask": "", "router": "",
                "status": "",
            })

        # 3) 兜底：服务解析失败时退回硬件端口列表（保证列表不为空）
        if not ifaces:
            return self._list_interfaces_fallback()

        # 4) IP/网关/启用状态（networksetup -getinfo，用真实服务名）
        for ifc in ifaces:
            try:
                info = run(["networksetup", "-getinfo", ifc["service"]])
                ifc["enabled"] = "disabled" not in info.lower()
                for line in info.splitlines():
                    if line.startswith("IP address"):
                        ifc["ipv4"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Subnet mask"):
                        ifc["mask"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Router"):
                        router = line.split(":", 1)[1].strip()
                        ifc["router"] = "" if router in ("(null)", "") else router
            except CmdError:
                pass
            # 链路状态（ifconfig）；接口不存在（USB 网卡未插入）单独标记
            try:
                detail = run(["ifconfig", ifc["device"]])
                ifc["status"] = "up" if "status: active" in detail else "down"
                # MAC 兜底（USB 网卡未插时硬件端口表可能没有该设备）
                if not ifc["mac"]:
                    m = re.search(r"ether (\S+)", detail)
                    if m:
                        ifc["mac"] = m.group(1)
            except CmdError as e:
                ifc["status"] = "absent" if "does not exist" in str(e) else "down"
        return ifaces

    def _list_interfaces_fallback(self):
        """服务顺序解析失败时的兜底：按硬件端口枚举（服务名=端口名约定）"""
        out = run(["networksetup", "-listallhardwareports"])
        ifaces = []
        for b in re.split(r"\n\n", out.strip()):
            port = re.search(r"Hardware Port: (.+)", b)
            dev = re.search(r"Device: (\S+)", b)
            mac = re.search(r"Ethernet Address: (\S+)", b)
            if not dev or not dev.group(1).startswith("en"):
                continue
            ifaces.append({
                "device": dev.group(1),
                "port": port.group(1) if port else dev.group(1),
                "service": port.group(1) if port else dev.group(1),
                "mac": mac.group(1) if mac else "",
                "enabled": None, "ipv4": "", "mask": "", "router": "",
                "status": "",
            })
        for ifc in ifaces:
            try:
                detail = run(["ifconfig", ifc["device"]])
                ifc["status"] = "up" if "status: active" in detail else "down"
            except CmdError:
                ifc["status"] = "down"
        return ifaces

    def enable_interface(self, service: str, enable: bool):
        run(["networksetup", "-setnetworkserviceenabled", service,
             "on" if enable else "off"], privileged=True)

    # ---------- 主 IP ----------
    def set_static_ip(self, service: str, ip: str, mask: str, router: str):
        run(["networksetup", "-setmanual", service, ip, mask, router], privileged=True)

    def set_dhcp(self, service: str):
        run(["networksetup", "-setdhcp", service], privileged=True)

    def set_dns(self, service: str, dns_list: list):
        run(["networksetup", "-setdnsservers", service] + (dns_list or ["Empty"]),
            privileged=True)

    def get_dns(self, service: str) -> list:
        out = run(["networksetup", "-getdnsservers", service])
        if "aren't any DNS Servers" in out:
            return []
        return [l.strip() for l in out.splitlines() if l.strip()]

    # ---------- 别名（附加 IP）----------
    def device_exists(self, device: str) -> bool:
        """接口是否真实存在于内核（USB 网卡未插时服务仍在但接口不存在）"""
        try:
            return device in run(["ifconfig", "-l"]).split()
        except CmdError:
            return False

    def add_alias_ip(self, device: str, ip: str, mask: str):
        run(["ifconfig", device, "alias", ip, mask], privileged=True)

    def remove_alias_ip(self, device: str, ip: str):
        run(["ifconfig", device, "-alias", ip], privileged=True)

    def list_alias_ips(self, device: str) -> list:
        """返回设备上除主 IP 外的 alias IPv4 列表"""
        out = run(["ifconfig", device])
        result = []
        main_ip = None
        for line in out.splitlines():
            if line.startswith("\tinet ") and "netmask" in line:
                ip = line.split()[1]
                if main_ip is None:
                    main_ip = ip
                else:
                    result.append(ip)
        return result

    # ---------- 路由 ----------
    def list_routes(self) -> list:
        out = run(["netstat", "-rn", "-f", "inet"])
        routes = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and re.match(r"^(\d+\.|default)", parts[0]) \
                    and not line.startswith(("Internet:", "Routing", "Destination")):
                routes.append({
                    "destination": parts[0],
                    "gateway": parts[1],
                    "netmask": parts[2] if parts[2] != "Flags" else "",
                    "flags": parts[3],
                    "iface": parts[-1],
                    "persistent": False,
                })
        return [r for r in routes if r["destination"] not in ("Destination",)]

    def add_route(self, dest: str, gateway: str, netmask: str = "",
                  iface: str = "", persistent: bool = False):
        target = "default" if dest.lower() == "default" else dest
        cmd = ["route", "-n", "add"]
        if target != "default":
            try:
                network = ipaddress.ip_network(dest, strict=False)
                if "/" not in dest:
                    # 掩码统一转前缀形式（macOS route 只认 10.0.0.0/16，不认 /点分掩码）
                    prefix = (ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
                              if netmask else 32)
                    target = f"{network.network_address}/{prefix}"
            except ValueError:
                raise CmdError(f"无效的目标地址: {dest}")
        cmd.append(target)
        cmd.append(gateway)
        if iface:
            cmd += ["-ifscope", iface]
        run(cmd, privileged=True)

    def delete_route(self, dest: str, gateway: str = "", iface: str = ""):
        run(["route", "-n", "delete", dest], privileged=True)

    # ---------- DHCP 服务相关 ----------
    def interface_ip(self, device: str) -> str:
        try:
            out = run(["ipconfig", "getif", device])
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
            return m.group(1) if m else ""
        except CmdError:
            return ""

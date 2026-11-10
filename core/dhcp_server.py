"""内置 DHCP 服务器（纯 Python socket 实现，需 root/管理员权限运行）

设计参考 bmc-dhcp-tool：指定网卡 + 地址池，为 BMC/设备批量分配 IP。
协议：UDP 67 监听，UDP 68 广播回复，支持 discover/offer/request/ack/release。
"""
import ipaddress
import json
import os
import socket
import struct
import threading
import time

# DHCP 常量
BOOTREQUEST, BOOTREPLY = 1, 2
DHCPDISCOVER, DHCPOFFER, DHCPREQUEST, DHCPACK, DHCPNAK, DHCPRELEASE = 1, 2, 3, 5, 6, 7


def pack_options(opts: bytes) -> bytes:
    magic = b"\x63\x82\x53\x63"
    return magic + opts + b"\xff"


def opt(code: int, payload: bytes) -> bytes:
    return bytes([code, len(payload)]) + payload


def build_packet(xid, chaddr, yiaddr, siaddr, opts) -> bytes:
    """按标准 DHCP 报文布局构造回包:
    op/htype/hlen/hops(4B) xid(4B) secs/flags(4B) ciaddr(4B) yiaddr(4B) siaddr(4B) giaddr(4B)
    chaddr(16B) sname(64B) file(128B) magic(4B) options"""
    pkt = struct.pack("!BBBBIHH", BOOTREPLY, 1, 6, 0, xid, 0, 0)
    pkt += struct.pack("!III", 0, yiaddr, siaddr)   # ciaddr, yiaddr, siaddr
    pkt += struct.pack("!I", 0)                      # giaddr
    pkt += chaddr.ljust(16, b"\x00")[:16]
    pkt += b"\x00" * 64                              # sname
    pkt += b"\x00" * 128                             # file
    pkt += pack_options(opts)
    return pkt


def get_opt(options: dict, code: int):
    return options.get(code)


def parse_packet(data: bytes):
    if len(data) < 240:
        return None
    op, _, _, xid = struct.unpack("!BBBI", data[:7])
    yiaddr, siaddr, giaddr = struct.unpack("!III", data[12:24])
    chaddr = data[28:44][:6]
    magic = data[236:240]
    if magic != b"\x63\x82\x53\x63":
        return None
    options, i = {}, 240
    while i < len(data) - 1:
        code = data[i]
        if code == 0:      # pad
            i += 1
            continue
        if code == 255:    # end
            break
        length = data[i + 1] if i + 1 < len(data) else 0
        options[code] = data[i + 2:i + 2 + length]
        i += 2 + length
    return {
        "op": op, "xid": xid, "chaddr": chaddr.hex(),
        "chaddr_raw": chaddr,
        "giaddr": giaddr,
        "msg_type": options.get(53, b"\x00")[0] if 53 in options else 0,
        "requested_ip": (socket.inet_ntoa(options[50]) if 50 in options else ""),
        "client_id": options.get(61, chaddr[:6]).hex() if 61 in options else chaddr.hex(),
        "options": options,
    }


class DHCPServer(threading.Thread):
    """单线程轮询式 DHCP 服务，可通过 stop() 停止"""

    def __init__(self, cfg: dict, log_cb=None):
        super().__init__(daemon=True, name="dhcp-server")
        self.cfg = cfg                      # interface, ip, start, end, mask, router, dns[], lease_hours
        self.log_cb = log_cb or (lambda msg, level="INFO": None)
        self.leases_file = cfg.get("leases_file", "")
        self.running = False
        self.sock = None
        self.leases = {}                    # client_id -> {"ip", "mac", "expires", "hostname"}
        self._load_leases()
        self._pool_lock = threading.Lock()

    # ---- 租约持久化 ----
    def _load_leases(self):
        if self.leases_file and os.path.exists(self.leases_file):
            try:
                with open(self.leases_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                now = time.time()
                self.leases = {k: v for k, v in raw.items()
                               if isinstance(v, dict) and v.get("expires", 0) > now}
            except Exception as e:
                self.log_cb(f"加载租约失败: {e}", "WARN")

    def _save_leases(self):
        if not self.leases_file:
            return
        try:
            with open(self.leases_file, "w", encoding="utf-8") as f:
                json.dump(self.leases, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_cb(f"保存租约失败: {e}", "WARN")

    # ---- 地址池 ----
    def _pool(self):
        start = ipaddress.IPv4Address(self.cfg["start"])
        end = ipaddress.IPv4Address(self.cfg["end"])
        return start, end

    def _alloc_ip(self, requested: str, client_id: str) -> str:
        """分配 IP：优先请求的/续租的 -> 之前租给该客户端的 -> 池中第一个未占用且 ping 不通的"""
        start, end = self._pool()
        used = {l["ip"] for cid, l in self.leases.items()
                if cid != client_id and l.get("expires", 0) > time.time()}

        def in_pool(ip):
            try:
                a = ipaddress.IPv4Address(ip)
                return start <= a <= end
            except ValueError:
                return False

        if requested and in_pool(requested) and (requested not in used):
            return requested
        old = self.leases.get(client_id, {}).get("ip", "")
        if old and in_pool(old) and old not in used:
            return old
        cur = start
        while cur <= end:
            ip = str(cur)
            if ip not in used and ip != self.cfg.get("server_ip") and not self._ping(ip):
                return ip
            cur += 1
        return ""

    def _ping(self, ip: str) -> bool:
        """ping 冲突检测（1 秒超时）"""
        import subprocess as sp
        from .netbase import IS_WIN
        if IS_WIN:
            cmd = ["ping", "-n", "1", "-w", "1000", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1000", ip]
        try:
            return sp.run(cmd, capture_output=True, timeout=3).returncode == 0
        except Exception:
            return False

    # ---- 主循环 ----
    def run(self):
        self.running = True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                self.sock.bind(("0.0.0.0", 67))
            except PermissionError:
                self.log_cb("绑定 UDP 67 失败：需要管理员权限", "ERROR")
                self.running = False
                return
            self.log_cb(f"DHCP 服务已启动  网卡={self.cfg.get('interface')} "
                        f"服务器IP={self.cfg.get('server_ip')} "
                        f"地址池={self.cfg['start']}~{self.cfg['end']}")
            self.sock.settimeout(1.0)
            while self.running:
                # 过期租约清理
                now = time.time()
                expired = [k for k, v in self.leases.items() if v.get("expires", 0) <= now]
                if expired:
                    for k in expired:
                        self.log_cb(f"租约过期: {self.leases[k]['ip']} ({self.leases[k].get('mac')})", "INFO")
                        del self.leases[k]
                    self._save_leases()
                try:
                    data, addr = self.sock.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    req = parse_packet(data)
                    if req and req["op"] == BOOTREQUEST:
                        self._handle(req)
                except Exception as e:
                    self.log_cb(f"处理包异常: {e}", "WARN")
        except Exception as e:
            self.log_cb(f"DHCP 服务崩溃: {e}", "ERROR")
        finally:
            self.running = False
            self.log_cb("DHCP 服务已停止")

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    # ---- 状态机 ----
    def _handle(self, req: dict):
        t = req["msg_type"]
        if t == DHCPDISCOVER:
            self._reply_offer(req)
        elif t == DHCPREQUEST:
            self._reply_ack(req)
        elif t == DHCPRELEASE:
            cid = req["client_id"]
            if cid in self.leases:
                self.log_cb(f"释放租约: {self.leases[cid]['ip']} ({req['chaddr']})")
                del self.leases[cid]
                self._save_leases()

    def _reply_offer(self, req: dict):
        with self._pool_lock:
            ip = self._alloc_ip(req["requested_ip"], req["client_id"])
        if not ip:
            self.log_cb(f"地址池耗尽，无法响应 {req['chaddr']}", "WARN")
            return
        # OFFER 阶段即写入临时租约（预留地址，防止并发 DISCOVER 拿到同一 IP），
        # 后续 REQUEST/ACK 会刷新正式到期时间
        self.leases[req["client_id"]] = {
            "ip": ip, "mac": req["chaddr"],
            "expires": time.time() + 120,   # 预留 2 分钟
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_leases()
        opts = (opt(53, bytes([DHCPOFFER]))
                + opt(54, socket.inet_aton(self.cfg["server_ip"]))
                + opt(51, struct.pack("!I", int(self.cfg["lease_hours"] * 3600)))
                + opt(1, socket.inet_aton(self.cfg["mask"]))
                + opt(3, socket.inet_aton(self.cfg["router"] or self.cfg["server_ip"]))
                + opt(6, b"".join(socket.inet_aton(d) for d in self.cfg.get("dns", [self.cfg["server_ip"]]))))
        self._send(req, ip, opts)
        self.log_cb(f"OFFER {ip} -> {req['chaddr']}")

    def _reply_ack(self, req: dict):
        requested = req["requested_ip"]
        with self._pool_lock:
            ip = self._alloc_ip(requested, req["client_id"])
        if not ip or (requested and ip != requested):
            opts = opt(53, bytes([DHCPNAK]))
            self._send(req, "0.0.0.0", opts)
            self.log_cb(f"NAK -> {req['chaddr']} (请求 {requested})", "WARN")
            return
        self.leases[req["client_id"]] = {
            "ip": ip, "mac": req["chaddr"],
            "expires": time.time() + int(self.cfg["lease_hours"] * 3600),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_leases()
        opts = (opt(53, bytes([DHCPACK]))
                + opt(54, socket.inet_aton(self.cfg["server_ip"]))
                + opt(51, struct.pack("!I", int(self.cfg["lease_hours"] * 3600)))
                + opt(1, socket.inet_aton(self.cfg["mask"]))
                + opt(3, socket.inet_aton(self.cfg["router"] or self.cfg["server_ip"]))
                + opt(6, b"".join(socket.inet_aton(d) for d in self.cfg.get("dns", [self.cfg["server_ip"]]))))
        self._send(req, ip, opts)
        self.log_cb(f"ACK  {ip} -> {req['chaddr']}")

    def _send(self, req: dict, yiaddr: str, opts: bytes):
        yi = int(ipaddress.IPv4Address(yiaddr)) if yiaddr and yiaddr != "0.0.0.0" else 0
        si = int(ipaddress.IPv4Address(self.cfg["server_ip"])) if self.cfg.get("server_ip") else 0
        pkt = build_packet(req["xid"], req["chaddr_raw"], yi, si, opts)
        if not self.sock or not self.running:
            return
        try:
            self.sock.sendto(pkt, ("255.255.255.255", 68))
        except OSError as e:
            self.log_cb(f"发送失败: {e}", "WARN")

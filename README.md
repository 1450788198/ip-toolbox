# IP 工具箱

一款面向网络运维 / 现场交付工程师的 macOS 桌面 IP 工具，原生窗口界面（PySide6），不依赖浏览器。
对标 [ipchange.app](https://ipchange.app) 的功能思路，并针对国内运维场景做了本地化增强。

![platform](https://img.shields.io/badge/platform-macOS%2013%2B-blue) ![python](https://img.shields.io/badge/python-3.10%2B-green) ![license](https://img.shields.io/badge/license-MIT-orange)

## 功能一览

### 网卡与 IP
- **网卡管理**：以"系统设置 → 网络"相同的服务名视角列出网卡（避免 en/bridge/幽灵端口混淆），4 秒自动轮询，USB 网卡置顶显示插拔状态
- **IP 配置**：静态 IP / DHCP / DNS 一键切换；同一物理网卡叠加多个附加 IP（alias）
- **IP 方案**：保存常用 IP/DNS 组合为方案，一键切换；也可从菜单栏托盘直接切换

### 路由管理
- 业务视图：自动隐藏默认路由、VPN（utun）、系统保留路由，只显示现场手工添加的路由
- 添加 / 删除静态路由，macOS 持久路由可选

### DHCP 服务
- 内置纯 socket DHCP 服务器（独立提权进程），给 BMC / 新上架设备临时自动分配地址
- OFFER 阶段地址预留，防并发冲突；自定义地址池 / 网关 / DNS / 租期

### 工具
- **子网计算器**：IP + 掩码即时算出网络/广播地址、可用范围、主机数、通配符掩码、地址类型、二进制对齐视图
- **子网划分器（VLSM）**：按子网数量或每子网主机数自动划分，支持 1024 行结果展示
- **掩码速查表**：/8 ~ /32 全表，双击即填入计算器
- **DNS 快速查询**：8 家国内公共 DNS 测速对比；**分省运营商 DNS**（30 个省级区域，含黑龙江电信/联通/移动），测速后一键应用到网卡
- 所有掩码输入框均支持简写：`24`、`/24`、`255.255.255.0` 三种写法通吃

### 权限与安全
- Touch ID 指纹解锁应用，验证通过才显示主窗口
- 一次性 sudoers 白名单授权（`/etc/sudoers.d/ip-toolbox`，仅放行 networksetup/ifconfig/route），之后所有操作免密
- 托盘图标与主窗口解耦，菜单实时显示各网卡 IP/掩码/网关/DNS 与 DHCP 状态

## 环境要求

- macOS 13+（Intel / Apple Silicon），Touch ID 设备可选
- Python 3.10+
- 依赖见 `requirements.txt`：PySide6、pyobjc（LocalAuthentication）

## 快速开始

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python main.py
```

首次运行会引导授权：Touch ID 指纹解锁 → 写入 sudoers 白名单（一次性）。

### 打包为 .app

```bash
pip install pyinstaller
pyinstaller "IP工具箱.spec" --noconfirm --distpath dist
# 产物：dist/IP工具箱.app
```

## 项目结构

```
├── main.py                 # 入口（含 --dhcp-runner 独立进程分发）
├── core/
│   ├── netbase.py          # 平台检测、命令执行、AppleScript 转义、路由分类
│   ├── net_mac.py          # macOS 后端（networksetup / ifconfig / route）
│   ├── net_win.py          # Windows 后端（netsh / route，实验性）
│   ├── dhcp_server.py      # 纯 socket DHCP 服务器
│   ├── dhcp_runner.py      # DHCP 独立进程入口
│   ├── dhcp_controller.py  # DHCP 进程管理（提权拉起 / 状态监控）
│   ├── presets.py          # IP 方案持久化与校验
│   ├── elevation.py        # sudoers 白名单授权
│   └── biometric.py        # Touch ID 指纹验证
└── ui/
    ├── main_window.py      # 主窗口 / 侧边栏导航 / 托盘
    ├── style.py            # QSS 主题
    ├── icons.py            # Lucide 风格内联 SVG 图标
    ├── common.py           # QThread 工具
    └── tabs_*.py           # 各功能页
```

## 已知限制

- Windows 后端（`net_win.py`）为实验性，未经完整实测
- Touch ID 需要带 Touch ID 的 Mac；无指纹设备会跳过解锁直接进入
- 运营商 DNS 数据来自公开资料汇总，实际以宽带下发为准

## License

[MIT](LICENSE)

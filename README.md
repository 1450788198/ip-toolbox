# IP 工具箱

一款面向网络运维 / 现场交付工程师的 macOS 桌面 IP 工具，原生窗口界面（PySide6），不依赖浏览器。
对标 [ipchange.app](https://ipchange.app) 的功能思路，并针对国内运维场景做了本地化增强。

![platform](https://img.shields.io/badge/platform-macOS%2013%2B-blue) ![python](https://img.shields.io/badge/python-3.10%2B-green) ![license](https://img.shields.io/badge/license-MIT-orange)

## 功能一览

### 网络管理
- **总览**：当前连接（IP / 掩码 / 网关 / DNS / 链路速率）、网卡概览、DHCP 状态、最近操作、快捷方案一键切换
- **网卡管理**：左侧网卡列表 + 右侧分组详情；以"系统设置 → 网络"相同的服务名视角列出网卡（避免 en/bridge/幽灵端口混淆），自动轮询检测 USB 网卡插拔；IPv4 手动 / DHCP 切换、**应用前强制变更预览**、原始配置一键恢复；多 IP（alias）添加 / 批量添加 / 清空；IP 方案保存与应用
- **路由管理**：业务视图自动隐藏默认路由、VPN（utun）、系统保留路由；搜索过滤、添加 / 删除、**最长前缀匹配分析**
- **DHCP 服务**：内置纯 socket DHCP 服务器（独立提权进程），给 BMC / 新上架设备临时自动分配地址；OFFER 阶段地址预留防并发；实时租约表与运行日志

### 网络工具
- **子网计算器**：网络 / 广播地址、可用范围、主机数、通配符掩码、地址类型、二进制对齐视图，实时计算
- **VLSM 划分**：按子网数量或每子网主机数自动划分，结果可复制
- **掩码速查**：/8 ~ /32 全表，双击复制
- **DNS 测速**：8 家国内公共 DNS + 分省运营商 DNS（30 个省级区域，黑龙江置顶），ping 测速自动排名，一键应用到网卡 / 恢复自动获取

### 系统
- **操作记录**：记录真实配置变更（前 → 后 + 结果），可查看详情与复制（不提供未经确认的一键回滚）
- **设置**：浅色 / 深色 / 跟随系统、自动刷新间隔、默认网卡、菜单栏图标模式、启动选项、Touch ID 测试、sudoers 免密授权开关
- **外观**：完整深色模式，跟随系统自动切换
- **权限**：Touch ID 指纹解锁应用；一次性 sudoers 白名单授权后操作免密

### Network Control（菜单栏控制中心）
- 点击菜单栏图标弹出原生毛玻璃面板（NSVisualEffectView），浅色 / 深色自动适配
- 网卡分组列表（已连接 / 未连接 / 未插入），类型图标区分 Wi-Fi / USB / 雷雳 / 蓝牙 / 桥接 / VPN
- 每张网卡可展开：IP / 掩码 / 网关 / DNS / MAC / IPv6 / 附加 IP / 配置方式 / 链路速率，**点击即复制**；右键一键复制运维格式的配置摘要
- IP 方案两列快捷切换（应用中的方案高亮），应用前内嵌确认
- 总体网络状态胶囊（正常 / 部分断开 / 异常 / 刷新中 / 数据过期），底部快捷栏（主窗口 / 网络诊断 / 设置 / 退出）
- 菜单栏图标四种显示模式：节点图标 / 连接状态 / 当前 IP 网段 / 当前网卡名（模板图标，明暗菜单栏自适应）
- 主窗口与菜单栏共享同一 Network State（`core/netstate.py` 单一采集循环），不重复执行系统命令；刷新失败保留旧数据并明确标注"数据已过期"

> 所有掩码输入框均支持简写：`24`、`/24`、`255.255.255.0` 三种写法通吃。

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
│   ├── settings.py         # 应用设置（外观 / 刷新 / 默认网卡 / 菜单栏图标）
│   ├── netstate.py         # 统一 Network State（主窗口与菜单栏共享的数据源）
│   ├── netinfo.py          # 只读补充信息（IPv6 / 网卡类型识别）
│   ├── history.py          # 操作记录持久化
│   ├── subnet_utils.py     # 子网计算 / VLSM 纯函数
│   ├── dns_data.py         # 公共与分省运营商 DNS 数据、ping 测速
│   ├── elevation.py        # sudoers 白名单授权
│   └── biometric.py        # Touch ID 指纹验证
└── ui/
    ├── main_window.py      # 主窗口 / 侧边栏导航 / Network Control 集成
    ├── theme.py            # 设计系统：颜色令牌 + 浅色/深色 QSS
    ├── icons.py            # Lucide 风格内联 SVG 图标
    ├── common.py           # QThread 工具
    ├── dialogs.py          # 变更预览、方案、路由等统一对话框
    ├── components/         # 卡片 / 侧边栏 / Toast / 徽标等通用组件
    ├── menubar/            # 菜单栏 Network Control：模板图标（4 种模式）、
    │                       #   Qt.Popup 面板、NSVisualEffectView 材质、网卡行、方案芯片
    └── pages/              # dashboard / network / routes / dhcp /
                            # subnet / vlsm / dns / history / settings
```

## 已知限制

- Windows 后端（`net_win.py`）为实验性，未经完整实测
- Touch ID 需要带 Touch ID 的 Mac；无指纹设备会跳过解锁直接进入
- 运营商 DNS 数据来自公开资料汇总，实际以宽带下发为准

## License

[MIT](LICENSE)

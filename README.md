# U30 Pro OpenWrt

为中兴 U30 Pro（MU5358）适配的 OpenWrt 固件，现已进入**稳定维护阶段**，
适合日常使用。系统基于 OpenWrt 25.12.5 和 Linux 6.12.94，结合 MU300
维护分支的软件框架与 U30 Pro 原生硬件驱动，提供网页看板、机身屏幕及完整安装工具。

公开仓库：[kanoqwq/u30pro_openwrt](https://github.com/kanoqwq/u30pro_openwrt) ·
维护分支：`main`

## 主要功能

| 功能 | 内容 |
| --- | --- |
| 蜂窝网络 | 4G/5G 拨号、IPv4/IPv6、双卡管理、射频开关、数据漫游及网络锁定 |
| 短信与流量 | 短信收发与转发、套餐设置、流量统计 |
| 无线网络 | AIC8800 Wi-Fi 6，默认 5 GHz、80 MHz、中国区域，SDIO 208 MHz |
| 原生屏幕 | 状态与网络信息、触摸操作、电源菜单、壁纸、电池历史及 NFC 开关 |
| 电池与充电 | 电量、电压、电流与功率显示，使用时间、续航估算、历史曲线及充电管理 |
| 设备管理 | CPU 调频与电压偏移、温控设置、USB 自动／设备／主机模式及 NFC 开关 |
| 安装与更新 | Windows、Apple Silicon macOS 和 Android 安装器，Diff Studio 差异包与网页系统补丁 |

屏幕、触摸、蜂窝联网、热点、充电及 OTG 等功能已进行实机适配与验证。
不同硬件版本、运营商和外设的具体记录见[适配文档](docs/U30PRO-PORT.zh-CN.md)。

## 安装与更新

使用为 **U30 Pro** 发布的完整固件 ZIP，解压后运行包内安装器，
也可以使用根目录的 `OpenWrt-Tools.apk` 从 Android 手机操作。
安装器负责检查设备、备份、分区规划和本机启动镜像构造；操作前请查看界面中的计划和数据影响说明。

系统使用独立的 `mu300root` 分区保存完整 OpenWrt 根文件系统，保留 Android。
Android／OpenWrt 槽位按本机情况识别；U30 Pro 的 `boot`、`vendor_boot`、
`init_boot` 由安装器统一处理，请勿单独刷入包内未绑定的 `boot-linux.img`。

日常差异更新可用 **Diff Studio** 生成补丁，通过网页“系统补丁”或包内更新工具应用，
保留用户插件、配置和数据。本地构建的完整包位于 `release/`。

## 源码与构建

克隆时一并获取共享安装器子模块：

```sh
git clone --recurse-submodules https://github.com/kanoqwq/u30pro_openwrt.git
cd u30pro_openwrt
```

已有检出可初始化子模块并检查构建输入：

```sh
git submodule update --init --recursive
python3 tools/build-release.py plan
python3 tools/build-release.py check
```

本机构建复用 WSL 的 `/home/kano/openwrt-build` 工作区，输入路径由
`tools/build-layout.json` 登记。请通过 `tools/build-release.py` 执行检查、编译及组包；
具体环境、命令和目录规则见以下文档。

- [本地构建与打包](docs/LOCAL-BUILD.zh-CN.md)
- [Agent 构建指导](docs/AGENT-BUILD.zh-CN.md)
- [硬件适配与验证记录](docs/U30PRO-PORT.zh-CN.md)
- [安装器接入说明](docs/U30PRO-INSTALLER-20261102.zh-CN.md)
- [双卡与硬件版本适配](docs/U30PRO-SIM-TOPOLOGY-20261103.zh-CN.md)
- [电池历史与统计](docs/U30PRO-BATTERY-HISTORY.zh-CN.md)

## 来源与致谢

本仓库从 [kanoqwq/mu300-linux](https://github.com/kanoqwq/mu300-linux) 的
`minikano-openwrt-feats` 分支 `29061dc8` 起步，从 `u30pro-bringup` 保留完整历史独立维护。
U30 Pro 的原生驱动、屏幕与硬件服务参考
[33333s/U30pro-openwrt](https://github.com/33333s/U30pro-openwrt)，逐文件来源和适配变更
记录在 [reference.json](devices/u30pro/reference.json) 与
[adaptations.json](devices/u30pro/adaptations.json)。

安装器与差异更新工具通过 [openwrt-tools](https://github.com/kanoqwq/openwrt-tools)
子模块固定版本引用，保留 U30 Pro 自己的启动和硬件适配。
各部分保留原作者版权，并遵循文件自身的许可证及 SPDX 标记。

# U30 Pro OpenWrt 安装包

本包只适用于 ZTE MU5358 / U30 Pro，Linux 6.12.94。软件、看板、分区安装及
空间回收来自 MU300 的 minikano-openwrt-feats 分支；驱动、基带加载器和
圆屏程序来自 U30 Pro。它不是 U30 Air 固件。

## 安装

完整解压 ZIP，打开根目录 OpenWrt-Installer.exe（Windows）或
OpenWrt-Installer.app（Apple Silicon）。Android 控制手机安装根目录的
OpenWrt-Tools.apk 后导入本包。Python 入口是 OpenWrt-Installer.py。

在 Android 开启 root 和 ADB，选择正确设备。按安装器展示的存储计划进行；
优先保留数据在线缩容，只有明确确认清除数据后才能使用格式化方案。
若出现机型不匹配提示，只有确认设备是 MU5358 / UMS9632 后才输入 yes
继续，底层仍会复核平台、槽位和分区。
内部安装使用 mu300root 分区和其中的 /openwrt，沿用 MU300 的空间检测、
缩容、续装和卸载方案，不使用原 U30 Pro 的固定扇区或 reserve2 overlay。

安装时会备份本机启动链，并以本机当前 Android 槽的容器构建另一个槽的
boot、vendor_boot、init_boot 和 DTBO，写入回读通过后才选择 Linux 槽。
不要直接 dd 包内 boot-linux.img：它是安装器的未绑定输入。
建议保留安装记录及电脑备份。丢失原记录时，卸载会按本机当前布局重新
核验并备份；不能核实的布局不会直接删除。

不支持直接作为 Magisk 模块刷入；应解压使用安装器。

## 首次进入

- 管理地址：192.168.77.1；账号 root，初始密码 root。
- 未导入 Android 热点时：U30Pro-OpenWrt，密码 openwrt1234。
- 原生圆屏沿用 U30 Pro，网络、短信、充电操作接到 MU300 管理后端。
- 首次启动先确认 USB 管理和屏幕，再测试热点、蜂窝、短信、充电及正常重启。

## 测试范围

此前已完成启动、蜂窝、热点与屏幕联调，用户也已确认上一版卸载成功。
本轮修复屏幕网页通知堆积、ADB 离线时误报身份／槽位变化及卸载标题，
通过源码回归和原生构建检查；这不代替每台设备的实机验收。本轮没有自动
刷写、重启或修改设备分区／NV。请保留 Android 恢复通道；默认启动为
Android，首次 Linux 为试启动。

Diff Studio 与系统补丁插件随包提供；原 U30 Pro 的 A/B 升级器没有带入。
U30 Pro 的三镜像启动容器更新仍需要单独硬件验收，首轮请使用完整安装器。
CPU 调频和核心开关使用标准内核接口，电压偏移已接本机 SML 两域接口，非零偏移仍需实际验证。

通用操作细节见 docs/GUI-GUIDE.md；Diff 工具见 docs/DIFF-STUDIO.md。

三镜像和公共安装器的具体边界见 docs/U30PRO-INSTALLER-20261102.zh-CN.md。

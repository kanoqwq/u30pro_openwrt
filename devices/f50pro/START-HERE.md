# F50 Pro OpenWrt 完整安装包

适用于 ZTE MU3356 / F50 Pro（UMS9632），不是旧款 F50 或 U30 Air。
与 U30 Pro 共用原生启动适配器和 MU300 的分区安装流程；F50 Pro 使用独立
卡板映射与指示灯配置，无屏幕、无电池，不启动相应服务。

## 安装、更新与卸载

完整解压 ZIP，打开根目录 OpenWrt-Installer.exe（Windows）或
OpenWrt-Installer.app（Apple Silicon）。Android 控制手机可安装根目录
OpenWrt-Tools.apk 后选择本安装包；Python 入口为 OpenWrt-Installer.py。

在目标设备 Android 中开启 root 和 ADB，核对设备后查看安装计划。
内部安装使用 mu300root 分区及其 /openwrt，优先尝试保留 Android 数据的
在线缩容；格式化方案需要单独明确确认。安装、更新和卸载均从同一安装器进入。
建议保留安装记录与自动备份，卸载可以归还安装占用的空间。

Android 与 Linux 槽动态识别。安装器读取本机启动模板，构造另一槽的
boot、vendor_boot、init_boot，保留 vendor_boot 内的本机 DTB，并同步本机 BSP 和 DTBO；
写入回读通过后才修改启动选择。不要直接刷包内 boot-linux.img，
它是未绑定具体设备模板的安装器输入，也不要直接作为 Magisk 模块刷入。

## 首次进入

- 管理地址 192.168.77.1，账号 root，初始密码 root；保留配置更新沿用原密码。
- 默认热点 F50Pro-OpenWrt；未导入 Android 密码时默认密码 openwrt1234。
- 卡位根据 MU3356 的 board_id 映射，不按运营商名称猜测。
- 原厂外置 SIM 1 对应 IMEI2，外置 SIM 2 对应 IMEI1；看板按实际卡源显示。
- 双卡双待默认关闭，可在“蜂窝 → SIM 卡管理”更改并保存射频及卡源组合。
- 默认实体按键无动作，可在设备管理中设置短按和长按功能。
- 默认 Wi-Fi 灯绿色表示 2.4 GHz、白色表示 5 GHz；颜色与亮度可在 LED 设置调整。

## 本版验证范围

已在 MU3356 / board 4 的 RAM 试运行中验证启动、蜂窝联网、热点、卡源切换、
USB 数据角色和指示灯；用户确认 NFC、实体长按可用。完整安装和卸载流程
通过离线回归，本版仍需进行 F50 Pro 首次正式安装验证；带供电扩展坞的实物
验证按用户安排延后。其他板号已按原厂 APK 做离线映射检查，不等于全部实机验收。

包内附带 Diff Studio、系统补丁插件及桌面/Android 安装器。
一般操作见 docs/GUI-GUIDE.md，差异更新工具见 docs/DIFF-STUDIO.md；
三镜像适配原理见 docs/U30PRO-INSTALLER-20261102.zh-CN.md，
其中 u30pro 是共享平台接口名称，实际产品标识仍是 f50pro。

# 无线配置保留与充电动画修复（2026-11-10）

## 无线配置

先核对差异更新和普通更新：固定版本的公共 OTA 引擎保留现存
`/etc/config/wireless`，新配置的 default 合并也不覆盖用户文件；普通更新
保留整个 `etc/config`。Android 保配置更新同样保留 wireless 的原始字节。
本次没有修改 OTA 合并或校验规则，用户对其他系统文件的小修改仍可更新，
并按原规则保留恢复副本。

另一个已复现的缺口位于 `openwrt-wifi-config`：旧安装若缺少
`/etc/mu300/wifi-configured`，原脚本会忽略现存 UCI 配置，重新导入旧的
Android 热点配置或生成密码。现在只有未初始化的禁用 OpenWrt 模板才执行
首次配置；已有 AP、STA、mesh 或禁用的自定义热点均保留。现存配置读取／
解析失败时也不当作空配置，不覆盖文件、不提交待保存设置。

回归：`tests/test_wifi_diff_preserve.py` 使用真正的固定版 OTA 引擎；
`tests/test_android_upgrade_config.py`、`tests/test_user_packages.py` 使用真实
更新函数；`tests/test_wifi_config_preserve.py` 执行真实启动脚本并隔离 UCI，
覆盖缺失标记、特殊字符密码、角色和加密方式、未提交设置和读取失败。
原有频道／首次初始化回归也通过。尚未复现独立于更新和初始化的 LuCI 保存
失败，不能据此声称所有密码问题均已实机验收。

## U30 Pro 充电圆环

原调度器给静止状态的充电动画固定 110 ms 帧间隔，触摸切页才为 16 ms。
可见的充电圆环现在也请求 16 ms，仍尊重用户高刷开关；休眠、非充电和被
弹窗／其他页面遮挡时不会为圆环维持快速刷新。无新增后台轮询。

`tests/u30pro_charging_animation.py` 编译真实界面并检查帧调度及像素变化，
高刷和充电交互原回归通过。ARM64 屏幕程序已通过正式入口编译，未热部署，
本轮未打完整固件包或做实屏验收。

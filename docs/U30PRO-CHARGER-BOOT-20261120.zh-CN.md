# U30 Pro 关机充电与正常启动交接

## 范围与行为

仅 U30 Pro / MU5358 启用 `S09u30pro-charge-mode`。F50 Pro 没有电池，
组包时不启用该服务。正常电源键启动、failsafe 和用户开启“上电自启动”
均直接继续原启动流程。设置沿用 `mu300-charge.main.power_on`，默认 0，
不新增另一份开关或覆盖用户配置。

充电启动来自 bootloader 的 `sprdboot.mode=charger` 或
`androidboot.mode=charger`，读取 cmdline 和 chosen/bootargs；设备树的 NUL
分隔符先转换为空格，再按完整 token 判断。不会按固件版本、内核哈希、
ABI 或另一台设备的分区地址选择功能。

关机充电时，S02 的原生 PM 看门狗继续运行，内核充电、PD 和温控驱动保持
原有职责。S09 等待在 S10 的模块自动加载、S12 硬件／网络初始化、S13 CP、
S14 正常屏幕及后续蓝牙／插件之前。既不加载 CP 和 AIC 蓝牙／Wi-Fi，
也不发 AT 或写射频权限。用户的射频、上网卡、AP／STA、蓝牙 autostart、
配对、限充和屏幕配置保持在原有配置文件中。

长按电源 2 秒，停止并回收充电画面、按键等待和临时限充 watcher 后，
继续同一次启动。普通服务从原有顺序恢复，重新读取各自用户配置，保留
NR0 自动事件入口、各 AT owner、显式选卡和初始化／回放协议。正常屏幕
首次提交帧后明确打开 DPMS，接管此前关闭的充电画面。

拔电连续 500 ms 后，通过现有启动选择 rearm、sync、根文件系统与 backing
mount 只读重挂，再调用内核 poweroff，包括 FGU shutdown 记账。若 poweroff
意外返回，保持启动门控并按重试 deadline 继续关机，不放行基带和网络。
按键／供电接口无法工作时明确记录并继续正常启动，避免无法开机。

进入关机充电即通过既有 `mu300-next-boot --rearm` 清理失败启动计数并按
原来的默认系统重新准备，不改变 Android/Linux 保存选择，避免反复拔插
充电器被当作多次启动失败。

## 原厂与本机证据

原生代码来源仍为 `devices/u30pro/reference.json` 的
`33333s/U30pro-openwrt df3b44fce648105aa785204571f8ad6317a95959`。
其参考 `u30pro-charger` 记录了 bootloader 的 charger 启动和电源键处理，
但该脚本未接入当前维护的 OpenWrt 启动链；其默认 watchdog 硬复位策略
也不适合作为当前“留在关机充电”的入口。

现有 `docs/U30PRO-PORT.zh-CN.md` 的 2026-11-02 实机记录证明，charger
启动可能只有 PM 在线。维护中的加载器已检查 PM/CH/NR 三个通道，不能仅
由 PM 在线推断基带已启动。此改动继续使用该加载器，不新增冷启动补丁。

2026-11-20 只读核对连接的 U30 Pro：`6.12.94-u30pro-p1`，board_id=2，
Android A、Linux B；正常启动的 cmdline 为 `modem=shutdown
sprdboot.mode=normal`。充电供电节点、gpio-keys 和 S02 看门狗均存在，
两张卡的当前 RF 权限均启用。未读出 SIM 身份，也未修改原始 NV／IMEI。

OpenWrt 的启动队列由 procd 自身执行，并不要求磁盘存在 rcS shell 文件。
[procd rcS.c](https://github.com/openwrt/procd/blob/master/rcS.c) 的启动队列
串行执行；运行超时设置限于 stop/shutdown，所以不能用充电脚本后台返回
来代替真正的启动门控。本机只读确认了实际 S02/S08/S10/S12/S13/S14 排序。

## 屏幕和运行开销

复用本机原生 KMS／evdev 程序的新 `charger` 入口，显示黑底电量环、闪电、
百分比、真实充电／暂停／充满状态和开机提示。此界面通过既有平滑矢量绘制，
没有提取或宣称逐帧复刻原厂 Android 动画。

充电模式不连接 ubus，不读取普通 feeder，不开放触摸菜单、快捷指令或
射频操作。充满后停止呼吸动画；10 秒自动息屏，短按电源亮／灭屏。
息屏后阻塞在内核电源事件、按键和待完成帧上，无独立 SOC 唤醒定时器。
亮屏时每 30 秒更新电量；本机 FGU 不提供周期电量事件。启用限充时沿用
已有 charge-watch 的 30 秒 SOC 期限和事件订阅，交接前停止该临时实例，
由正常 S97 服务重新接管，不重叠运行两个限充 watcher。

`/run/mu300/charging-boot.json` 记录 charging、handoff、poweroff 或
poweroff-failed，以及进入时间和退出原因；它是本次启动的诊断记录。
充电中标记为 `/run/mu300/charging-boot`，退出前移除。两者都不保存用户密钥。

## 六轮离线回归

| 轮次 | 实际执行路径 | 结果 |
| --- | --- | --- |
| 1 | 实际 ucode 模块：型号、两类 boot token、自动启动、failsafe、伪 token 和 NUL／换行 | 150 组组合通过 |
| 2 | 生产 C 按键等待函数，用真实 pipe/poll 检查长按、短按、功能键、拔电去抖和供电读取失败 | 3 项通过 |
| 3 | 实际 libuci、uloop.process、signal、子进程回收；长按、拔电、接口失败、画面失败、限充 watcher 及 poweroff 返回 | 9 项通过，设备操作均为替身 |
| 4 | 真实原生 UI 渲染／输入隔离、充满与未知电量、正常电源事件和快速切页 | 充电画面 1 项、电源事件 8 项、导航 17 项通过 |
| 5 | 实际差分生成／应用：首次加入与后续更新、每次撤销再应用，携带已校验的 ARM64 panel／keys、启动链接和 ucode；普通更新使用真实 apply_one，跨可用 POSIX shell 检查两次更新 | 用户 Wi-Fi、RF、蓝牙、限充、壁纸与数据逐字节保留 |
| 6 | 10,000 次策略／退出判定循环；真实等待进程 CPU ticks 和临时 worker 检查 | 20,000 次断言通过；4 秒空闲观察增量不超过 1 tick，无重复 rearm |

可复现入口：`tests/fixtures/u30pro_charge_policy.uc`、
`tests/test_charge_keys.py`、`tests/test_u30pro_charge_boot.py`、
`tests/u30pro_charge_screen.py`、`tests/u30pro_power_events.py`、
`tests/u30pro_navigation.py`、`tests/test_u30pro_charge_delivery.py` 和
`tests/test_update.py Update.test_charge_boot_first_and_subsequent_update_keep_saved_radio_states`。
均通过受锁的 `tools/build-release.py run` 执行，日志在
`out/build-logs/20261120-14*-charger-*/`。最终入口／差分回归为
`20261120-143926-charger-final-lifecycle-delivery-84483`；原生最终编译为
`20261120-143735-charger-runtime-final-84257`。

这些是离线检查与正常开机的只读采样，不能代替关机插电、拔电、按键开机、
PD／温控和长时间充电的实机验收。UI 与 keys 的 ARM64 构建已完成；内核和
模块没有变化，无需为此重编或刷 boot。

随后按本轮明确授权热部署上述 5 份用户态文件并启用 S09，仅重启屏幕。
设备 boot ID、两卡 RF 权限及 Wi-Fi／射频／限充／屏幕／默认系统配置摘要
均保持一致；屏幕 RPC 回读触摸、按键、feed 和电源事件监听正常。
备份在设备 `/root/update-backups/u30pro-charge-mode-20261120-144457`，
本机证据在 `work/diagnostics/u30pro-charge-mode-20261120-144457`。
首次部署的同名 staging 文件冲突被摘要校验拦截，只影响尚未启用的新入口，
核实其原先不存在且内容为本次误写后已清理，随后按完整目标路径隔离暂存。
首次关机充电实测发现电量计节点尚未注册时，画面显示结构默认的 0% 和
暂停，而且之后没有重新发现节点；用户长按后已正常进入系统，读数恢复
实际 48%／Charging。修正为未知读数明确显示“正在读取”，并在可信内核
add/change 电源事件和亮屏时重新发现电池；不更改 FGU、充电 IC 或百分比。
同时在进入正常系统后的重复调用中通过既有 CP-started 标记跳过门控，
因为该次启动的 cmdline 仍保留 charger。

修正后 `20261120-145323-charger-readiness-final-matrix-85325` 的 40 项相关
测试重新通过，包含迟到电池注册和实际 ARM64 两个二进制的 OTA 交付。
最终原生构建为 `20261120-145145-charger-late-supply-runtime-85254`。
按原授权更新同一 5 份文件并只重启屏幕，备份在
`/root/update-backups/u30pro-charge-mode-20261120-145429`；本机证据同名位于
`work/diagnostics`。boot ID、配置摘要和 RF 权限仍未改变。
用户再次关机插电后确认电量和充电状态正常；后续开机服务核对如下。
这些结果不等同于长时间充电／温控验收。

用户随后确认拔电关机、重新插电长按开机及“插电自动开机”均正常。
正常开机只读核对：两卡 RF 权限为 `[1,1]`、DSDS 已启用，WAN 已在
`sipa_eth0` 上联网，Wi-Fi／USB LAN、DHCP/DNS、网页、双卡短信、流量、
看门狗和屏幕服务均已运行；SIP 插件运行且音频 ready=true。蓝牙后台和
事件服务正常，控制器遵从原有 autostart 关闭状态。NFC 同步和锁频回放
为正常完成的单次任务，不需要常驻。一次 AT 预热 busy 返回后，原有
netifd／同一 AT owner 的流程已完成握手和注册，没有为其复位基带。

设备记录证实了电池就绪顺序：进入门控时 online=1、Charging，capacity
和 type 尚不可读；长按退出时为 Battery、48%、Charging。另补齐 Pro 的
现有 power_supply hotplug，使已启用的限充、手动暂停和单次充满能随
迟到电池事件应用；无电池的 F50 Pro 仍退出。入口初次 apply 不可用但有
用户策略时保留原 charge-watch，不会丢弃策略或新增另一套轮询。
`20261120-150233-charger-limits-event-delivery-86113` 的 12 项回归通过，
包括 60 组事件／型号／策略组合、三类迟到策略、进程交接及实际差分交付。
该补充沿用本轮部署授权更新 6 份用户态文件，仅重启屏幕；备份为
`/root/update-backups/u30pro-charge-mode-20261120-150350`。启动身份、配置
摘要和 RF 状态均未改变。限充的该事件补充为离线验证，尚未单独实测阈值
跨越；长时间充电、满电、低电压及温控仍没有完成本轮硬件老化验收。

## 更新交付

`tools/u30pro-runtime.py` 的现有源码／ELF 回执覆盖新的 panel 和 keys。
`tools/u30pro-package.py sources/finish` 复制该回执对应的二进制、正式 overlay
代码，并仅为有电池产品启用 S09；`tools/test-u30pro-root.py` 核对源字节、
服务链接和真实 ucode 编译。普通完整更新和差分更新都从同一正式 root 交付，
没有依赖热部署文件、手动 mkdir 或设备调试目录作为输入。

## 2026-11-22：低电充电时暂时掉线不能当作拔线

用户报告 0% 充电时短暂显示暂停、关机后又被充电器唤醒。只读检查的机器运行
`u30pro-r20261121.135443-g7fcb9347-s1365e778`，本次 charger 启动持续约 289 秒，
长按进入正常系统时电量为 5%。之前几次关机未留下持久记录，不能把每次关机
都断言为软件触发；没有要求把电池再次耗尽，也没有部署或重启。

已确认的软件缺口：原入口只看 SGM41513 的 `online`（REG08 的 power-good），
连续 500 ms 为零便关机。当前日志存在 PD hard-reset 的 1925 ms 受电恢复阶段；
恢复期间的电源有效性变化不能单独证明物理拔线。原生 `sc27xx_typec_cable[]`
将独立 CC 受电连接暴露为 `cable.3/state`（EXTCON_SINK），本机已只读确认。
证据保存在 `work/diagnostics/u30pro-low-charge-20261122/`，不是构建输入。

ucode 入口现在按 Type-C 控制器名称解析实际 extcon 实例，给既有按键／uevent
等待器传入独立 sink 状态。只有主充 offline 且 CC sink 也断开，才启动原来的
500 ms 拔线确认；仍接着受电端时等待原生电源恢复。接收既有 power_supply 和
extcon 事件，不新增周期性轮询，不改电压、电流、低压或温控保护。普通按键与
未传此参数的 U30 Air 充电入口保持原行为，F50 Pro 不进入本充电门控。

离线验证：7 项原生等待测试（包含旧逻辑同条件误关机、1925 ms 恢复、真实
extcon 拔线、信号错误及长短按）、12 项真实 ucode/uloop 生命周期、3 项共享
uevent、8 项原 U30 Air 启动门控（其中 1 项按现有条件跳过）以及 1 项实际
差分生成／应用测试均完成；共 30 项通过、1 项跳过。交付测试覆盖首次引入、
后续更新、回退再应用，保留充电、射频、Wi-Fi、蓝牙和用户数据。匹配的 ARM64
按键程序已增量编译并更新源码/ELF 回执；硬件低电充电验收尚未执行。

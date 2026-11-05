# U30 Pro 板号与物理 SIM 适配

## 证据与边界

采用用户提供的 `D:/111/ZteWebServerPlus.apk`，版本
`15.0.000.2601301518`，读取 `BoardIdConfigEnum`；原厂
`vendor-telephony-common.jar` 的 `com.android.vts.VendorSubInfoUpdater`
给出 GPIO 和逻辑栈的对应关系，以及先断电、切 mux、等卡恢复再启用的顺序。
Android 15 内核归档的 `sim_gpio_ctl.c` 给出 GPIO 名称、启动参数和检测极性。
具体来源和摘要见 `devices/u30pro/board-topology.json`。这些摘要仅用于来源记录，
不作为可用固件版本白名单。

连接设备为 board_id 2；它的启动参数含 `zteboot.zte_boardid=2`，但没有
`/proc/driver/board_id`。运行 DT 中存在 `zte,sim_gpio_ctrl` 和三个 GPIO，
原移植内核未接入驱动。只切 `SPACTCARD/SPSWDATA` 不能代替硬件选路。

调查文件在 `work/u30pro-board-topology/`。新卡路由版本经本次单独授权部署，
下文区分本轮 board 2 启动检查与尚未进行的物理切卡；不能把此前 USB/OTG
的实测通过算成本次 SIM mux 的全部验证。其余 E5/MU300 仓库未修改。

## 原厂板号

| board_id | 物理组合 | 物理位置 ID |
| --- | --- | --- |
| 0 | 3 内置 + 1 插拔 | 0、1、2、3 |
| 1 | 3 内置 | 0、1、2 |
| 2 | 2 内置 | 0、1 |
| 3 | 2 内置 + 1 插拔 | 0、1、3 |
| 4 | 3 内置 + 1 插拔，无屏版本 | 0、1、2、3 |
| 5 | 1 插拔 | 3 |
| 6 | 2 内置，使用第 1/第 3 位置 | 0、2 |

0–5 的映射在 MU5358/MU5358D/MU5358E 枚举一致；6 只在给定 APK 的 MU5358
枚举出现。第 6 项名称里的运营商缩写与布尔能力字段不一致，不能用名称推断
实际账号或运营商。界面只展示内置 SIM 的位置及插拔卡，不根据运营商筛选。
V50 的板号含义不同，保留其独立映射。

| 物理 ID | 硬件位置 | 逻辑 SIM/AT 上下文 | GPIO 选择 |
| --- | --- | --- | --- |
| 0 | 内置 SIM 1 | 0 | `psim_select=0` |
| 1 | 内置 SIM 2 | 1 | `chip_select=0` |
| 2 | 内置 SIM 3 | 1 | `chip_select=1` |
| 3 | 插拔 SIM | 0 | `psim_select=1` |

四个物理位置依然只有两个逻辑栈；绝不能发送 `SPACTCARD=2/3`。
射频权限、频段、小区、短信、流量、APN 和 AT 查看继续按逻辑卡槽管理。
网页物理选择、查看卡槽、主页 IMEI 和射频标签使用实际卡源名称；
AT 参数与 IMEI 编号仍表示逻辑栈，不随界面名称反转。

## 2026-11-05：双待入口及全板号显示复核

原来的双待能力判断只放行同平台的 F50 Pro，遗漏 U30 Pro；不仅按钮隐藏，
网页任务校验和 mobile-data 调度也会拒绝。现将 U30 Pro 接入同一个既有
RF/双待事务，默认关闭；关闭时保留所选上网卡的一路射频，允许全关，
显式切到另一张卡时先关闭原卡。开启双待不擅自打开另一张射频，已有显式
双待选择继续保留。冷启动、基带重启仍由公共初始化回放权限。
补齐物理切回逻辑栈 1 的单待入口，避免原栈已关闭时无法切回。

重新核对用户 APK 的 SHA-256 与 board-topology.json 一致，并交叉核对本轮
原厂枚举中的 MU5358/D/E 条目：0–5 相同，6 仍仅由 MU5358 条目支持。
七种板号的候选位置和两个 mux 的四种状态都进入离线回归：不存在的卡源
返回 null，而不是挪用 MU3356 的外置卡反向映射，也不按运营商猜卡位。

前端统一插拔卡名称为“外置 SIM 1”，射频行和主页 IMEI 保持“实际卡源 +
对应 IMEI”关系；board 6 的第二栈是内置 SIM 3。board 5 仅有一张插拔卡，
隐藏无意义的双待开关、禁用不存在的第二路射频与查看选项，并将旧浏览器
遗留的不存在卡槽选择恢复为自动跟随。刷新与切卡后使用同一只读状态，
不新增定时器、AT 所有者或机型专属复位流程。

本轮没有对 U30 Pro 做实机切卡或双待验收；离线通过不能替代其他板号硬件验证。
公共射频、双待、数据卡、开机初始化、U30 Pro/F50 Pro/V50 物理卡和翻译合计
138 项回归通过；追加 U30 Pro 冷启动/基带重启权限检查 1 项通过。
三语言/双宽度 RF 界面 6 组、查看选择器主题布局 60 组及主页双 IMEI 检查通过。
日志位于 `out/build-logs/20261105-071145-u30pro-standby-routing-regression-49300/`
和 `out/build-logs/20261105-071805-u30pro-standby-cold-warm-extra-97846/`。
正式 native 回归入口已加入双待/射频/数据卡/开机回放测试，后续构建可重复执行。
沿用当前 F50 Pro 产品 staging 执行正式 sources/finish，99 项源码/原生适配/
翻译文件与目标根一致；目标 ucode、服务及原有 LED/USB/充电检查通过。
该检查确认共享修复实际进入打包输入，不表示已组装 U30 Pro ZIP 或已实测其双待。
记录：`out/build-logs/20261105-072007-u30pro-standby-target-root-99056/`。

## 实现

- 专属 `CONFIG_U30PRO_SIM_MUX` 驱动只绑定本机 DT 的 GPIO。采用 descriptor
  极性，提供平台属性 `chip_select/psim_select/physical_present`。输入卡检测
  IRQ 使用原厂 100 ms 事件去抖和 `PSIM_STATUS` 通知，不启动轮询，不自动改用户选卡。
- 启动时保留原厂 `androidboot.simswitch/psimswitch` 的显式选择；没有参数时按
  本机 SKU 设置原厂对应路线，board 5 为插拔卡、board 6 为第 3 内置卡，
  在 CP 启动前完成，减少用户态重复切电和等待。
- 用户态优先读取 `/proc/driver/board_id`，无该节点时读取完整的
  `zteboot.zte_boardid/androidboot.zte_boardid` token。未知板号禁用物理选择，
  启动时保留 bootloader 线路，不猜板号、不因可选物理路由阻塞原逻辑栈初始化。
- 物理切卡事务提取为一份 `mu300-physical-sim`。V50 和 U30 Pro 使用独立映射，
  独立保存键和代际标记；原 V50 命令入口保留为薄入口。没有复制两套切卡事务。
- 只在已有 `mobile-data` RF 互斥内部切 GPIO，保留 `SPACTCARD`、SFUN 5/3、
  原厂换卡等待、SFUN 2、早期回放和用户 RF 权限，然后交给原数据卡事务完成
  `SPSWDATA`。失败按原事务恢复；不覆盖手动关闭数据的意图。
- 新卡切换前推进对应逻辑栈的缓存代际；后台旧采样不能把旧 ICCID/驻网重新写回。
  不删除短信、流量或用户数据。所有选择都不改 NV/IMEI。
- 网页使用 `physical_sim_get` 展示板号实际候选、当前卡和开机选择，复用既有
  确认、加载、任务结果及主题样式，补齐中/英/土耳其语。其他平台不显示物理卡选择。
- kernel 配置、源码覆盖、组包脚本、RPC ACL 和当前根校验已同步。新增驱动与
  现有全部 overlay 都必须匹配内核构建回执，不能只更新脚本却复用旧内核。

## 离线验证

完整卡事务回归 76 项通过：V50 13、U30 Pro 6、数据卡 15、双栈初始化 22、
查看卡槽 5、射频策略 15。另有网页交互用例覆盖四种 V50 和七种 U30 Pro 布局，
包括确认取消、任务错误/成功、物理 ID 到逻辑查看卡槽的映射及就绪状态刷新。
测试使用假 sysfs、伪造 AT owner/FIFO 和隔离配置，没有接触真实 SIM/NV。

双角色/新 SIM 驱动的 6.12.94 内核及完整配套模块编译成功；这不代表各个硬件
SKU 已经实测。日志：`out/build-logs/20261103-083159-u30pro-card-mux-kernel-ready-88322/`
和 `out/build-logs/20261103-083334-u30pro-card-full-regression-92370/`。

## 实机启动检查与待验证项

2026-11-03，用户授权“现在应用并重启验证”。重新核对 Linux A / Android B、
当前 kernel/ramdisk 后，备份本机 boot、模块和待替换程序；只写 Linux A boot、
配套模块与 SIM 程序，未写 Android、GPT、userdata 或 NV，未主动切换上网卡。
boot 即时回读通过，Android boot 及两槽 vendor_boot/init_boot 摘要保持不变。

本轮 board 2 结果：

- 原生 mux 驱动绑定成功，chip/psim 均为 0，网页 RPC 返回 `[0,1]`，ready=true。
- 两路只读 CPIN 均为 READY；实际/保存的逻辑上网卡仍为 0。
- 蜂窝 IPv4/IPv6 外网各两包均成功；热点、屏幕进程、USB 自动策略与 NCM 恢复。
- 258 项模块及元数据、13 项运行程序逐项摘要通过。设备端仅清理本轮 staging
  和旧模块目录，完整电脑备份保留。
- 开机第一轮有一次 SIM presence unreadable，现有公共重试自行恢复联网；未为
  消除这条暂态日志增加延时、复位或另一个回退实现。

记录在 `work/u30pro-board-topology/deploy-20261103-092916/`。本次没有主动
物理切卡，因此切卡实测、重启保持及失败恢复仍待验证。board 0/1/3/4/5/6
还需相应硬件，尤其第 3 内置卡与插拔卡选路，不能由 board 2 推断全部通过。

## 2026-11-06：保存的卡源也在 CP 启动前恢复

F50 Pro 的实机短信故障证实，不能只在 CP 启动后通过射频初始化回放保存的卡源。
U30 Pro 原有启动流程也存在这个顺序缺口；双内置卡并不能排除选择器需要恢复的情况。
但已测 board 2 的双内置组合与上电线路均为 0/0，本项通常不需要改变 GPIO，
不能据此声称该台 U30 Pro 曾经发生同一短信故障。

两款共用 `devices/u30pro/overlay/usr/sbin/u30pro-sim-preinit`，S13 vendor 服务
在任何 CP 加载前执行，替代旧 F50 Pro 专属入口。按 `/etc/mu300/model` 分别使用
MU5358 / MU3356 的现有 board_id 映射，不混用编号或电平：

- U30 Pro 复用运行时 `u30pro_boot_cards` 的保存选择和默认组合，包括单外置板 5
  和第 3 内置卡板 6；不另创开机选卡策略。未知板号保留原厂线路。
- F50 Pro 仍只恢复明确保存的单卡／成对来源，未保存时保留原厂选择。
- 完整验证路线后再写有变化的 GPIO；已匹配时不写、不发 AT、不增加等待。
- CP 启动标记、既有 AT bridge 或加载器存活时拒绝变更线路。正常运行中的切卡
  仍由原物理切卡事务及 RF owner 管理；射频、双待、数据卡权限不改。
- sources 会删除本工具已弃用的 F50 专属 helper；两款生产 overlay、目标根语法及
  源码一致性检查均覆盖新入口。无需因此重编未变化的内核或安装器。

新增离线用例覆盖所有 MU5358 板号及可选／默认卡源，并接着调用真实运行时 boot
控制器，确认不再触发晚期 SFUN／等待；同时覆盖错误卡号、错误 layout、未知板号、
存活 CP 拒绝及与 MU3356 相同板号的映射差异。此轮 U30 Pro 尚未做实机部署验证；
F50 Pro 的实测结果不能替代 U30 Pro 硬件验收。

本轮两产品卡板回归共 34 项通过（dash/bash/BusyBox ash），其中 U30 Pro 的
全部板号及默认／保存组合覆盖 78 个启动场景。日志：
`out/build-logs/20261105-171725-pro-pre-cp-owner-regression-43257/`。
正式 U30 Pro sources/finish 完成；目标 ARM64 根的源文件一致性、helper 可执行权限／
shell 语法、服务顺序和既有 modem/SMS/NR0 事件回归通过。旧 F50 专属入口已从
本工具拥有的 staging 移除。完整目标根检查日志：
`out/build-logs/20261105-172056-pro-pre-cp-common-target-root-69493/`。

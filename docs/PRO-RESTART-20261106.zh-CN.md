# Pro 偶发重启变关机：原厂重启准备缺项

用户报告 U30 Pro 未插 USB／充电器时，点击重启有时正常、有时直接关机。
另报告无电池 F50 Pro 的关机和重启都会重新启动。两种现象分别保留，
不能仅因同属 Pro 就认定根因或关机行为相同。

## 证据与已确认差异

网页选项、RPC、action、屏幕电源菜单和 panel-control 均将 reboot／poweroff
分别传递，没有发现命令互换。调查期间连接过的机器是 F50 Pro，不能把它
当作 U30 Pro；其前次 pstore 末尾为 `reboot: Restarting system`，这只能
证明那轮内核走到了重启入口，不能证明用户点的是哪个菜单，也不能证明
U30 Pro 的失败状态。后续 USB 管理连接已断开，没有发出远程重启或刷写。

从本机安装器保存的 MU5358 原始 Android B vendor_boot 备份提取驱动，先与
该事务 checksums.json 核验原始镜像一致；只提取两个小模块作离线分析，
没有再次备份整机或读取 NV。另与此前本机 MU3356 B22 备份对照。

| 参考 | 原厂模块构建标识 | spi-sprd-adi.ko SHA-256 |
| --- | --- | --- |
| 实际 U30 Pro／MU5358 | 6.6.98-android15-8-g3cb7658a4268-dirty-ab20260203.005522-4k | cb41993263f18df2f9c0764b2f30d9b99672838fbc8117e4d506ec8d804bd5be |
| 实际 F50 Pro／MU3356，F50ProV1.0.0B22 | 6.6.98-android15-8-g13dae4439181-dirty-ab20260321.130936-4k | 1cc45b73ca449f16e501dedaef4e920f629d7329d23f2075d3a8136c4888fb75 |

这些摘要仅用于追溯证据，不作为固件加载白名单或运行时版本检查。
两个模块的 `sprd_adi_restart_handler` 反汇编相同：

1. ADI 的 restart notifier 注册优先级为 **130**，先于通用 PSCI 的 129。
2. UMS9632 数据表的 reset-status 地址为 **0x21d4**，与本仓库 UMP9650
   `POR_RST_MONITOR` 寄存器定义一致。
3. 正常重启将低字节写为 **0x40**，保留高字节；原低字节为 **2 或 4**
   的安全错误原因保持不变。recovery／bootloader 等有各自的原因码。
4. 随后读取 `sprd,psci-reboot`：值为 1 时不使用 ADI 触发 PMIC 硬复位，
   返回并让后续 PSCI SYSTEM_RESET 执行真正的重启。

实际 U30 Pro 原厂 vendor_boot 的 DT 数据有 64 字节的 Spreadtrum 表头，
FDT 位于偏移 64，不能将整个字段直接当 FDT。解出后确认 ADI 为
`sprd,ums9632-adi`、`sprd,psci-reboot=<1>`，PMIC 为 UMP9650。
F50 Pro 捕获的原厂及实时 DT 也具有相同 ADI／PSCI 配置。

当前移植的 ums9632_data 没有 restart 回调，缺少上述标记准备；通用 PSCI
直接调用 SYSTEM_RESET。**原厂步骤缺失已证实，但尚未在 U30 Pro 失败现场
证明此缺项就是偶发关机的唯一根因。**

## 修复边界

在 UMS9632 ADI 中补 priority 130 的准备回调，只在本机 DT 明确声明
`sprd,psci-reboot=1` 时注册。回调保持原厂的正常／安全原因处理，写入后
回读检查；错误会明确记录，但仍返回 NOTIFY_DONE，让 PSCI 正常继续。
其他 ADI 型号原有重启回调不变；不改 PSCI 的 SYSTEM_RESET／SYSTEM_OFF，
不写看门狗寄存器，不取消 nowayout，不强制 CPU0 在线，不改电池或充电策略。

另核实两个原厂 sc27xx-poweroff.ko 的 probe：DT 的
`sprd,psci-poweroff=1` 时**不会**安装直接写 PMIC 的 pm_power_off 回调。
两款实际 DT 均为 1。因此“只启用通用 SC27XX 关机驱动”不是已经证实的
修复，主线旧驱动的固定寄存器也不能直接套用 UMP9650。F50 Pro 在持续
USB 供电下的关机保持行为仍需单独按原厂对照，不宣称本次已经解决。

## 验证

`tests/u30pro_restart.py` 编译真实的三段 C 函数，覆盖正常及命名重启、
安全原因与高字节保留、读／写／回读失败、优先级、DT 属性缺失／0／非法值、
注册失败和旧 ADI 路径；检查不接管关机或看门狗。已接入原生回归入口。
两项测试通过：
`out/build-logs/20261105-211642-pro-stock-restart-regression-37511/command.log`。

Image 和完整模块在既有缓存增量构建通过，构建记录：
`out/build-logs/20261105-211729-pro-stock-restart-kernel-37547/command.log`。
新 Image SHA-256：
`9b056cac1c4ff40fecb752f811cc90eb30793af2809415b4d2a3015b3d28ddac`。
配置未变。离线编译／隔离测试不等于实机修复验收；还需要用户授权应用并在
U30 Pro 上对照复测。此前已交付 ZIP 不包含本次新内核。

## 实机验证前的只读准备

用户随后接回 U30 Pro，实机识别为 MU5358 产品，当前固件仍为
`u30pro-r20261105.200523-g96a594bc-s33cfc29d`。动态确认 Linux A，
CPU0–7 均在线，reboot mode 为 cold、reboot CPU 为 0；前次 pstore 记录
Restarting system。这也不能用来认定用户报告的那次失败已被捕获。

读取 boot_a 到本机并与设备 SHA-256 核验，备份摘要为
`f31f18f3b8dd394991a774d2c424bd4ef1f4b0352a8cef0f976768841a0b2b96`。
现有 248 个模块与新构建逐文件同名、摘要完全一致，无需重写模块。

通过已有 `u30pro-boot-repair.py kernel-trial` 生成本机测试镜像，保留当前
ramdisk、安装参数和 boot 分区大小，仅替换已核验的内核包装。该工具原先
直接读取公开 JSON 的 `~/openwrt-build`，未展开显式本地配置；现改为使用
共用 build-settings，遵守 runner 传入的工作区。新增隔离测试验证配置选择
及原 ramdisk、命令行、镜像大小不变，与 ADI 两项回归合计三项通过。

用户随后选择“先不刷，保留修复”。以上全部是设备读取和本机准备，
未写设备分区、NV 或调用关机／重启；测试镜像和原 boot 备份保留，
实机效果仍未验收。

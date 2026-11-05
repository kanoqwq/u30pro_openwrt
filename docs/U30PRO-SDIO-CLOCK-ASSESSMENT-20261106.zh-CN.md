# Pro SDIO 父时钟与 CPU 性能策略核查

2026-11-06 用户连接 U30 Pro，授权只读核查。未切换时钟、CPU governor，
未重载无线、重启、操作 AT 或 NV。以下实机结果仅适用于这台 U30 Pro，
不能当成 F50 Pro 或全部批次的实测。

## 实机证据

- 固件：`u30pro-r20261105.184944-g96a594bc-sbede6ee5`。
- 内核：`6.12.94-u30pro-p1`。
- `/sys/kernel/debug/mmc2/ios`：请求 208000000 Hz、4-bit、SDR104。
- `clk_summary` 与各时钟的 `clk_parent`／`clk_rate` 一致：
  `rpll-390m (390000000) → sdio1-2x (390000000) → sdio1-1x (195000000)`。
- 可选父时钟包括 `v4nrpll-409m6`；其当前读数为 409600000 Hz。
- `policy0`／`policy6` 均为 `schedutil`；当次频率为 1326000／884000 kHz，
  上限 2041000／2210000 kHz。这是一次快照，不是测速负载曲线。

## 源码与原厂模板

- 时钟定义：`drivers/clk/sprd-u30pro/ums9632-clk.c` 的 `sdio_2x_parents`。
  Wi-Fi 控制器是 SDIO1；未使用的 SDIO0 不能当作 Wi-Fi 修改。
- 公开原厂 `vendor_boot` 模板的 Wi-Fi 节点 `sdio@22220000` 指定父源
  `<g1-pll CLK_RPLL_390M>`，与本次实机读数相符。模板只是参考，实际设备
  的 bootloader、DTB／DTBO 和运行时仍需分别核对；不能覆盖整套设备树。
- `sdhci-sprd.c` 在 probe 时缓存 `base_rate=clk_get_rate(clk_sdio)`，后续按
  该缓存算控制器分频，没有在每次设置时钟时重新读取父源。不能只在热运行时
  改 debugfs 父源，却假定驱动仍按正确基准分频／调谐。
- 当前 `set_clock` 没有报告 `mmc->actual_clock`，因此 `ios` 的 208 MHz
  请求读数不能单独证明总线实际运行在 208 MHz。

## 结论

切换父源在本机有对照价值：若二分频及其余设置不变，理论总线由 195 MHz
变为 204.8 MHz，增幅约 5.03%。500 Mbps 的 5% 约为 25 Mbps，所以群友
报告的约 20 Mbps 在量级上合理，但没有证明吞吐一定增加或问题已经修复。
如果其他机器已使用该父源，则没有相同的切换收益。

正式适配需在初始化阶段处理 Wi-Fi 控制器父源、分频、DLL／tuning，再验证
实际时钟、CRC／timeout、持续吞吐、无线重载及休眠恢复。本轮只读核查没有
测得切换后的吞吐、功耗或温度变化。

## 用户随后授权的源码实现

用户要求将总线提高到 204.8 MHz，并说明机器已拔走。因此下面只有离线实现，
不标记为新频率的硬件验收：

- R11P3 且带 `no-sd`／`no-mmc` 的 Wi-Fi 专用 host，在读取 `base_rate` 前
  通过本 SoC 的 OF 时钟提供者获取 `CLK_V4NRPLL_409M6`，设置本 host 的
  parent 和 409.6 MHz 2x 输出。不改 PLL 本身频率，不改 SD／eMMC host。
- 保留提供者的 EPROBE_DEFER 与错误语义，验证父源及最终输出的真实 rate。
  不能获得正确时钟时明确报错，不伪装成已经配置成功。
- 显式报告实际总线频率，关闭时钟时清零 `actual_clock`。
- 启动策略默认请求 204800000 Hz，保留明确的低频选择；旧配置中的
  208000000 Hz 请求按本板上限收敛到 204800000 Hz，不因旧默认值拒绝启动。
- 编译实际 C 函数的隔离测试涵盖 Wi-Fi／存储边界、提供者未就绪、父源频率
  不符、设置失败、引用释放、初始化顺序及分频后的实际频率报告。

两款 Pro 复用同一份配套的新内核／模块；只支持 UMS9632 平台，不改 MU300／E5。

`performance` 属于 CPU 调频 governor，不是更换 CPU 调度器。它请求策略允许的
最高频率，可避免升频等待、加快 CPU 瓶颈下的协议栈／软中断处理；不保证减少
硬中断屏蔽或唤醒延迟，也不保证固定增加 50 Mbps。仍受 thermal／QoS 上限影响，
持续功耗与发热需要同负载对照；本次保持用户原有 `schedutil`。

参考：[CPUFreq](https://docs.kernel.org/admin-guide/pm/cpufreq.html)、
[Common Clock Framework](https://docs.kernel.org/driver-api/clk.html)。

## 更新后实机回读（2026-11-06）

用户连接已更新的 U30 Pro，授权只读检查。固件为
`u30pro-r20261105.200523-g96a594bc-s33cfc29d`，内核为
`6.12.94-u30pro-p1`。未修改时钟、配置、AT、NV，未重载无线或重启。

- `mmc2/clock` 为 204800000；`mmc2/ios` 的请求与 **actual clock**
  均为 204800000 Hz，4-bit SDR104。
- `clk_summary` 及逐节点回读一致：
  `v4nrpll-409m6 (409600000) → sdio1-2x (409600000) → sdio1-1x (204800000)`。
  确认父源和实际频率均已生效，并非只改请求读数。
- DLL 日志为 `SDIO tuning at 204800000 Hz: 71 of 76 steps pass`。
- policy0／policy6 仍为 `schedutil`；热点为 5 GHz、信道 36、80 MHz。
- 两次读数相隔 35 秒，无线保持 up，RX／TX 字节均增长；command/data CRC、
  data timeout、tuning、ADMA 错误均为 0。command timeout 为 1、unexpected IRQ
  为 5，前后未增长。
- 本次启动的 dmesg 存在 AIC bus down／recovery／bus err 记录；没有证据将其
  归因于本次时钟修改，也不据此撤销修改。短时观察未发现上述计数持续增长。

本次确认的是启动后的时钟应用及短时连接状态，不是持续压测、功耗、休眠恢复
或改信道重载验收；尚未量化相较旧频率的吞吐增幅。结果仅适用于本台 U30 Pro。

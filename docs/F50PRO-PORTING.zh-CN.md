# F50 Pro（MU3356）首轮调查与试启动

日期：2026-11-05。参考为本机 `F50ProV1.0.0B22` / Android 15 /
`20260321.130936`，不是 U30 Pro 的 MU5358 资料。
本页是适配证据记录，不表示已经提供正式 F50 Pro 安装包。

## 2026-11-05：去除多余的独立 DTB 同步与备份

首个完整安装包在 backup 阶段报 Unsupported backup partition：F50 Pro
备份清单新增独立 dtb_a/b，底层传输并未允许该请求。初步准备补传输入口后，
用户指出 U30 Pro 并不需要此项，进一步核对确认该项增加本身没有依据：
本机 F50ProV1.0.0B22 原始 dtb_a/b 各 8 MiB，全部为零；vendor_boot_a/b
分别包含 200163/200069 字节的 DTB。原生三镜像适配器保留的是本机
vendor_boot 中的 DTB，这也是当前成功试启动使用的来源。

因此删除 F50 Pro 特加的独立 DTB 必需检查、BSP 同步、GUI/CLI 备份和
缓存备份映射，保留原有 BSP 五件及 boot/vendor_boot/init_boot/DTBO 的
原生事务。未放宽传输白名单，没有新增两套兜底逻辑。未知其他批次的独立
分区用途不由这份样本推断；不因存在同名分区就额外写入。
新增测试直接从 F50 Pro Adapter.backup 走真实备份校验、dd/pull、哈希、
进度和清理路径，另在冻结后端覆盖首次备份，不能只测试缓存复用。
84 项源码回归中 83 项通过、1 项因以 root 运行而跳过；三端安装器重新构建并
校验来源。新完整包的实际 Windows 冻结后端通过首次完整备份、二进制传输、
缓存复用、恢复和诊断检查，全程为模拟传输，没有操作设备。
原冻结恢复测试的 SSH mock 缺少现有 set_keepalive 接口，补齐 mock 后通过，
未为测试修改生产 SSH 行为。记录位于
`out/build-logs/20261105-082443-f50pro-fresh-backup-frozen-final-10406/`。

## SIM 组合必须先区分型号，再区分板号

从本机 `/system/priv-app/ZteWebServerPlus/ZteWebServerPlus.apk` 提取
`BoardIdConfigEnum`，并从 `/system/framework/vendor-telephony-common.jar`
提取 `com.android.vts.VendorSubInfoUpdater`。完整摘要与结构化组合记录在
[`devices/f50pro/board-topology.json`](../devices/f50pro/board-topology.json)。
摘要只用于追溯原始证据，不是固件版本加载白名单。

| MU3356 board_id | 内置卡 | 插拔卡 | 原厂位置 ID |
| --- | --- | --- | --- |
| 0 | 3 | 0 | 0、1、2 |
| 1 | 2 | 0 | 0、1 |
| 2 | 2 | 0 | 0、2 |
| 3 | 2 | 2 | 0、2、3、4 |
| 4 | 2 | 2 | 0、1、3、4 |
| 5 | 0 | 2 | 3、4 |
| 1000（测试配置） | 1 | 2 | 0、3、4 |

本机为 **MU3356 / board_id=4：两内置卡＋两插拔卡**。
MU5358 的 board_id=4 则是三内置卡＋一插拔卡；编号相同不代表接线相同。
现有 `u30pro-card.sh` 明确只处理 MU5358 系列，不能直接用于 MU3356。
界面应展示内置／插拔位置，不按实际运营商过滤卡位：用户可能更换内置卡，
或者把内置卡位置改成插槽。四个物理位置仍只复用两个逻辑协议栈。

`handleTwoEsimAndTwoPsimBootAction()` 与
`readSelectSlot1SimForMU3356()` 核实了板号 3/4 的路由：

| 位置 | 逻辑栈 | 原厂模块参数 | 参数值 |
| --- | --- | --- | --- |
| 内置 0 | 0 | gpio_sim_ctrl_psim | 1 |
| 内置 1（板号 4）／内置 2（板号 3） | 1 | gpio_sim_ctrl | 1 |
| 外置 SIM 2，原始位置 3 | 0 | gpio_sim_ctrl_psim | 0 |
| 外置 SIM 1，原始位置 4 | 1 | gpio_sim_ctrl | 0 |

这些是 **Android 原厂参数值**，不能当成当前 U30 Pro 驱动归一化后的
`psim_select` / `chip_select` 值。原厂模块反汇编确认参数 setter 直接调用
`gpiod_set_value_cansleep()`；`gpio_sim_ctrl` getter 的第一位是检测输入，
第二位才是选择输出，不能把两位均视为选择器。
原厂 `dealWithTwoPsimSwitch()` 还明确把位置 3/4 对应到逻辑栈 0/1。
1000 号只有 APK 能力证据，不能凭列表推定其启动和切换接线已验证。

### 外置卡编号交叉已确认

同一份 B22 APK 的 `ElfDeviceManager.needReversePsimMapping()` 对
MU3356 的双插、两贴两插、一贴两插型号返回 true；U30 Pro 不走此条件。
`SimCardModule.smartLifeSlotToRealSlot()` 把对外的外置 SIM 1（运营商类型码
11）映射到原始位置 **4**，外置 SIM 2（类型码 12）映射到 **3**；
`realSlotToSmartLifeSlot()` 的逆变换也一致。不能把原始编号 3/4 直接
顺序命名成外置 SIM 1/2。

| 原厂对外名称 | 原始卡位 | 逻辑 SIM（phoneId） | IMEI |
| --- | --- | --- | --- |
| 内置 SIM 1（本机板号 4） | 0 | SIM1（0） | IMEI1 |
| 内置 SIM 2（本机板号 4） | 1 | SIM2（1） | IMEI2 |
| 外置 SIM 1 | 4 | SIM2（1） | IMEI2 |
| 外置 SIM 2 | 3 | SIM1（0） | IMEI1 |

IMEI 查询由 `ElfDeviceManager.getImei(int, boolean)` 直接按逻辑 phoneId
调用 `TelephonyManager.getImei()`，没有再交换两组 IMEI。
这是本机原厂软件中的明确编号策略，尚不证明每个 PCB 的机身印字；
修正界面命名时应保持已经核实的 GPIO／逻辑栈路由，不能再交换一次。
运行代码保持原始路由 ID；网页外置卡名称按原厂转换显示：原始 4 为外置
SIM1，原始 3 为外置 SIM2，不反转 GPIO 或 AT 逻辑卡编号。

正式接入需要 MU3356 独立拓扑及 GPIO 启动策略，复用中央 AT owner、
SPACTCARD 选卡、射频互斥、配置回放和失败恢复；不另起抢占 AT 的服务。
原 MU5358 的表和启动选择方向保持独立。未知板号不能回落成 MU5358 表。

## 首轮试启动已完成

用户授权试启动并要求同步对侧 BSP。本机当时 Android 在 A，故 Linux
试验使用 B；这是实测状态，不是固定槽位规则。

1. 按分区读取并 SHA-256 核对两槽 boot、vendor_boot、init_boot、dtb、
   dtbo、uboot、sml、teecfg、trustos、vbmeta 与 misc 控制区备份。
2. 把本机 A 的 BSP 同步到 B 并回读核验，使用本机 DT 与 bootconfig
   重新绑定试验启动容器，没有刷入别台 U30 Pro 的 DT。
3. 重用已发布 U30 Pro 6.12.94 内核和 rootfs；rootfs 在 RAM 中展开。
   提前恢复 Android 下次启动选择，设置块设备只读，NV 通知仅应答，
   `--writeback=off`；没有缩容、修改 GPT、写入 NV／IMEI。
4. RAM 系统中禁用屏幕、电池记录等明确不适用于本机的服务。该临时隔离
   只用于此次调查，不等于已经完成生产配置的无屏／无电池支持。

结果：

- 完整 OpenWrt、USB NCM 管理网络、SSH 和 Wi-Fi AP 启动成功。
- SDIO 实际为 SDR104 / 208 MHz；AIC8800D80X2 固件与现有 U30 Pro 包
  中的七个文件逐项一致，基带装载 XML 也一致。
- CP 固件能够启动到 `Modem Alive`，随后在射频初始化期间多次出现
  `T_P_ATC ... mnphone_api.c` 断言；**尚未验证蜂窝联网成功**。
  错用 MU5358 拓扑是已确认的适配缺口，但没有证据证明它就是断言原因。
- Type-C 角色策略及部分温度传感器还有兼容缺口，不能仅因 USB 管理
  通道可用就判定全部电源／OTG 功能已经适配。
- 正常重启已回到 Android A，实际确认 boot_completed、root 和 ADB 可用。

本机没有物理电池，但原厂仍返回 `present=1`、`capacity=50` 和
`Charging`。生产配置必须显式声明无电池，不能仅按 power_supply 节点
存在判断。同时应保留 USB 供电／充电芯片相关依赖，不能一并删除。

本轮原始备份、反编译结果、镜像清单和日志保存在
`work/f50pro-stock-reference/`；不收入包含设备身份、NV 或整机镜像的文件，
也不把这些调查缓存作为正式编译输入。

## 独立产品接入（2026-11-05）

`devices/f50pro/profile.json` 是无屏、无电池的独立产品入口。
构建选择 `--profiles f50pro-6.12`，原 U30 Pro 仍使用默认的
`--profiles u30pro-6.12`。两款共享 UMS9632 内核、运行库和现有 AT owner，
按顺序复用受锁定的根 staging；没有复制另一套内核／根文件系统缓存。

- `/etc/mu300/platform=u30pro` 表示已有平台 ABI，不表示产品是 U30 Pro；
  `/etc/mu300/model`、发布元数据和安装器 manifest 单独标明产品。
- MU3356 使用独立卡位表和原厂 GPIO 启动方向；原 MU5358 的映射不变。
  Android 安装导入已核实的原厂物理卡位，生成首次配置；不会覆盖已有
  OpenWrt 卡位选择。固定接线型号只切数据卡，不额外切 GPIO／循环射频。
- 启动容器仍动态绑定本机 boot/vendor_boot/init_boot 模板、DT 和槽位。
  本机 DTB 随 vendor_boot 保留，不额外备份或同步独立 dtb_a/b 分区；
  与 U30 Pro 使用相同的原生容器处理方式。
  型号参数放入 vendor_boot 命令行，保留 canonical boot 的既有识别格式。
- F50 Pro 不启动屏幕、电池历史和充电上限服务，并禁止虚拟电池信息
  进入看板；保留 USB 控制器及供电相关依赖。GPIO LED 驱动只在 F50 Pro
  加载，灯状态由已有注册和无线事件驱动，不增加 AT 轮询。
- 安装器产品识别、更新、OTA、恢复与卸载均使用同一原生启动适配器，
  同时校验产品身份。型号码不匹配仍保留现有输入 yes 的明确确认流程。

已完成内核编译和离线卡位、启动链、安装器、目标根文件系统检查。
这些结果不代表 F50 Pro 新卡位初始化、基带联网、指示灯、OTG、按键
或 NFC 已经实机验收。首轮 CP 断言仍需用新配置重新验证；原生充电
芯片 ID 探测失败也仍是待调查项，不能因本机没有电池就忽略 USB 供电。
`release_ready=false` 在完成这些核对前保留。

`tools/f50pro-ram-trial.py` 仅从已登记的生产根、内核和本机备份模板
生成 RAM 试验镜像，不连接或刷写设备。实际写入／重启仍须用户授权。
试验启动先恢复 Android 下次启动选择，关闭 NV 写回并将存储设为只读；
根文件系统只在 RAM 中展开，不使用固定的 Android A／Linux B 假设。

## 第二轮 RAM 试验结果

本机板号 4，用户授权应用第二轮镜像。正式原生启动适配器在复核备份后，
将本机模板绑定到新的共享内核和 F50 Pro 配置；对侧 BSP 已一致，无需
重复写入。三镜像／dtbo 回读与 misc 提交成功，随后正常启动。

- 产品标记 f50pro，mux layout 为 mu3356，实际 chip=0、psim=1；
  原始卡位 4、逻辑 SIM2，与原厂当前选择相同。
- 注册及 IPv4/IPv6 地址获取成功，约四分钟观察内未出现首轮 CP 断言。
  GPIO LED 服务运行，当时用三通道合成 Wi-Fi 白色、当前卡位网络 GPIO
  为蓝色；用户随后报告混色，不能把当时的 sysfs 值记成灯色验收通过。
- FGU 未注册虚拟电池；屏幕、电池历史与充电策略未启动。NV daemon
  明确使用 writeback=off，sdhci 写保护为 Y，mmcblk0 为只读。
- 外网 Ping／DNS 无回包，不能宣称蜂窝数据通过。返回 Android 后，同一
  原始卡位仍为 4、同一逻辑 SIM2 使用 3gnet，Ping 为 3/3；RAM 试验为
  空 APN。APN 差异与数据链路需要进一步对照，不能直接认定欠费或 SIPA
  驱动故障，不增加重置／重拨兜底。
- 原生充电芯片 ID 探测仍失败。wcn/usb 温度读数为 124872，Android
  对照也相同；不据此直接改动温控或伪造温度。OTG、按键、NFC 尚未验收。

试验正常返回 Android A，boot_completed=1；没有改动 GPT、userdata、
NV 或 IMEI。第二轮日志在 `work/f50pro-stock-reference/trial-profile-mu3356/`。

## 原厂板号、单待与灯控复核

拓扑查询必须先识别 MU3356/MU5358，再读取 `board_id`；两款同号板的
接线不同。MU3356 的 0～5 号生产布局独立覆盖，未知板号不猜测路由。
原厂界面将外置槽编号转换为原始位置 4/3，AT 的逻辑栈编号仍为 1/0。
网页物理卡选项、查看卡槽名称按实际 mux 转换；提交的卡位 ID 不变。
`board_id=4` 只是本次样机，不会成为其他批次的默认值。

第三轮使用同一镜像、同一卡位和框架，将 RAM 中 APN 改为 3gnet 后仍未
收到外网探测回复。因此 APN 不是已确认根因，也不将 3gnet 写成产品默认。
随后已正常返回 Android。原厂实测 `car_mode_dual_sim_switch=0`、选中
原始卡位 4：其 RIL 关闭逻辑栈 0，只开启栈 1；旧 RAM 配置却同时开启
两栈。先补齐首次导入的单待意图；用户随后明确要求新增双待开关默认
关闭，因此当前新安装固定 dual_standby=0，仅允许所选数据卡射频。
保留用户已经保存的 OpenWrt 选择，不强制改成“两个外置槽”。
此差异与外网无回包之间的因果仍需实机核验。

实际 F50ProV1.0.0B22 的 Lights HAL 使用单个 GPIO 发光通道，不将三个
通道同时点亮来合成白色；网络类型 8/9/11 先清其他 GPIO 和 PMIC green，
再点目标通道，Wi-Fi 类型 101/102/103 同样先清 PMIC red。
`sprd-leds-bltc.ko`（SHA-256
`84ed3f41d731792b2c7b87c2fd7cda37b0169b256b6dde6db8073b2e89bfb322`）
中 `sprd_led_set(0)` 清除 DT base 上的 `3 << (channel * 4)`，并非修改
充电寄存器。样机 DT 为 ump9651-bltc、base 0x180，红/绿通道为 0/1。

新增 F50 专属 `f50pro-led-handoff` 模块从 DT 取得 base，先清上述两个
通道的 RUN/TYPE 位（0x33）并回读。后续按实际 HAL/模块证据补齐两个
独立白灯：sc27xx:red 为 Wi-Fi 白灯，sc27xx:green 为网络白灯。
GPIO green 是绿色，不能充当白灯。驱动使用原厂 UMP9651 的模块/时钟
使能位置 0x2008 bit9 / 0x2010 bit7、DT base bit12 清除，以及
base+8+channel*16 的 period=255、duty=brightness；不改电流及蓝通道。
共享内核虽编译此模块，默认 enabled=false，不声明自动加载 alias；
只有 F50 产品的 modules.d 传 enabled=1，U30 Pro 不加载。
GPIO 服务也按原厂先灭再亮，仍由既有注册/无线事件触发，不轮询 AT。
用户确认首个 handoff 试验的网络灯已正常，但 Wi-Fi GPIO green 实际为
绿色；两个 PMIC 白灯的新驱动效果仍需目视验收，不能把离线测试或
sysfs 单色值当作实际灯色通过。

### 本轮 RAM 实机结果

用户单独授权本轮镜像应用及正常返回 Android。本机仍为 Android A / Linux B，
先逐项核对本机备份与两槽 BSP 均一致，再由正式启动适配器写入并回读三镜像
和 dtbo，最后提交 32 字节试启动记录；没有复制其他设备的分区或修改 GPT。
对应 Image SHA-256 为
`f275408d6f197164894ece17c729ee7e4975de15e9634cdc77973d3ae259f9a6`。

- mux 仍为 board 4、chip=0、psim=1，原始卡位 4 / 逻辑 SIM2；
  RPC 返回当前两逻辑栈对应物理卡位 `[0,4]`。
- 首次导入射频策略为 `0 1`，两栈 AT+CFUN? 实际回读为 0 / 1，符合
  本机原厂单待状态。没有改成“两个外置槽”，也没有切换物理 SIM。
- 数据走 sipa_eth8，IPv4 和 IPv6 外网 Ping 分别 3/3、0% 丢包，运营商
  DNS 返回 A/AAAA；本轮默认 APN 未作前次的手动 3gnet 对照修改。
- F50 PMIC handoff 完成关闭及回读；网络 GPIO 仅 blue=1，Wi-Fi 仅
  green=1。用户确认网络灯正确，Wi-Fi 是绿色，白灯映射需要上述修正。
- 观察时无 CP assert；无屏/无电池服务隔离正常，NV writeback=off，
  eMMC 软件写保护及块只读均为 1。原生充电芯片 probe -5 仍存在，与
  原厂已有观测一致；不能据本轮数据联网通过声称 OTG/NFC 也已验收。

本轮通讯成功与单待配置修正相符，但没有做单变量因果对照，不将其表述为
所有历史无回包问题的已证实根因。原始日志在
`work/f50pro-stock-reference/trial-board-led-20261105/`，不作为生产输入。

### 可配置状态灯与开机动画

按用户要求默认网络灯为 4G 蓝、5G 白、未注册红；Wi-Fi 为 2.4 GHz 绿、
5 GHz 白。LuCI「系统 → LED 配置」提供上述五种状态的独立颜色选择、
两组灯开关与白灯亮度，GPIO 彩灯按其 max_brightness=1 只提供开关能力。
每组先关闭全部 GPIO/PMIC 通道再点选一个发光通道，避免混色；配置
修改触发 procd reload 事件立即应用。旧 led-status/mu300-led 调用转交
同一 F50 灯控 owner，不再另写同名 PMIC 节点。

F50 服务在 S11 启动红/绿/蓝/白跑马灯；S99 完成服务写入 /run 的启动
完成标记并发事件，取消动画定时器后显示正常状态。服务晚启动/重启时
读取标记，不重新播放开机动画；先订阅再复核标记，避免完成事件竞态。
只有启动动画按帧定时切色；启动完成后的灯控依赖既有注册、无线和
配置事件，不增加 AT 查询或持续定时轮询。页面可关闭开机动画。
F50 服务及完成标记服务只在 F50 产品启用，U30 Pro 原有屏幕/灯行为不变。

看板 IMEI1/IMEI2 的括号改为当前实际卡槽名称：本次样机为
IMEI1（内置 SIM1）、IMEI2（外置 SIM1）。mux 切换后名称随实际路由更新，
IMEI 的逻辑编号和号码不交换。只读 logical_cards 由既有物理卡控制器产生，
MU3356 的位置 4/3 分别显示外置 SIM1/2；MU5358、V50 使用各自映射。
主页沿用原有可见状态刷新周期更新标签，不增加 AT 请求或独立轮询定时器。
MU300 仓库同步支持 V50 的内置/外置名称，E5 依用户更正不接入此更改。

### 两路卡源组合及双卡双待

原厂框架 `handleTwoEsimAndTwoPsimBootAction` 分别处理两个 mux，并在
DSDS 开启时允许另一逻辑栈驻网；硬件/原厂流程没有“一内置一外置”的
强制限制。此前只保存了默认上网物理卡，未完整保存非上网栈的选择，
是本移植的缺口，不能把一次启动的 mux 状态称为所有版本的固定组合。

F50 Pro「SIM 卡管理」增加“卡源组合”：分别选择 IMEI1/IMEI2 对应卡源，
只列本机 board_id 真正存在、且能路由到该栈的卡位。board 4 可组合
双内置、两种内置/外置混合、双外置；board 0/1/2 没有外置选项，board 5
只有两个固定外置卡源。外置 SIM1 仍对应 IMEI2，外置 SIM2 对应 IMEI1。

`f50pro-card-pair` 只负责组合事务，实际切换复用现有 RF owner/互斥与
SPACTCARD、SFUN5/3/2/4、原厂 5 秒 GPIO 切换间隔及回放。两个卡源
独立保存到 f50pro_route0/1，单独改上网卡也同步保存实际两路组合。
仅改变非上网栈时不 ifdown WAN；改变上网栈时保留原 autostart 意图。
失败恢复两路及原配置，不自动选择另一张卡。未插卡/关闭射频的卡源也可
保留；不为了验证卡源而开启用户关闭的射频。冷启动的卡就绪判断交由
后续公共 dual-radio 初始化，不在组合回放中重复等待空副卡。

双卡双待沿用公共 radio-allowed/sim-radio/data-sim/mobile-data 和异步作业
机制，只扩展 F50 Pro 产品能力，默认关闭。关闭时两路射频互斥且可都关；
开启双待允许用户分别启用两路，不自行把已关闭的卡打开。默认上网卡
始终单独控制。原 U30 Pro 双栈行为保留，不移植新的默认关闭策略给它。
首次安装只读导入 Android 的实际两路 selector，不写 Android NV，已有
OpenWrt 组合不被导入脚本覆盖。离线回归不代替双实卡驻网验收。

### 本轮离线回归记录

- `20261104-211159-f50pro-complete-pair-standby-ui-regression-61849`：
  15 项卡位/双源事务、16 项公共射频、SIM 页面各布局检查通过。
- `20261104-211423-f50pro-pair-led-final-root-78678`：翻译菜单覆盖、
  当前生产源与 F50 根逐项比对、目标 ucode 编译、灯控映射及生命周期通过。
- `20261104-212008-f50pro-led-pair-ram-trial-94375`：仅生成文件的新版
  RAM 三镜像校验完成，含两路来源及默认关闭双待；没有执行设备写入。
- `20261104-212101-u30pro-isolation-after-f50pro-pair-94406`：同一固定
  staging 切回 U30 Pro 后，原屏幕/电池服务启用，F50 灯控服务及模块
  自动加载入口移除，当前源与目标根及目标运行回归通过。

镜像已包含最新正式源码及模块，而非仅修改实机。上述均为离线检查，
新白灯、双待和卡源组合的实际硬件验收仍待单独授权后执行。

### 新版卡源与双待 RAM 验证（本机 board 4）

用户随后单独授权写入新版备用 B 槽启动镜像、试启动及临时卡源/射频测试，
结束后恢复原配置并返回 Android。记录目录为
`work/f50pro-stock-reference/trial-led-pair-20261105/`；不作为生产输入。

- 经正式 native 启动适配器写入并回读校验三镜像；两槽 BSP 原已一致，
  本轮未重写。Image 沿用前述已验证版本，boot SHA-256 为
  `aa197047ee0d9f2cb45249f61de8af00912c84c972162ca504189e785c01fd30`。
- 启动后实际卡源 `[0,4]`、默认双待关闭、策略与 CFUN 均为 `[0,1]`，
  数据走 sipa_eth8，IPv4/IPv6 外网各 3/3 成功。
- 通过真实 LuCI RPC 异步作业将组合切到 `[3,4]`，再重复应用相同组合，
  最后恢复 `[0,4]`。未使用的逻辑栈保持 RF-off；两次非上网卡源操作期间
  WAN uptime 连续，数据接口未变，没有为未插的外置 SIM2 开启射频。
- 开启双待不会自行启用副卡；显式启用后 CFUN 为 `[1,1]`。关闭双待
  恢复 `[0,1]`。单待下再启用逻辑栈 0，确认为 `[1,0]`；关闭后
  `[0,0]`，最后重新启用数据栈并恢复 `[0,1]`。最终数据联网自动恢复。
- 实际登录网页检查了卡源选项、默认值、可用的双待开关及手机布局。
  新开页面的 SIM/LED 视图无 JavaScript 异常、无横向溢出。
- 两个 PMIC 白灯节点正常注册；5 GHz Wi-Fi 白灯亮度实际为 127。
  临时改为白灯亮度 63，再切蓝灯，确认白灯先熄灭且只有蓝 GPIO 点亮；
  后续还原原配置。当前注册缓存为 NR（rat=11），网络白灯符合规则。
  开机完成标记存在，动画已结束，没有在正常状态继续跑帧定时器。
- 全程 NV daemon 为 writeback=off，eMMC 驱动写保护及块设备只读均为 1。
  观察期间无 CP assert/阻塞告警。恢复原卡源/单待后正常重启，确认
  Android A、boot_completed=1、board 4、卡位 4、DSDS=0、chip=0/psim=1。

本机只有一张有流量的外置卡，因此这里只证明双外置**路由**可配置及
双栈射频可控，不声称已验证两张真实外置卡同时驻网。用户本轮没有目视
跑马灯及实际灯色，保留到下轮确认；GPIO/PMIC 回读不替代目视验收。

用户指出射频区仍只写 SIM1/SIM2，已补为实际物理卡源名称及 IMEI 逻辑
编号；确认弹窗和无障碍名称同时使用此标签。刷新复用已有周期及只读
来源查询，不新增定时器，不改变提交给射频 owner 的逻辑 slot 0/1。
这项文案补齐发生在本轮已返回 Android 之后，未冒充已热部署。
对应 `20261104-213147-f50pro-radio-source-caption-browser-95874` 的三语言、
两种宽度、路由变化/查询失败、确认操作及逻辑 RPC 编号检查通过；
`20261104-213259-f50pro-current-rf-caption-root-95891` 已将最新文案收入
正式 F50 根，94 项当前源比对和目标运行回归通过。

### USB、CPU、NFC 与实体键补齐（2026-11-05）

本轮先只读采集同一 MU3356、board 4、F50ProV1.0.0B22 的 Android：
`work/f50pro-stock-reference/hardware-completion-20261105/`。这些记录
是调查证据，不作为正式构建输入；不能推断所有板号均安装同一种充电芯片。

- **USB 外部供电主机**：原厂 DT 有 bq2560x/vddvbus，但原厂驱动同样
  报充电芯片 I/O 失败，不能把 DT 的节点当成芯片实装证明。F50 无电池，
  新增明确的产品启动参数 `f50pro_external_power_only=1`，由 MUSB 与
  PD 共用，禁止对外升压；数据主机不再因无法取得电池产品的升压 regulator
  而无法启动。必须实际有外部 VBUS 才进入主机状态，支持设备／自动恢复。
  网页标明主机需要有源扩展坞。不绕过原状态机，不直接写充电芯片寄存器。
  U30 Pro 不带此参数，原有主机供电、Type-C 与电池路径保留。
- **CPU 调压与温控**：本机两槽 SML 均通过现有双电压域结构 ABI 检查；
  摘要仅用于证据，不作为固件白名单。沿用原生 SMC、动态 policy/OPP 和
  本机 SML 分区，不另造一套调压实现。原厂 policy0 是六小核、policy6
  是两大核；原厂运行时 SoC 档位为 90/100/105/115°C。随后实际核对 DT
  原始值为 70/85/105/115°C，Android 启动后另有策略调整，二者不能混称。
  OpenWrt 目前保留本机 DT 的阈值及原有保护，不擅自提高到运行时值。辅助 wcn/usb
  温度在原厂也为 124872 m°C，不伪造读数或提高温控阈值。实机首次只查
  原厂零偏移和真实能力，不在适配验证中擅自降压。
- **NFC**：原厂 fm11tag 使用 `/dev/i2c-4`，复位脚空闲高、访问低。
  F50 专属模块从本机 `/ntag_fm11_gpio` 解析 GPIO，默认不自动匹配，
  只由 F50 产品明确加载。原生工具在访问前拉低、正常退出及终止时恢复高；
  新增只读 `probe`，仅读能力容器，不改标签内容。硬件复位入口不存在时
  不虚报支持；U30 Pro 继续原访问方式。手机碰一碰验收不能被只读探测替代。
- **实体键**：用户确认仅有一枚切卡键，默认无功能。复用事件驱动的公共
  keys owner，F50 只处理实际 KEY_HOME（102），忽略原厂通用 DT 中的
  电源／音量占位键。网页可分别保存短按、长按 3 秒的无动作、切换上网卡、
  Wi-Fi 频段或 NFC；默认不切卡、不关机、不额外唤醒灯控。切卡复用
  实际卡源和既有射频事务，不按运营商或内置／外置猜另一张卡。

`20261104-221153-f50pro-usb-data-role-final-kernel-12844` 已编译匹配的完整
Image/模块，Image SHA-256 为
`ed60c65c468aa301b592351e6e687420104506df082ee4900273d4a4df84038e`。
主机使能与状态机共用数据角色判断，手动主机不会仍被原始 ID 悬空挡住；
F50 的 host-idle 阶段也处理外部 VBUS 插拔。原 U30 Pro 的 ID 判断未变。
`20261104-221253-f50pro-peripherals-final-root-trial-16797` 完成 99 项当前源比对、
目标 ucode 编译和原生运行回归。USB 策略、PD 禁止升压、NFC 退出恢复、
按键默认无动作及三语言手机布局均做离线检查；不将其称为硬件验收。
新版 RAM 文件在 `trial-peripherals-final-20261105/`，未获新一轮授权前不写设备。

用户确认只有外置 SIM1 插卡；双外置路由及射频已验证，两张实卡同时驻网
仍待具备第二张卡。灯色目视验收、正式安装／卸载／发布包按本次要求暂缓。

U30 Pro 的 `20261104-221520-u30pro-final-peripherals-isolation-18268`
完成同一 staging 的反向切换检查，F50 专用服务／自动加载项移除，原屏幕／
电池服务、CPU／温控和目标运行回归通过；不额外复制根文件系统。

### 本轮外围硬件实机验证及返回 Android

用户已单独授权本轮 B 槽三镜像及 32 字节 misc 试启动，完成后返回 Android。
记录目录为 `work/f50pro-stock-reference/trial-peripherals-final-20261105/`。

- 写入前核对两槽本机 BSP、原始控制块和机型/板号/卡源；正式启动适配器
  确认 BSP 原已一致，不再改写 BSP。三镜像写入、回读后提交试启动记录。
- MUSB/PD 实际读取到外部供电策略。临时数据主机启动、USB 根集线器
  注册成功，整个过程 Type-C 仍为 sink；随后自动恢复 auto/device，NCM
  管理连接恢复。本轮未接真实有源扩展坞，不冒充外设枚举/传输验收。
- NFC 实际读出 Type 2 标签、872 字节容量，访问前后复位均为高。
  本轮不改 EEPROM/NDEF，也未做手机碰一碰的目视验收。
- CPU 两域实际支持调压，频率表与本机 Android 对应：六小核最高
  2.041 GHz、两大核最高 2.210 GHz，偏移始终为 0。温度、原始 DT 的
  被动档位和 CPU cooling 绑定可读；未擅自改压、改温控档位。
- 实机发现镜像漏带 `mu300-keys`，已在 `tools/u30pro-runtime.py` 注册
  共享 C 源编译，组装入口要求完整 9 项 runtime，目标根检查新增真实
  ARM64 程序摘要、可执行性及调用验证，避免只有服务脚本却缺可执行文件。
  将本次正式构建程序热补到 RAM 后，事件 helper 启动成功；向实际 input
  设备注入短按/长按事件，默认无动作，卡源和设置不变。网页默认值为 none。
- 本轮实际网页初次载入已看到按键、NFC、外部供电主机、CPU 调压和物理
  卡源标签；跨页面自动化遇到 LuCI 异步加载异常，后续登录重试也未完成，
  不记为整套实机网页回归通过，不在没有归因的情况下改 LuCI 核心。
- 原卡源 `[0,4]`、RF `[0,1]`、默认关闭双待均保持；蜂窝 IPv4/IPv6
  外网各 3/3 成功。全程 NV writeback=off，eMMC 软件写保护及块只读为 1。
- 正常返回 Android A，boot_completed=1、board 4、物理卡位 4、DSDS=0、
  chip=0/psim=1。原 Android boot/vendor_boot/init_boot/dtbo 摘要逐项一致。
  本轮 Android 上传 staging 在验证成功后清理，电脑备份及诊断记录保留。

按键构建遗漏的修复通过 `20261105-053232-f50pro-button-runtime-root-regression-20052`
目标根回归。包含该修复的后续 RAM 文件位于 `trial-peripherals-keys-20261105/`；
不声称这些重生成文件已经再次写入机器。正式发布、灯色目视、双实卡驻网仍暂缓。

用户随后要求启动 OpenWrt 自行查看，已复核本机当前 B 槽仍是上述已验证
三镜像，仅写 32 字节临时启动记录重启；原 Android A 不变。进入 RAM 后
补入同一正式构建的按键程序并校验摘要，保留 NV writeback=off 与存储只读。
为手动查看取消了已逐项核对 PID/父子关系/命令行的 600 秒试验回退进程；
机器保持 OpenWrt 供用户查看，主动重启仍回 Android。此操作只控制本轮
试运行，不改变正式默认启动或诊断镜像的超时策略。状态记录在
`trial-peripherals-final-20261105/manual-inspection-start.txt`。

### 查看卡槽默认跟随上网卡

用户手动查看时发现初始页面仍显示内置 SIM1：旧公共前端将缺省选择固定为
逻辑 0，且浏览器旧 session key 无法区分隐式默认和用户主动选择。
修复为缺省自动跟随实际数据栈；`sim_get` 增加只读 actual_sim，来自既有
`/run/mu300-data-sim-actual`，尚未发布时使用已保存的 data_sim 意图。
自动模式先完成这项无 AT 的查询，再发该卡的状态/AT 请求；并发查询去重，
不增加独立轮询。用户手动查看另一栈仍保留，并可明确切回自动。
物理卡名继续按本机板号 mux 映射，不更改 AT/IMEI 的逻辑编号。

选择意图使用新的浏览器 session key，旧版隐式 SIM1 默认不再覆盖当前数据卡；
SIM 管理成功切换数据卡后恢复自动跟随。数据栈改变及物理名称更新复用已有
状态刷新，查询失败不悄悄向逻辑 0 发 AT。网页、接口、英文/土耳其文目录及
正式 sources/finish 同时更新，不只修改实机。

`dashboard_sim_follow.js` 覆盖首次实际 SIM2、actual 与 saved 不同、并发、
外部切卡、手动查看、恢复自动、成功切卡后跟随、读取失败及单卡。
原 SIM 页面控制、60 组主题/宽度/语言选择器布局回归通过。已热部署当前
RAM 机器，实际网页验证自动显示外置 SIM1 → 手动内置 SIM1 → 自动外置
SIM1，实际状态 RPC slot 依次为 1/0/1，数据卡未切换。多页面导航时仍捕获
此前 LuCI 异步加载异常，不据此宣称 LuCI 核心已修复。

### 按键切频段保留 AX 与 Wi-Fi 灯就绪事件

用户反馈按键切频段把 AX 改成 N/AC，随后纠正热点本身正常、只是自动
设置及灯态不对。现场确认旧 `mu300-wifi-band` 确实写死 HT20/VHT，
不是 AIC 或 SDIO 故障，不回退工作驱动。公共脚本现保留 HE 模式，
分别记住两频段的 HE20/40/80 选择；首次 2.4 GHz 默认 HE40，5 GHz
按当前国家允许的信道/带宽使用 HE80。2.4 GHz 不支持 80 MHz，不能
把 AX 与 80 MHz 等同；显式保存的合法 HE20/40 选择不强制覆盖。
SSID、密钥、加密、国家和发射功率不被频段切换重写。

旧灯控由网卡 add 等较早事件读取 netifd radio.up，可能读到启动尚未
完成的状态后一直灭灯。F50 灯控改为直接订阅内核 RTM_NEWLINK/DELLINK，
仅处理选定 Wi-Fi 接口，并查询实际 hostapd ENABLED 状态与频率。
删除早期 net hotplug 刷新入口及其专用事件，正式 sources 刷新移除旧
文件，不让新旧两套 Wi-Fi 刷新共存。正常状态无轮询定时器。

21 项频段/信道回归通过（1 项依赖完整 wifi-scripts 镜像的环境项跳过），
5 项 LED/其他产品隔离测试在 WSL 通过；目标根中实际灯控程序的启动、
配置、注册和 12 项 Wi-Fi 就绪事件生命周期检查通过。源码/服务/退役
入口同时进入正式组装，未重编不变的内核。

热部署后通过用户实际配置的 long=wifi-band 入口往返验证：
2.4 GHz HE40、AP ENABLED、green=1/white=0；随后 5 GHz HE80、AP
ENABLED、green=0/white=127，未靠下一次注册事件或轮询点亮。
最终保持 5 GHz 信道 36、实际 80 MHz，蜂窝 WAN 仍 up；凭据/国家/
功率配置摘要前后一致。记录为
`trial-peripherals-final-20261105/wifi-ax-led-live.json`。这些是软件调用
同一按键动作的实机结果。随后用户确认 NFC 和实体长按均可用；
扩展坞用户验收按要求延后到打包后，不在本轮继续测试。

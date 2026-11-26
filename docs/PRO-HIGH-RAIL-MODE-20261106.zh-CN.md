# Pro 原厂高铁模式指示核查

本次核查原厂状态来源和移植边界，未新增开关、部署程序或修改已生成的固件包。

## 2026-11-26：确认状态值与原厂双卡通知上下文

### 原厂样本与方法

- MU5358：`U30Pro_LTYV1.0.0B05`，`20260203.005521`，来自本机现有
  `U30Pro研究/system_a/system_a/system`。这份样本是官改系统，不能称为
  未修改的官方 B05；以下结论以实际 JAR 内容为依据。
- MU3356：`F50ProV1.0.0B22`，`20260321.130936`，来自现有 B22 解包。
- 两份 `services.jar` 的 SHA-256 分别为
  `dd2a7c6b64cadbf02014dd6d216afabea4f8154276eeb722fc015d0b3cd94200`、
  `aef96edc6f5000220d718aa9cea2d2f52eec2ef5374b1c9b0fcb805c191d6f38`。
- 回核 `NotificationAttentionHelper.SettingsObserver.onChange()` 的 Java
  反编译与原始 DEX 指令。JADX 报告了父类中一处反编译错误，因此另用 DEX
  指令确认本段 `const/4 0`、`const/4 1` 和双卡条件分支，不依赖错误方法。
- B22 `libril-private.so` 与 `librilcore.so` 从已有 RIL APEX 的 payload
  单文件提取；payload 与 B22 原始 `com.unisoc.hardware.rild.apex` 内的内容
  摘要完全相同。没有修改原始 APK、JAR、APEX 或设备。
- 输入摘要、派生 Java/DEX 指令和 AArch64 反汇编留在
  `work/pro-highrail-20261126/`，仅作调查资料，不作为构建输入。

### 状态判断已经确认

两份 `services.jar` 都监听 `high_rail_state0/1`，实际条件等价于：

```java
boolean active = state0 == 1 || state1 == 1;
```

状态变为 true 时调用 `setPlatformHighSpeedFlash()`，变为 false 时调用
`cancelPlatformHighSpeedFlash()`。因此 **1 是原厂判定的高铁激活状态，0 是
非激活状态**。两张卡中任一条栈为 1，整机指示保持激活；只有两条都不为 1
才取消指示。没有发现其他数值的语义枚举，不应把任意非零值都当成激活。
原厂网页属性仍使用 `Math.max(state0, state1)`；这是原厂的整机汇总行为，
不是本项目的显示需求，后者按下面用户确认的当前数据卡范围处理。

### 先前范围：只显示当前实际数据卡（已被下方新决定替代）

- 网页看板和 U30 Pro 屏幕只显示当前实际生效的上网卡状态，不合并另一条
  卡栈的高铁状态。F50 Pro 仅使用网页看板。
- 复用现有看板的实际数据卡来源：已连接 WAN 的实际移动网卡、
  `/run/mu300-data-sim-actual` 及已有的选卡未知标记。不能仅凭 UCI 中的
  保存偏好判定当前卡；网页与屏幕使用同一份已确认状态。
- 只有确认归属于当前数据卡的 1/0 通知才更新其显示；非数据卡通知不影响
  当前提示。切换数据卡时先失效旧状态，再等待新卡的有效状态。
- 未确认归属的 NR0 裸 URC 不能因“只关注数据卡”而直接挂到当时的数据卡上，
  也不能使用最后一次 SPACTCARD 命令对象补齐归属。该归属问题仍按后文的
  原厂上下文证据处理；本轮没有新增运行逻辑。

这证实的是状态位的显示语义，未揭示基带如何判定进入高铁场景，不能据此
编造速度、频段或专网触发条件。原厂观察器对缺失的第二条记录有默认 1 的
读取分支；其注册器会先初始化两条记录为 0。移植时不能把缺失记录当作已
收到进入事件，也不能照搬这个默认值来制造激活提示。

### 归属来自原厂上下文，不在裸 URC 正文

1. `VendorServiceStateTracker.registerOnAtCmdEvent()` 为各条逻辑栈分别构建
   `RadioInteractorListener(phoneId)`，收到文本后写该 phoneId 的记录。
2. `radio_interactor_common.jar` 的 `RadioInteractor.listen()` 明确调用
   `listenForSlot(listener.mPhoneId, listener.mCallback, events, notifyNow)`。
   `onAtCmdEvent(String)` 本身只带文本，归属已在监听器/服务实例中确定。
3. B22 `libimpl-ril.so` 的接收回调 `0x41c20` 先通过
   `s_privateFunctions + 0x18` 得到 socketId，再调用
   `processMiscUnsolicited(socketId, line)`。该函数识别
   `+SPHIGHRAILINFO:`，以通知编号 5031 转发原文，并把 socketId 另作为第 4
   个参数传给 RIL 通知回调（调用点 `0x936e8..0x936f4`）。
4. 上述私有函数表字段的重定位指向 B22 `libril-private.so` 的
   `getSocketIdByChannelID()`，地址 `0x10ac0`。双卡条件下，原厂逻辑通道
   0..2 映射到 socket 0，3..5 映射到 socket 1；这是该原厂 RIL 的通道表，
   不是从状态整数推导出的卡号，也不是实体内置/插拔卡的位置编号。

因此，`+SPHIGHRAILINFO: 1` 这条**裸文本没有 SIM 字段**。原厂能分卡是因为
通知链另有 socketId/phoneId 上下文。当前 OpenWrt 的统一 NR0 URC 事件只
发布 `{channel, line}`，不能把上述原厂通道分组直接套成“NR0 就是卡1”，也
不能用最后一次 SPACTCARD 控制请求的对象冒充自动事件归属。仅凭这两个字段
不能恢复原厂的双卡上下文；接入前还需核对当前接收路径可取得的真实归属。
也不能简单地收到一个 0 就清除两条栈或整机状态，另一条栈可能仍为 1。

本轮仅核实并记录上述静态证据；没有修改 AT owner、网页、屏幕或固件包，
没有进行高铁网络现场验收。

## 输入与证据

- 用户提供的 `D:/111/ZteWebServerPlus.apk`，39,932,884 字节，SHA-256
  `a9240f3912e15a3a8f2d6fdf1e6bccb61fe93f7907e85ed8bec092a7ce1bb02f`。
  本次未重新确认其固件版本，不凭文件名假定批次。
- 已有 F50 Pro 原厂采集 `work/f50pro-stock-reference/ZteWebServerPlus.apk`，
  43,685,661 字节，SHA-256
  `46d5a6b7e0f1cbebcb3b001d8350a86afc89c89d2f23570a0420aedb34f54efc`。
  采集记录标记 MU3356 / F50ProV1.0.0B22 / Android 15 / 6.6.98。
- 同一参考目录的 `vendor-telephony-common.jar`，SHA-256
  `be6b8214b4419190c58f1fd41d6d850663c7a1c7dc56226293576e8d0bb5f8e7`。
- 既有 `work/f50pro-sms-apex/libimpl-ril.so` 的只读字符串和 AArch64 调用分析。

调查文件只作证据，不能成为正式构建依赖，也不能把 APK/RIL 整包收入固件。

## 已确认的链路

1. 两份 APK 的 `res/9j.json` 均声明 `HighSpeedRailMode`，`accessMode` 为 `R`。
   `CellularModule.propertyGet()` 读取 `ElfNetworkManager.getHighRailState()`。
2. `ElfNetworkManager.getHighRailState(int)` 从 Android `Settings.Global`
   读取 `high_rail_state` 加 phoneId；无参方法先检查功能支持，禁用返回 -1，
   启用时返回两条栈状态的 `Math.max(state0, state1)`。这属于设备总体提示，
   不必然等于当前上网卡的状态。
3. 原厂 RIL 识别 `+SPHIGHRAILINFO:`，与 `+UNSOLATCMD:` 一起走原始 AT
   文本的异步通知分支；该位置没有发送开启高铁模式的 AT。
4. `VendorServiceStateTracker$3.onAtCmdEvent()` 检查此前缀，通过 `": "`
   切分，解析其后的十进制整数，写入对应 phoneId 的 `high_rail_state`。
   `registerOnAtCmdEvent()` 初始将该 phoneId 的记录置零，再注册通知。
5. APK 的 `setHighRailState(int,int)` 只是写上述 Android 状态记录，
   不是发给基带的模式控制命令。不能凭这个方法名把它做成射频开关。

因此可确认 Android 的这条提示路径是**被动接收基带状态并显示**，不是用户主动
开启一个网络模式。现有证据没有证明基带判定仅依赖“高铁专网”，也没有证明
具体速度、频段、驻网小区等触发条件；这些属于基带内部策略，不能据此编造判断。

## Pro 接入边界与尚待核实

- 只用于本仓库 U30 Pro / F50 Pro，沿用原厂自动状态提示，不添加手动模式开关。
- 接入现有 AT owner 发布的 NR0 URC；不额外打开串口，不在 NR0 添加控制查询，
  不增加周期探测、GPS/测速推断或网络模式重设。
- Android 从 RIL 提供的 phoneId 区分栈，而当前看到的文本只含状态整数。
  NR0 本身不能证明事件属于 SIM1 或当前上网卡。接入前仍须核实 OpenWrt 实际
  上报中的归属上下文；状态值含义已由上面的 2026-11-26 补充确认，不能用
  最后一次 SPACTCARD 查询对象硬套。
- 重启基带、拔卡或失去有效驻网时不能继续显示旧的高铁状态；未收到可靠报告
  应保留未知态。网页和有屏产品使用同一来源，不把未实现写作已支持。

本次没有高铁网络现场日志，未验证实际进入/退出、两卡同时变化及重启后的通知
重发。刚生成的两个 Pro 完整包尚不包含这项指示功能。

## 2026-11-26 当前数据卡实时查询复核

用户确认当前连接为 U30 Pro。只读核对为 `6.12.94-u30pro-p1`、产品标记 `u30pro`，实际数据卡记录为 0。沿用既有 `mu300.modem at` owner 和 `/run/mu300-at4` 控制队列，查询 `AT+SPACTCARD=0;+SPHIGHRAILINFO?`，返回 `{"ok":1,"reply":"ERROR"}`。这里 `ok=1` 只代表请求完成；基带返回 ERROR，不能视为支持状态查询。未切换物理卡源、射频、上网卡或重启设备。

因此目前已确认的裸 NR0 通知和此查询无法同时满足「只属于当前实际数据卡」「切卡立即重新判断」「不沿用旧状态」三项要求。本轮未把无法分卡的事件挂到数据卡上，未在网页或屏幕加入会误报的指示；该项接入仍待有归属的实时来源。公开搜索未找到该私有命令的文档，不能据此编造其他查询 AT。只读查询原始记录保存在本机 `work/pro-highrail-20261126/current-sim-query.txt`，不作为固件构建输入。

## 2026-11-26 补齐实际设备路径与接收线程：原厂如何分卡

### 新取得的同机型 vendor 证据

从用户提供的 `U30Pro研究/super` 的 `vendor_a` 中按 EROFS 文件路径只读提取
`build.prop`、`com.unisoc.hardware.rild.apex`，再仅提取相关两份库；没有解出另一
份完整 vendor/rootfs。逻辑分区元数据头及表校验通过，原始范围和哈希保存在
本机 `work/pro-highrail-20261126/u30-vendor/extraction.json`。分区布局按
[AOSP liblp 格式定义](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/liblp/include/liblp/metadata_format.h)
读取。本样本的 system 是 U30Pro_LTYV1.0.0B05 官改研究镜像，不将它描述为未修改原厂整包。

- U30 vendor `ro.vendor.build.date=Tue Feb 3 01:00:34 CST 2026`；
  `ro.vendor.modem.tty=/dev/stty_nr`。
- F50 Pro B22 的 vendor `build.prop` 也为 `ro.vendor.modem.tty=/dev/stty_nr`。
- U30 样本提取的 `libimpl-ril.so` 与此前 F50 Pro B22 文件逐字节一致，SHA-256
  `d0e9fca6cc92489d085fd9adfab75e7abe90986da754a1f1c4edc1849652384a`。
  `libril-private.so` 也一致，SHA-256
  `a1873a88702d478f63239e48588f1bcbe5b2dd395ceee77fa0d197c516770b73`。
  这些校验用于确认本轮反汇编证据可适用于两个样本，不是运行时版本/hash 门槛。

### 接收链已闭合

1. `libimpl-ril.so` 的通道工作线程 `0x410d0` 取得逻辑槽位 `s`，计算起点
   `3*s`（`0x41208`）、终点 `3*s+2`（`0x412bc`）。它读取
   `ro.vendor.modem.tty`（键位于 `0x1251e`），用 `%s%d`（`0x207f0`）拼接
   设备路径，并在 `0x413b8..0x413bc` 打开文件。因此这里的通道编号确实对应
   `/dev/stty_nr0..5`，已不只是没有设备名的抽象编号。
2. `0x414bc..0x414cc` 调用 `at_open(fd, channelId, "Channel%d", callback)`，
   callback 为 `0x41c20`。`at_open` 在通道结构偏移 `+4` 保存 channelId
   （`0x39550`），在 `+0x268` 保存 callback（`0x39558`）。
3. 实际读线程收到行后，`0x39c38..0x39c4c` 从该通道结构取回 callback、
   channelId 和原始行，调用 `callback(channelId, line, NULL)`。处理短信的
   另一条回调分支 `0x39964..0x39978` 同样传入当前读取通道的编号。
4. callback `0x41c20` 将 channelId 交给 `getSocketIdByChannelID()`；已确认的
   双卡分支是 `3 <= channelId < 6` 得到 socketId=1，其余得到 0。
   处理 `+SPHIGHRAILINFO:` 时不再解析卡号，`0x936e8..0x936f4` 将原文与
   socketId 一起上送通知 5031。
5. `librilcore.so` 的 `unsolAtCmdInd()`（`0x19e270`）以传入 socketId 索引
   对应服务实例（`0x19e298`），向该实例注册的回调发送原文。Java 侧使用
   `mPhone.getPhoneId()` 建立 `listenForSlot(phoneId, ...)`，该监听器收到原文
   后更新自己的 `high_rail_state<phoneId>`。

双卡配置下的原厂接收分组因此为：

| 原厂读取设备组 | 原厂 socketId / phoneId | 逻辑槽位 |
| --- | --- | --- |
| `/dev/stty_nr0`、`nr1`、`nr2` | 0 | 槽位0 / IMEI1 |
| `/dev/stty_nr3`、`nr4`、`nr5` | 1 | 槽位1 / IMEI2 |

**更正先前提问中的前提：原厂这段代码不是把所有卡的高铁 URC 统一从 NR0
收到后，再从正文恢复 phoneId。它直接保留读取通道的分组。NR0 收到的裸
高铁行，在这份原厂 RIL 中会被标成 phoneId=0；它没有识别“这一行实际来自
槽位1”的额外解析分支。** URC 中的状态 0/1 仍然只表示退出/激活，不能当卡号。

### 对当前 OpenWrt 接入的意义与边界

上述是两个实际 vendor 样本的静态接收/分发证据，不是两卡高铁场景的实机
路由验收。当前 NR0 统一入口规则来自已有 PDP、注册、来电、短信等运行经验；
不能反过来据此声称原厂高铁通知也从 NR0 统一接收，更不能把原厂物理分组
泛化为当前 NR0 上的所有通知都属于槽位0。

现在明确需要核对的是本项目运行条件下这类高铁 URC 的实际路由，而不是寻找
不存在的高铁查询 AT，或重新猜测 phoneId 的枚举。保留现有 NR0 入口和 AT
owner／SPACTCARD／队列；本轮只调查，没有增加 NR3 接收者、改变事件入口，
也没有将裸 NR0 行按当前数据卡或最后一次 AT 选择对象强行贴上槽位。

接收线程的完整反汇编留在 `work/pro-highrail-20261126/readerLoop.asm`，通道打开
和回调片段位于同目录 `ril-caller-410d0.asm`、`at_open.asm`、
`ril-caller-41c20.asm`。这些均为离线调查资料，不成为生产构建输入。

## 当前产品决定：整机提示与屏幕预览优先

用户已明确改用整机级「高铁模式」提示，不再声称属于当前数据卡，也不在
界面绑定 phoneId 或标注卡号。上文“只显示当前实际数据卡”的限制属于历史
调查范围，已被本决定替代；已有原厂通道/通知证据保留，不因此将推测写成
基带触发事实。

- 网页：沿用用户指定的位置与临时启动提示卡片样式，作为整机模式提示。
- U30 Pro 屏幕：在主屏 5G／4G 接入制式胶囊内，文字右侧续接用户提供的高铁
  SVG 图标，保持垂直居中及原有主题风格。激活时显示，退出时移除。
- 先用现有原生屏幕程序的 host simulator 生成预览，供用户看效果；SVG 已由用户在会话提供，原始路径几何已保存至
  `devices/u30pro/assets/high-rail.svg`，仅规范化 XML 命名空间和无关元数据。
- 本阶段不为预览编造一枚替代图标，不将设计样图描述为已经完成实机接入。

### 用户 SVG 的原生屏幕预览

- 图标放在主屏 5G／4G 胶囊文字右侧，与文字同色；18×18 抗锯齿透明度掩模，
  新增只读像素数据 324 字节。设备端不新增 SVG 引擎、Python 或图像解码依赖。
- 源 SVG 和可复现转换入口 `tools/generate-high-rail-icon.py` 已收录。生成的
  `tools/ui/high_rail_icon.h` 由既有原生 builder 的头文件依赖收录；普通更新、
  差分更新仍走同一个 u30pro-panel 二进制，不依赖额外下载图片。
- 原生 UI 接收独立的 `high_rail` 整机标志；仅字符串 `1` 激活，0、空或无效值
  清除。默认关闭。预览阶段仅完成视觉及输入字段；后续事件接入见下节。
- 已通过真实 C 屏幕渲染器 host 编译（Wall/Wextra/Werror），覆盖 5G 和 4G 的
  进入／退出；退出后像素逐字节恢复，网络行之外的画面逐字节不变。
- 预览脚本 `tests/u30pro_high_rail_preview.py`；渲染图、模拟数据说明与完整源码
  摘要位于本机 `work/u30pro-high-rail-preview/`。构建记录为
  `out/build-logs/20261126-130446-high-rail-screen-preview-69405/`。
- 559 项已导入原生源文件的来源校验通过，修改文件适配摘要已同步。
  本轮没有编译正式 ARM64 屏幕产物、组装固件或部署实机；预览的电量、时间、
  网络数据均为模拟值，不代表真实高铁场景验收。

## 2026-11-26：Pro 整机提示接入

范围限定为本仓库的 U30 Pro 和 F50 Pro。MU300、E5 仓库不增加本功能。
F50 Pro 只显示网页提示；U30 Pro 同时在已确认的屏幕制式胶囊内显示用户 SVG。
这是被动模式指示，不新增高铁开关、AT 查询、SIM 归属判断或基带配置。

### 状态与显示

- 既有 `mu300-modemd` owner 在 NR0 处理 `+SPHIGHRAILINFO: 1/0`，包括命令回包
  夹带通知的情形。保留原始 URC、AT 回答、SPACTCARD、命令队列和其他事件。
- `mu300.high-rail` 仅保存本次 owner 进程收到的实时状态，不写文件、不读取旧日志，
  不重放上次启动的结果。初始未知；重复通知不重复发送归一化事件。
- NR0 断开、重开、EOF、打开失败、丢事件或 bridge 重连时归为未知。其他通道的
  高铁通知和丢事件报告不改变它；未明确收到进入通知就隐藏，不猜测当前模式。
- `mu300.modem.high_rail` 是只读内存快照；同名 ubus 事件传递状态变化。网页在
  既有状态刷新周期读取快照，沿用临时启动卡片的位置／样式；错误、未知、页面
  恢复均先隐藏。没有额外网页轮询，也不从慢档小区缓存恢复模式。
- 屏幕 feeder 订阅归一化事件立即传递 `high_rail=1/0`，既有整页快照也带此字段。
  owner 对象消失时立即清除；整页刷新期间发生的事件优先，避免旧快照重亮图标。
  事件使用明确的 `partial:true` 局部 feed；原生 C 回调只更新传入字段，保留短信、
  客户端和 NR／信号数据，默认整页 feed 的清理语义不变。
- 显示为整机模式，不随看板查看卡或上网卡重新解释。英文／土耳其文网页翻译及
  LMO 已同步。设备端新增逻辑为 ucode，无 Python 常驻进程或新增独立定时器。

### 交付

模块随既有 rootfs ucode staging 复制；owner、dashboard、网页和 feeder 使用原来的
同一份生产源码路径。掩模编入原生 `u30pro-panel`，builder 的全部 UI 头文件摘要
会触发增量编译。发布根校验补入新模块和 feeder 的逐字节检查。

已通过既有 runner 编译 ARM64 屏幕程序，产物仍在固定 workspace 的
`artifacts/u30pro-runtime/`；没有重新编译内核、组装固件 ZIP 或部署实机。
来源检查覆盖 559 个导入文件，原始来源 hash 未改变，适配说明和当前 hash 已核对。

### 六轮离线回归

| 轮次 | 核对范围 |
| --- | --- |
| 1 | 实际 ucode 状态机：初始未知、严格 0/1、其他通道、畸形通知、重复通知、快照隔离、重建不重放；连续 40,000 次状态变更 |
| 2 | ARM64 实际 modemd + 私有 ubusd + bridge 协议：空闲通知、AT 回包夹带通知、NR3 隔离、实际事件发送，AT 选择及回包不变 |
| 3 | bridge／NR0 故障恢复、owner 消失，以及屏幕整页刷新等待另一个 RPC 时收到退出事件，防止旧快照覆盖退出 |
| 4 | Chromium：360／1280 宽度、中文／英文／土耳其文共六种布局；进入／退出／未知／错误和卡片位置；保留既有看板与启动页回归 |
| 5 | 实际 Diff Studio generator + OTA Engine：两款 Pro 首次加入、后续更新和撤销；实际普通更新 apply_one 连续两次；保留用户 Wi-Fi／射频设置、壁纸和插件数据 |
| 6 | 原生 C 屏幕渲染器 5G／4G 进入／退出像素恢复、网络行外像素不变；ARM64 屏幕编译；实际 C 回调用真实 blobmsg 编码逐字节核对局部更新保留其他数据；真实 ubus feeder 输入输出和 1,000 条连续 owner 事件不产生 AT 查询 |

测试入口：`tests/high_rail_runtime.py`、`tests/high_rail_browser.py`、
`tests/high_rail_delivery.py`、`tests/u30pro_high_rail_preview.py`。
原生局部更新检查为 `tests/high_rail_panel_feed.py`，编译生产 C 回调并在 ARM64
容器运行，覆盖显式 true、false、缺省、无效状态以及亮屏／息屏。
ARM64 回归使用只读的既有准备根，所有可写内容和消息总线位于一次性容器中；
bridge 和面板服务是测试外设，未连接真实串口、基带或屏幕。
普通／差分交付使用隔离目录和合成旧版本基准；新程序取自生产源码及本轮 ARM64
编译结果，不放宽检查、不写实际 boot。

最终结果：六轮检查通过；实际 ARM64 事件／feeder 矩阵 6 项通过，更新交付矩阵
2 项通过，浏览器六种尺寸／语言组合通过，既有翻译回归 17 项通过。
关键构建／测试日志位于 `out/build-logs/`：

- `20261126-133443-high-rail-native-feed-c-70981/`：实际 C 局部更新回调。
- `20261126-133525-high-rail-runtime-build-final-71012/`：最终 ARM64 屏幕程序。
- `20261126-133625-high-rail-complete-runtime-71056/`：最终事件、断连、并发及 feeder。
- `20261126-133753-high-rail-final-delivery-71092/`：最终产物的普通／差分更新及撤销。

本节记录的是离线验证。尚未在真实高铁环境收到进入／退出 URC，因此不声称完成
高铁场景实机验收；正常信号、数据卡、射频和充电策略均未改动。

## 2026-11-27：网页火车图标与运行提示

网页提示复用用户提供的 `devices/u30pro/assets/high-rail.svg` 两条原始路径，
以 24px 内联 SVG 显示在「高铁模式运行中...」左侧，不添加方括号。图标使用
主题强调色，保留原卡片位置和原有进入／退出／未知时隐藏逻辑。屏幕图标与
URC 后端均不变；MU300、E5 不增加该功能。

图标直接包含在已受管的 home.js，不增加外部资源请求或单独的图标交付依赖。
中英土文案、PO／LMO 同步；普通与差分交付测试加入两份 LMO 文件，继续核对
首次加入、后续更新、撤销和用户配置保留。

六种浏览器尺寸／语言组合核对 SVG 路径与原图一致、图文居中、无方括号及
进入／退出隐藏；翻译与交付回归 47 项通过。日志：
`out/build-logs/20261126-203739-rail-web-icon-17773/command.log`。
离线渲染图位于 `work/pro-high-rail-web-preview/desktop-icon.png`。
本次仅更新源码和翻译产物，未热部署或重打之前已经完成的 Pro ZIP。

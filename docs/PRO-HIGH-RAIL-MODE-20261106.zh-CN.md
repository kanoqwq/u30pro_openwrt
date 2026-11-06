# Pro 原厂高铁模式指示核查

本次核查原厂状态来源和移植边界，未新增开关、部署程序或修改已生成的固件包。

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
  上报中的归属上下文及状态值含义；不能用最后一次 SPACTCARD 查询对象硬套。
- 重启基带、拔卡或失去有效驻网时不能继续显示旧的高铁状态；未收到可靠报告
  应保留未知态。网页和有屏产品使用同一来源，不把未实现写作已支持。

本次没有高铁网络现场日志，未验证实际进入/退出、两卡同时变化及重启后的通知
重发。刚生成的两个 Pro 完整包尚不包含这项指示功能。

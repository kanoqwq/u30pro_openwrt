# Pro AIC 客户端工作模式通知修复

## 用户现场与确认边界

U30 Pro 用户版本为 `u30pro-r20261119.193454-g4b3c497a-s44bcd79d`，
Linux 6.12.94。AP 为信道149、80 MHz，Wi-Fi SDIO 为204.8 MHz、4位、SDR104。
PLR-AL30 显示 AP 下行 VHT MCS9/40MHz/1SS、上行 VHT MCS7/80MHz/2SS；
MLR-AL00 显示 HE/80MHz/2SS。用户要求不再实测，改从源码定位。

确认 `rwnx_send_me_sta_add()` 设置 `STA_OPMOD_NOTIF` 后，错误地把
`link_sta_params->opmode_notif_used` 布尔值填入固件的 `req->opmode`。
Linux 6.12.94 实际头文件区分 `u8 opmode_notif` 与 `bool opmode_notif_used`。
IEEE VHT opmode 的低两位为带宽、4–6位为 RX NSS 减一；因此布尔 true
变成的 `0x01` 恰好表示40MHz/1SS，而80MHz/2SS的 `0x12` 会丢失。

代码错误及其字段后果已经确认，与用户的下行状态高度吻合；用户设备的
实际关联通知入参尚未捕获，不能声称已经实机确认慢速根因或验证吞吐恢复。
同一现场还发现接口总流量被误报为各客户端流量等统计缺陷，本次不混入修复。

## 修改范围

只把固件字段赋值改为 `link_sta_params->opmode_notif`。
通知有无仍由原布尔值控制，其他能力、标志和 AT/供电流程不改。
按客户端真实限制传递：20/40MHz、单流及其他合法通知值仍保留，不强制
80MHz或双流，不通过关闭省电、改功率、改频道或固定速率掩盖问题。

修改位于 U30 Pro/F50 Pro 共用 UMS9632 AIC 驱动 overlay，已在
`devices/u30pro/adaptations.json` 记录原始来源摘要、当前摘要和原因。
两个产品继续使用各自产品标识及配置，无新增机型或固件版本白名单。

## 离线验证与构建

- 新测试编译执行生产代码中的实际通知序列化分支。修复前确认失败：
  通知存在且真实值0时，固件错误收到1；日志
  `20261122-083621-aic-peer-opmode-baseline-96659`。
- 修复后 ASan/UBSan 回归通过，覆盖2种通知状态 × 256个模式字节 ×
  4种已有标志，共2048组；另核对带宽/空间流位，不丢有效的零值。
  日志 `20261122-083712-pro-aic-peer-opmode-kernel-96679`。
- 使用登记的原有 Linux6.12.94 源码/对象缓存，完整 Image/modules 编译
  通过；构建日志确认 `rwnx_msg_tx.o` 和 `aic8800_fdrv.ko` 实际重编：
  `20261122-083811-pro-aic-opmode-native-build-96703`。
- 标准 sources/finish 已更新构建根；253个模块、Image/config/source回执、
  原生 APK 内核元数据核对通过；准备树中驱动源码与正式 overlay 逐字节相同。
  日志 `20261122-084005-pro-aic-opmode-module-delivery-900`。

初次编译调用未指定共用安装器产物目录而停在输入检查；补充显式的既有
产物路径后重跑，没有重编或更新安装器。首次 source 刷新误用只接受
packaged 状态的 refresh-sources；改用既有 sources-installed 状态对应的
标准 sources/finish 入口完成，未修改状态或绕过校验。

不包含本轮设备部署、重启、手机连接或吞吐测试。后续两个 Pro 完整包和
差分均通过既有内核/模块交付路径携带本次修正，不能单凭离线结果宣称测速恢复。

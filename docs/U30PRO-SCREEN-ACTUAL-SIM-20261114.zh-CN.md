# U30 Pro 屏幕误报无 SIM

用户提供的同一台故障机只读快照：保存的 `data_sim=0`，
`/run/mu300-data-sim-actual=1`；逻辑栈 0 为 absent，逻辑栈 1 为 ready。
屏幕发布的状态仍为 waiting-sim。原机 board_id=2，自动形态、
mu5358 布局及两项 GPIO 均与已有映射一致。

屏幕 feeder 原先只按保存的 data_sim 选择 SIM 和信号缓存；公共看板已经
按实际 WAN 与现有 owner 记录解析正在使用的数据卡。保存值与运行状态不一致
时，屏幕误读另一张卡的缺卡状态，显示“无SIM卡”。

feeder 现在先获取公共看板快照，用其中确认的实际数据卡选择状态、信号及
短信；实际卡未知的启动阶段仍按保存值读取。没有根据“哪张卡有卡”擅自切卡，
也不改写 UCI、board_id、GPIO、射频权限或 AT 所有权。原有缺卡、PIN 锁定、
射频关闭和基带无应答的区分保留，没有新增轮询或 AT 查询端。

修改沿用 `devices/u30pro/overlay/` 的正式 sources 安装路径，目标文件为
`/usr/sbin/u30pro-ui-feed`。这是 ucode 适配层变化，不需要重编内核或屏幕 C 程序。

`tests/u30pro_sim_status.py` 从生产 feeder 提取实际读取流程，先复现旧实现
在“保存卡1、实际卡2”时仍读取卡1，再覆盖反向选择、实际卡未知的启动和
真实缺卡。ARM64 ucode 回归以及原有短信阅读、切卡动作回归均使用离线夹具。
不将离线验证视为故障机验收。

此前生成的 `r20261114.134725` U30 Pro 和 `r20261114.135305` F50 Pro
ZIP 早于本次修正，不包含此修复。本次尚未操作用户设备。

## 后续确认的数据连接故障

同一故障机随后提供 WAN `available=false`、`NO_DEVICE`，两卡射频均开启、
双待开启；`sipa_eth0` 到 `sipa_eth19` 均存在，但未启用。
`mu300cell-wan.registration-wait` 为 `0`，拨号错误明确为
`SIM absent; waiting for card state event`。因此该现场并非网卡驱动缺失：
拨号与恢复按保存的卡1等待，基带实际选中卡2不等于主机已选择它拨号。
本轮没有改板号映射或自动把另一张存在的卡持久化为默认卡。

继续检查发现独立的恢复缺陷：用户明确选择实际已选中的卡2时，
`mu300-data-sim apply` 的同卡分支只保存默认卡，不唤醒仍等待旧卡的 WAN。
现在仅在保存目标改变、WAN 确认未连接且未在拨号、autostart 为 true 时恢复
已有拨号路径。对于之前被缺卡判定为不可用的协议，先用现有 `notify_proto`
action 5 恢复可用状态，再执行 `ifup`；仅执行 `ifup` 不会解除 `NO_DEVICE`。
普通异卡切换的成功分支复用同一恢复方法；其 `ifdown` 会清除 autostart，
恢复后仍需显式 `ifup`。运行中的同卡连接、正在处理的拨号以及用户主动
ifdown 均不打断。
物理卡选择原有流程也调用此事务，无需新建 AT 通道、轮询或射频重置。

`tests/test_data_sim.py` 在生产脚本上复现旧分支不重拨，并覆盖双向选择、
手动关闭数据、已连接与正在拨号的边界。故障机尚未反馈重新选择并连接后
的实测结果，不能将离线修复称为该机联网验收通过。用户指出无网后，
本轮尚在进行的 U30 Pro 打包已中止，失败 staging 保留。

最终选卡回归：`20261114-143715-data-sim-wan-final-32533/command.log`，
19 项测试全部通过。夹具同时模拟 netifd 的不可用状态拒绝 `ifup`、
`ifdown` 清除 autostart，确认修复不只在把 `ifup` 当作必成功命令的模拟中成立。
netifd 行为核对依据为上游 `interface_set_up()` / `interface_set_available()`：
https://github.com/openwrt/netifd/blob/master/interface.c 。

故障机后续由用户执行已有物理选卡程序，明确保存内置卡2，并解除旧卡留下的
WAN 不可用状态。返回 `saved_sim=1`、`actual_sim=1`、`data_connected=true`；
WAN 在 `sipa_eth8` 上 `up=true`，同时取得 IPv4、IPv6、双栈默认路由及 DNS。
这验证了该现场的选卡／等待状态原因；没有部署本轮新文件，不将其等同于新版
选卡脚本或屏幕程序已经完成实机验收。随后恢复 U30 Pro 发布组包。

## F50 Pro 及其他仓库范围核对

F50 Pro 的平台仍为 u30pro，物理卡事务最终调用同一份 mu300-data-sim，
因此共享本次恢复修正；没有复制 MU5358 的卡源表到 MU3356，也不接入屏幕 feeder。
F50 Pro 单独执行 tests/test_f50pro_cards.py，20 项通过，日志：
out/build-logs/20261114-145107-f50pro-data-sim-regression-47597/command.log。
共用选卡程序的 19 项回归结果见上文。尚未发布包含本修正的新 F50 Pro 包。

MU300 发现相同恢复缺陷并同步修正，E5 在自己的 Python RPC、e5-sim 和网页
同卡操作分支做等价修复；各仓库记录为 docs/DATA-SIM-ADOPT-20261114.zh-CN.md。
E5 原有信息屏直接读取实际 card 参数，不需要复制本 Pro feeder 修正。

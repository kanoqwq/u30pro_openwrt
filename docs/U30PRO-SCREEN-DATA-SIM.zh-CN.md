# 屏幕切换上网卡

「功能 → 切换上网卡」列出当前 MU5358 板型所支持的卡：内置卡 1／2／3、外置卡。
可见卡来自现有 physical_sim status，当前卡来自 active_card；不将物理卡编号误作逻辑栈。
未知板型、未就绪或读取失败时不开放切换。新增内建菜单项追加在末尾，保留原有 fn 编号。

点击通过原有异步屏幕动作调用 `data-sim apply data u30pro-card-N`，与网页任务使用
同一个验证／物理卡源／射频／拨号适配器，保留 board_id、单待策略、互斥和 eUICC 保护。
不新增 AT owner、URC 读者或周期查询；完成由 token 对应的 `data_sim_result` 返回，
并触发既有 feed 刷新。超时、重复点击和过期结果不会覆盖当前选择。状态不乐观变更。

正式源码在 `devices/u30pro/native/tools/` 与 `devices/u30pro/overlay/usr/sbin/`。
`tools/u30pro-runtime.py` 编译屏幕，组包复制 overlay；根校验比较这两个脚本和原生构建收据。
新增回归 `tests/u30pro_screen_data_sim.py` 进入 native 检查入口，测试真实 C 页面／动作
和 shell 适配器（均使用模拟命令）。本轮 ARM64 已编译，未热部署或执行实机切卡。

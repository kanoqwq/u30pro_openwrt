# Pro CPU0 开关按内核能力展示

2026-11-06 用户连接 U30 Pro 后只读检查：运行
`u30pro-r20261105.200523-g96a594bc-s33cfc29d`、
`6.12.94-u30pro-p1`，`CONFIG_HOTPLUG_CPU=y`，CPU0 的
`/sys/devices/system/cpu/cpu0/online` 存在、内容为 1、权限为 0644。

该 ARM64 内核由 `arch_register_cpu()` 调用 `arch_cpu_is_hotpluggable()`
决定是否提供 hotplug 属性。原网页后端却额外用 `id != 0` 禁止 CPU0，
请求校验也强制 CPU0 在线，造成内核已提供操作入口时仍无法使用。

本次仅修改 Pro 仓库两款产品共用的用户态组件，不修改内核或其他仓库。
所有核心均依据 online 节点的有效内容及写权限判断是否可操作，不再按编号
排除 CPU0；没有节点或节点不可写的核心继续保持固定状态。仍要求至少一个
核心在线，先上线目标核心再下线其他核心；保留内核写入拒绝、同步回读、
失败恢复、持久化与启动重放检查。不增加自动关核策略。

网页说明及中／英／土翻译同步修改，正式 root 校验新增后端和组件的源码
一致性检查；既有通用插件安装路径会收录这两份文件。

离线验证：

- ARM64 OpenWrt 容器运行真实 ucode 及 `tests/cpu_cores_fixture.sh`，覆盖
  CPU0 支持／缺失／只读、全关拒绝、持久化、重放、恢复初始状态、写入与
  保存失败恢复。日志：
  `out/build-logs/20261105-203417-pro-cpu0-hotplug-target-test-35031/command.log`。
- `tests/cpu_cores_browser.py` 检查三种语言、手机／桌面布局、固定核心与
  可操作 CPU0、提交／保存／重置／失败后的控件状态。日志：
  `out/build-logs/20261105-203523-pro-cpu0-hotplug-browser-final-35072/command.log`。

初次离线验证没有在实机执行 CPU0 下线或上线，也没有热部署。sysfs 入口可操作不等于
所有固件均已完成实机验收；PSCI／平台仍可能拒绝具体请求，此时如实报错。
此前已打好的包不包含本次更改。

## 用户随后授权的热部署

同日用户要求热部署至已连接的 U30 Pro。确认产品后，以 SSH 二进制流传输
`cpu-cores.uc`、`cpu-cores.js`、`common.js`，逐文件原子替换、保留权限并回读
校验。旧文件保存在 `/tmp/u30pro-cpu0-hotfix-20261106/`。

原生后端及真实 `ubus call unisoc-cpu-cores get` 均返回 CPU0 的
`online:true,writable:true`。部署前后在线核心均为 `0,6`；未调用 apply，
未改变核心、电压、频率、持久化设置，未重启服务或整机。

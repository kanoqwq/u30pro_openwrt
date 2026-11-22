# 自编内核的 APK 配套

`tools/stage-kernel-packages.py` 是主机端组包步骤，不在设备上运行，
不增加后台服务、轮询或启动时数据库修补。

## 原因与实现

OpenWrt 基础 rootfs 的 `kernel` / `kmod-*` 记录属于 armsr 官方内核，
不能继续用于已经替换 Image 和模块的固件。实际的 `/sbin/kmodloader`
属于已有的 `ubox`，并不是缺少一个必须另外安装的 loader 包。

但这不能直接作为“apk upgrade 后不开机”的根因：已检查的 Pro 和 E5
原始 `world` 本来就锁定官方 kernel 版本，该 kernel 包只登记
`modules.builtin` / `modules.builtin.modinfo` 等文件，不包含启动镜像。
正常软件包升级是否覆盖无线或基础服务的适配、是否真的发生内核启动失败，
仍需故障机的升级事务与启动日志，不能从元数据错配直接推导。

组包完成依赖安装、选择机型内核和部署完整模块后，构建器：

1. 从实际 Image 和全部模块读取 release，拒绝混装；读取该 Image 的配置和 built-in 清单。
2. 使用实际配置、Image、模块内容与能力清单生成包版本。它是动态生成的交付件身份，
   不是写死的固件版本白名单，也不表示相同 `uname -r` 就一定 ABI 兼容。
3. 生成标准 APK，由真正的 apk-tools 在隔离的临时数据库里解析、检查依赖并提取记录。
   临时数据库没有设备文件、服务或网络访问；不在运行中的系统执行卸包预检。
4. `kernel` 拥有实际模块、built-in/depmod 清单和原内核包的有效自动加载文件；
   有证据支持的常用能力拥有真实的 `kmod-*` 元包，依赖精确的本机 `kernel` 版本，
   因而 LuCI 可以显示已安装。未提供的能力不会被冒充为已安装。
5. 保留全部用户态包记录和 world 中的无关选择，固定本机内核及随包能力，
   防止后续无关 APK 操作回收能力记录或把内核换回官方版本。

三个生产入口分别是 E5 的 `openwrt/build-profile-tf.py`、
Pro 的 `tools/u30pro-package.py finish` 和 MU300 双主线内核的
`openwrt/build-rootfs.sh`。通用基础 rootfs 仍可先安装官方用户态依赖，
只在已经确定实际机型内核的最终组包阶段替换内核记录。

部分旧 MU300/E5 内核实际没有提供 rootfs 已安装 PPPoE/legacy iptables
用户态包所依赖的驱动。本次补齐它们的按需模块配置；相关 Image/模块
必须重编，不能拿旧内核缓存配新配置。Pro 原配置已经提供这些能力。

## 更新与边界

普通更新沿用新镜像的 APK 数据库；差分更新沿用共享 OTA 的逐包合并和事务回滚。
共享更新器仅清理“从原始固件移除、且依赖原内核”的 kmod 记录；
不以包名开头相同为由删除用户额外装的包。用户配置及额外软件保留。

信息在 `/usr/share/unisoc-kernel/package.json`，匹配的第三方模块 APK
应按其中的 `package_version` 声明 `kernel=<版本>`，并使用配套源码、配置、
导出符号和头文件构建。这里没有给第三方 feed 的任意
`u30pro-kernel-<标识>` 提供假别名，也没有关闭内核/模块检查。
官方 armsr 的 `.ko` 不会因此变得适用于自编内核；未编译的驱动仍需配套构建。

本次验证的是完整镜像/普通更新与差分更新。历史开发命令单独更换 boot、
仅复制模块或手动切旧内核，不属于一次完整的软件包元数据升级，不能据此
宣称数据库已与另一个内核同步。

## 离线回归记录（2026-11-21）

以下是独立离线回归轮次，不是实机或断电验收：

| 轮次 | 实际执行内容 | 结果 |
| --- | --- | --- |
| 1 | 读取 Pro/E5 基础数据库与 MU300 两内核正式包，核对 ubox、内核记录、实际模块 | 确认旧官方记录残留；实际 loader 已存在 |
| 2 | 实际 apk-tools 安装生成的内核/能力 APK，查询模块文件归属，拒绝外来内核依赖 | 通过 |
| 3 | 重复准备、缺失能力、模块 release 不匹配；失败前后数据库比较 | 通过 |
| 4 | 实际 diff generator + Engine.apply：首次迁移、用户额外包与无线配置保留、事务 rollback | 通过 |
| 5 | 第二次 diff、普通 E5 keep_config 迁移、非本机内核/非 kmod 边界 | 通过 |
| 6 | 连续 12 次真实 APK 操作，检查包版本、依赖、内核选择和配置不漂移 | 通过 |
| 7 | 现有 Pro Image、全部现有模块及完整真实 APK 数据库在隔离根目录组包 | 通过 |
| 8 | 实际 E5、MU300 6.18/7.2 Kconfig 解析新增模块选项；共享 OTA 既有回归 | Kconfig 均接受；213 项 OTA 测试中 212 通过、1 项跳过 |

专用回归：`tools/test-kernel-packages.py`；共享移除边界：
`installer/tests/test_native_kernel_packages.py`。
通过现有 `tools/build-release.py run` 执行，日志在 `out/build-logs/`。

Pro 本轮配套更新器固定到 `760aa2621ebc3d0e526724a88ed1996180ae2e4e`，
Windows、Apple Silicon macOS 和 Android 均已原生重编并校验；
版本锁对应的三份归档已发布至 `build-tools-760aa26`。
Pro 内核配置没有变化，复用经核验的 Image 和 253 个匹配模块。
实际目标根回归通过，并用原版 `b07c028` RAM 执行器迁移真实的 Pro
基础 APK 数据库/world，迁移后真实 APK solver 检查通过。

正式交付以 `release/` 的 ZIP 及 SHA-256 为准，本轮没有实机部署或硬件验收。
MU300/E5 的相关内核配置仍须在它们各自后续打包时重编；
不能手改构建指纹或放宽 OTA 校验来复用不匹配的旧模块。

## Pro 软件源退役与容器能力补全（2026-11-21）

更新后的 U30 Pro 实机只读检查确认：新 Image 配套的 253 个模块逐一与正式 ZIP
摘要一致，更新事务完成，主要服务及 IPv4/IPv6 工作。运行中的 APK 数据库仍保留
7 个用户额外安装的旧官方 kmod 记录；本次实际使用的旧 RAM 执行器不含新能力接管
逻辑。新执行器已经随本次更新安装，但不能倒推本次事务已经使用了它。

另一个独立问题是参考 Pro 源 `33333s/u30pro-store`：实机缓存索引里的
`kmod-ipt-extra`、`kmod-nf-ipvs` 为 `6.12.94_p540-r1`，明确依赖
`u30pro-kernel-89cf01ae97b8` 和其自带 loader。这不是本固件的内核包标识。
不能提供这个旧标识的假别名，让 APK 误装另一套内核的模块。

本机实际配置及模块已经有 Docker 所需的 extra/conntrack/NAT/physdev/IPVS，
此前遗漏的是相应 APK 能力登记。本次增加 12 项配置和真实模块/built-in 共同验证的
能力，Pro 当前输入从 69 项增至 81 项，同时涵盖上述 7 个残留包的功能。
Image、内核配置和驱动未更改。匹配内容在下一次完整组包时重新生成能力 APK，
不会在运行中的系统伪造数据库或放宽模块兼容检查。

两款 Pro 直接删除内置的 `etc/apk/repositories.d/u30pro.list`，停止复制该源公钥；
组包时只清理固定 staging 中这两个旧文件，不扫描或过滤用户的软件源配置。
不新增开机迁移脚本、服务或 RPC，也不改用户自行添加的其他源。
本轮只修改源码，没有热部署或重打 ZIP。

能力补全已通过 `tools/test-kernel-packages.py` 的 12 项离线回归（11 通过，
1 项为 Pro 不包含 E5 普通更新适配器而跳过）。覆盖真实 APK solver、
Docker 所需六项内核依赖、缺模块/禁用配置、差分接管用户旧 kmod、回滚和连续事务。
实际 Pro 配置和 253 个模块/built-in 清单另行核对，新增 12 项均有对应输入。
日志：`out/build-logs/20261121-133652-pro-native-capabilities-and-feed-24602/command.log`。
这些结果不等于已在实机安装并运行 Docker。

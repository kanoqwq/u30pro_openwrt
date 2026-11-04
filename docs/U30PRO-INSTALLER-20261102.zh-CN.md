# U30 Pro 公共安装器接入（2026-11-02）

## 决定和证据

保留本机 Android v4 的 boot、vendor_boot、init_boot 容器。系统仍为 MU300 的
mu300root 分区和 /openwrt 容器，不把 rootfs 放入 vendor_boot，也不采用参考仓库的
reserve2、固定扇区或双槽根系统升级器。

证据为本机 MU5358-20260203 抓取的三镜像：boot 为 64 MiB、vendor_boot 为
100 MiB、init_boot 为 8 MiB；内核、厂商 ramdisk/DTB/bootconfig、Android 通用
ramdisk 分开。此前将新内核和启动内容配套写入后，实机已进入 OpenWrt，用户确认
画面与触摸正常。此证据不是本轮新安装/更新/卸载流程的实机验收。

## 实现边界

公共 UI、日志、无线/有线 ADB、SSH、分区计算、在线保数据缩容、安装记录和卸载
流程继续复用 openwrt-tools。desktop/manifest.json 的 platform=u30pro 显式选择原生
启动适配；其他 MU300、E5 包不启用该适配。机型不匹配仍可输入 yes 明确确认。
启动布局不同不会偷偷切换为另一套硬件实现。

- 初装/重装：动态确定 Android 和另一 Linux 槽；读取本机模板，保留本机 DTB 和
  bootconfig，生成一致的 boot/vendor_boot ramdisk，并清空另一槽 init_boot 的
  Android /init。DTBO 和 BSP 使用本机当前槽，备份并回读，最后提交 misc。
- 临时启动：正常路径仅检查三镜像是否配套、修改 misc；明确修复时先备份另一槽
  的启动容器并重建，再回读并试启动。界面列出实际修复目标。
- OpenWrt 下完整更新：SSH 读取并校验当前 Linux 槽模板，通过同一编码器生成
  vendor_boot/init_boot，在持久系统盘暂存和备份。配套写入失败恢复原容器、根及 misc。
- Diff OTA：补丁只携带一份规范 boot 输入；设备端保留本机配置生成 guard/final
  的配套容器，不在 ZIP 重复塞入三个通用 boot。事务记录包含分区、大小、SHA 和
  恢复文件；更新、断电恢复与撤销都处理配套容器。恢复副本沿用引擎原清理规则。
- 卸载归还空间：维护镜像在存储发现后、挂载系统前进入公共离线卸载器；同时将
  相同维护 ramdisk 放入 vendor_boot，保留原 Android 槽。完成后恢复另一槽 Android
  的 vendor_boot/init_boot/DTBO 及 boot，避免留下 Linux 启动组件。
- Android 挂载前 F2FS 扩容：原生 Android v4 独立 ramdisk 路径使用当前 Android
  槽 init_boot，保留其 kernel/头/参数，仅临时添加 Magisk pre-mount hook；完成或
  失败均按原件 SHA 恢复。仍需实际固件支持原有 Magisk 挂载前工具，不伪造支持。

未加入固件文件哈希白名单；哈希用于本次传输、备份、并发变化和恢复校验。
容器格式、片段表或边界不符会在写入前停止，不能把未知固件结构当已适配。
AVB 元数据容器保留不等于重新签名；本机既有启动链行为不作额外放宽。

## 离线结果及限制

- 公共安装器完整回归：610 项执行，608 通过，2 项因环境条件跳过。
  日志：out/build-logs/20261102-140029-u30pro-installer-acceptance-77679/command.log。
- 前端 TypeScript/Vite 构建通过，10 项协议测试通过；复用已有 node_modules，不复制缓存。
- tests/u30pro_boot_adapter.py：10 项文件模拟通过，包含两种槽位方向、部分写入恢复、
  misc/BCB 失败恢复、卸载配套容器恢复/重试及真实 SSH 更新 shell 函数。
- installer/tests/test_u30pro_boot.py：覆盖动态槽位、三镜像一致性、损坏输入、SSH
  二进制传输、卸载启动标记、OTA 更新/恢复/撤销及用户插件保留。

本轮不连接或操作实机，不修改用户 NV/IMEI，不重启设备。尚需用户授权后的实机
初装/更新/卸载和断连恢复验收，特别是当前固件 Magisk init_boot 的挂载前扩容。
未将离线测试称作硬件通过；本轮没有生成新的 EXE/APK/完整包。

## 生产构建接入

共享编码器唯一源为 installer/runtime/luci-app-unisoc-ota/root/usr/lib/unisoc-ota/boot.py。
完整包将其复制为 desktop/boot-runtime.py 并纳入 manifest 校验及包身份；设备端由
现有 stage-ota.py 收入。桌面、Android 和 SSH 使用同一共享后端，没有移动端专用
刷写分叉。CLI 通过有包上下文的后端入口加载，避免相对导入在打包后失效。
原生安装器改动先提交到子模块，再在本仓库固定 gitlink；E5/MU300 参考仓库不修改。
新源码要求重建匹配的安装器交付件，旧 artifact 的源码指纹检查不可绕过。

## 2026-11-03：慢链路原生启动容器备份

已确认 vendor_boot 下载曾被共享元数据助手的 120 秒预算提前终止。U30 Pro 随包 Android.download 在调用实际桌面／内嵌 Android ADB 传输时，给 pull 保留至少 888 秒；更长的显式预算不缩短，其他命令的超时与哈希校验不变。调整位于三个控制端共用的可移植包入口，不修改已冻结 GUI 后端，也不改变 E5/MU300 适配器。

## 2026-11-04：卸载维护启动及原记录重试

已从本机卸载事务的实际 boot-uninstall.img 确认：通用载荷没有
etc/mu300-desktop-root-mode，而原生等待脚本必须读取它。缺失时在存储发现后
进入救援分支，执行不到卸载 worker；强制重启返回 Android 后，GPT 仍为原样。

共享安装器的 U30 Pro 卸载分支现在明确携带 prepare 模式；仅让等待脚本确认
userdata/misc，随后直接进入卸载 worker，不调用安装、格式化或根挂载流程。
因此首次卸载和 mu300root 已移除后的维护启动均不依赖 OpenWrt 根分区。

用户明确继续旧失败记录时，先证明两份 GPT、Android boot 和原维护启动配套
容器仍匹配，再用当前安装包重新准备一次维护启动。原备份保留；验证失败即停止，
再次失败不会自动循环重启。其他机型及清空 Android 的路径不使用这一专属重试。

测试覆盖两种 A/B 方向、eMMC/UFS 节点、OpenWrt 分区存在/已移除、缺配置的
负对照、启动内容变化拒绝重试及写入异常传播。均为离线文件/模拟节点验证，
不代表本轮已在实机完成卸载。

### 同日复查：规范载荷漏带早期存储依赖

第一次修正版仍停在 Logo。无线 ADB 读回确认 Android B 正常，Linux A 的
boot/vendor_boot/init_boot 摘要与这次卸载写入记录一致；主备 GPT 均与卸载前
备份逐摘要一致，尚未执行空间归还。pstore 没有留下上次启动日志。

对实际 boot-uninstall.img 解包后发现：虽然 prepare 配置已补齐，完整 init
仍在卸载 hook 之前 source /etc/mu300-desktop-storage.sh，但规范载荷没有该文件。
此前测试只直接调用等待函数，并自行提供拓扑函数，遗漏了整个 init 的依赖。

现将早期只读发现改为 source /etc/mu300-storage.sh，并由 canonical_boot 正式
收入同一份共享拓扑库。安装/挂载策略的 source 移至 storage-ready hook 之后，
卸载镜像在该边界截断，既不缺发现依赖，也不进入安装、格式化或根挂载路径。
不改内核、AT、NV 或其他机型的维护入口。

完整 init 离线回归运行于私有 chroot，使用真实共享拓扑解析与合成 sysfs/block
节点；仅把宿主挂载、USB 配置和卸载 worker 换为无写入桩。覆盖双向 A/B、
eMMC/UFS、根分区存在/不存在，以及缺必需库时禁止到达 worker 的负对照。
正式组包另从实际规范载荷生成两槽维护镜像，检查其早期 source 依赖齐全。
这些验证不是实机卸载验收；本轮只读核查没有改设备分区、数据或 NV。

### 准备阶段的旧进程扫描空转

同机继续原记录时，实际主机日志停在对旧 worker 的 /proc/*/cmdline 扫描。
只读检查确认 Android toybox tr 持有一个已退出进程的 cmdline fd，数分钟内
read 调用达七亿次且没有输出；该原生记录已 committed，却仍重复检查旧进程。
终止这条扫描后还确认该机 su 会掩盖被终止命令的退出状态，因此单靠退出码
不能认定检查已完成。经用户允许，在本轮分区写入前暂停并关闭电脑端后端；
原事务、电脑备份及设备的原启动镜像均保留。

已完成记录不再扫描旧 worker；确有中断写入时，使用随包 BusyBox 的 pgrep
匹配原生 worker 的完整调用形式，由同一 BusyBox timeout 限定为 5 秒。
必须收到明确的 busy/idle 标记；超时、缺工具、空响应或 su 误报成功均停止
本次准备，不能进入新写入。原生 Android 配套分区恢复也复用同一个检查函数。
该同机只读检查约 0.22 秒返回 idle，没有启动服务、刷写或重启。

测试使用真实随包 BusyBox、普通进程与文件模拟，覆盖直接/namespace 调用、
仅在命令文本中提及路径、进程退出、真实超时和被掩盖的外层退出码；中断
用户记录的恢复方法另在内存副本上通过，未改原记录或设备。相关卸载回归
90 项中 89 项通过、1 项因宿主旧 F2FS 工具跳过；原生启动容器 15 项通过。

原生刷写器还要求收到脚本在镜像和 misc 全部回读校验后输出的完成标记，
才把 receipt 记为 committed；su 返回零但缺少完成标记时，保留未完成记录
供回读恢复，不宣称写入完成。完整文件模拟验证已覆盖该情形。

## 2026-11-04：删除旧记录后重新发起卸载

当前流程不再要求恢复已删除事务。U30 Pro 在 Android 正常启动、内置 OpenWrt
分区仍存在时，可以把备用槽的原生维护镜像作为当前待备份状态；重新核对
双 GPT、空闲文件系统、已完成的 OpenWrt 标记、u30pro 平台标记和 Android
槽位，生成全新的卸载计划、分区快照和启动备份。旧维护请求里的参数不作为
新的分区规划输入，也不读取旧安装历史来推断容量。

只允许该机型的重新卸载入口检查这种维护启动镜像；普通启动、安装和扩容
继续拒绝未完成维护。已存在且匹配的中断卸载记录仍可续接；其他机型原流程
不变。新记录再次在实际备份前复核同一组设备证据，不跳过校验或自动清数据。

新增测试覆盖双 A/B、空记录目录、当前系统标记、错误槽位/平台/占用/伪造
维护标志，以及从新计划经过新备份到维护请求准备的完整模拟路径。相关卸载
95 项中 94 项通过、1 项因宿主工具跳过；启动相关 19 项通过。重编 Windows
EXE 另运行四项实际冻结后端的关键路径测试，均使用合成设备，不访问真实分区。
本轮没有执行实机卸载或写入 NV；最后的实际空间归还仍需用户确认执行。

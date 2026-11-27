# F50 Pro 安装准备被原厂选卡记录中断

## 现场与复现

用户提供 F50 Pro / MU3356、board_id=4 的安装诊断。完整包为
`f50pro-r20261126.204945-g3ec8289d-se26fed96`；安装选择保留 Android，
使用已有 GPT 空闲空间。两次都在 `prepare` 的 `android-image.sh` 失败，
ext4 创建和三个关键根文件校验通过后没有具体错误文字。

后续 Android 只读输出：

- `zte_webserver_sim_slot_id=0`，双待设置为 0。
- `gpio_sim_ctrl=10`（检测输入 1、选择输出 0），`gpio_sim_ctrl_psim=0`。
- 三份原厂 modem XML 及 AIC8800 固件均存在。

依既有 MU3356 原厂映射，两栈实际卡源为 `[3,4]`，均为外置卡；保存卡源
0 则是内置卡。仅凭这些数据不能确认 Android 当时真正使用哪一栈上网，
也不能推断保存记录为什么与选择器不一致。

旧 `f50pro_import_card` 在该快照下返回非零且没有诊断。外层 importer 的
`set -e` 将可选的原厂设置导入当作必要运行文件失败，直接中止镜像准备。
隔离 Android 路径运行实际脚本可复现此退出；无需写 GPT、boot、misc 或 NV。

## 修正与范围

- 可选快照无效返回 2，与写文件失败的返回 1 分开。所有快照检查仍发生在
  生成首次配置之前，不导入不完整卡源组合。
- Android importer 仅对返回 2 打印明确提示，保留新 OpenWrt 的默认配置并
  继续准备；不猜测当前上网栈，不切 GPIO、射频或修改 Android 设置。
- 有效快照仍导入原有卡源、默认数据栈及单待策略；首次配置继续保护已有
  OpenWrt 的显式选择。RAM 试运行调用者仍将无效快照作为失败处理。
- 创建目录、写入及追加首次配置失败均返回错误，不能被当作可选设置跳过。
  modem XML、原厂 Wi-Fi 固件、镜像和后续 GPT/boot 完整性检查不变。

修改位于 Pro 仓库的 F50 Pro 板级 helper 和 Android importer，不修改共享
安装器子模块、内核、U30 Pro 卡源表、MU300 或 E5。正式组包原本就从
`tools/mu300-vendor-from-device.sh` 复制载荷，从 F50 Pro overlay 复制 helper；
桌面 EXE、macOS App 和 Android APK 共用这些外置载荷，无需重编未变的前端。

## 离线回归

`tests/test_f50pro_vendor_import.py` 在 dash、bash、BusyBox ash 下执行实际
importer，Android 文件、命令和根目录均重定向到独立夹具。覆盖现场快照、
其他不一致记录、部分/全部缺失选择器、正常双卡源导入、XML/固件缺失、
目录和文件写入错误，以及 U30 Pro 隔离。既有卡源和射频事务回归同时重跑。

旧行为复现日志：`out/build-logs/20261127-121731-f50pro-stock-import-reproduce-40990/command.log`。
首轮修正 7 项通过：`20261127-122056-f50pro-stock-import-fix-41622/command.log`。
扩展矩阵：`20261127-122145-f50pro-stock-import-regression-42412/command.log`。
该轮原有 26 项 F50 Pro 卡源回归通过；新增写入失败夹具最初使用 PATH 中的
cat 桩，不能覆盖 BusyBox 内置 applet。改用隔离目录内指向 `/dev/full` 的
文件后，实际写入错误可被所有 shell 观察；没有为适配夹具改动生产逻辑。
最终 importer 与已有导入用例 13 项通过：
`20261127-122609-f50pro-stock-import-final-66896/command.log`。
补齐 M3 入口后的 Pro 最终矩阵 54 项中 53 项通过、1 项因测试进程为 root
而跳过：`20261127-122927-pro-installer-m3-stock-final-77320/command.log`。
这些是离线结果，尚不代表故障设备已重新安装成功。

# U30 Pro / F50 Pro 原生构建输入

此目录随普通 Git clone 获取，不使用 Git LFS，不需要访问原作者的私有仓库或 Release。
`u30pro-native-inputs-20261107.tar.xz` 为约 7.6 MiB 的普通 Git 文件，仅包含：

- 3 份通用启动模板：boot、vendor_boot、init_boot。
- 3 份基带布局 XML：modem_cp_info、modem_sp_info、modem_ch_info。
- 7 份 AIC8800 固件及配置。

构建直接读取本目录的归档与 `MANIFEST.sha256`；归档摘要固定在
`tools/public-inputs.lock.json`，解包时再次校验每个成员。现有工作区只复用摘要相同的
模板／固件文件，不从邻近仓库、旧固件包或私有 Release 补缺。

`ORIGIN.json` 记录原始归档和原始清单的 SHA-256、13 个保留成员的来源路径及摘要，
以及当前精简归档的摘要。归档保持这些成员的原始字节，移除了其他研究文件和重复输入。
维护工具 `tools/export-native-build-inputs.py` 可以从已核验的原归档重现此精简包；
普通用户编译不需要原归档，也不需要执行该维护工具。

这些是硬件模板／固件资源，并非本项目重新授权的开源驱动源码。
驱动与工具的源码来源及许可见上级目录的 `reference.json` 和 `native/LICENSE`。
此处不包含用户 NV、IMEI 工作数据或整机备份。

模板只用于通用载荷生成和离线验证。实际安装器继续读取目标机器自己的
Android 启动容器、DTB 和动态槽位信息，不直接将此处的模板当作用户机器的原厂镜像刷入。

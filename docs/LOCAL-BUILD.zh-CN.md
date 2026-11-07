# U30 Pro 本地构建规范

其他用户首次构建请按 [BUILD.zh-CN.md](BUILD.zh-CN.md)。以下是维护机的既有缓存规则；
其中 `/home/kano` 和 Windows 路径不是公开构建的必要条件。

本仓库从用户的 MU300 `minikano-openwrt-feats` 分支创建，现为独立仓库
`kanoqwq/u30pro_openwrt`，维护分支 `main`。
这里构建 U30 Pro，不是 MU300/F50/V50/U30 Air；不能使用它们的 Image、模块、
SC2355 固件或单 boot 安装布局。硬件代码来自 [移植记录](U30PRO-PORT.zh-CN.md)。

现增加 F50 **Pro**（MU3356）机型入口，它不是旧 F50（UMS9620）。两款 Pro
共用此仓库同一份已核验的 UMS9632 内核及对象缓存，机型配置和 SIM 拓扑独立。
`--profiles u30pro-6.12` 为兼容原行为的默认值；
`--profiles f50pro-6.12` 选择无屏、无电池、MU3356 布局。
`--profiles all` 按顺序构建两款，用同一个受锁定的根 staging 切换明确配置，
不会复制第二份完整根或内核树。不能同时在该 staging 组装两个机型。
使用 `run` 手动执行 sources/finish/package/canonical_boot/test-u30pro-root.py 时，
同样须给 runner 指定对应的 `--profiles`，它会传递 UMS9632_MODEL。

## 固定环境

| 内容 | 路径 |
| --- | --- |
| Windows 源码 | D:/Git/u30pro_openwrt |
| WSL 源码 | /mnt/d/Git/u30pro_openwrt |
| Linux 工作区 | /home/kano/openwrt-build |
| 已有 Linux 6.12.94 源码 | 工作区 sources/u30pro-linux-6.12.94 |
| 已有独立对象缓存 | 工作区 objects/u30pro/release |
| 默认公开输入登记 | tools/build-layout.json、tools/public-inputs.lock.json |
| 本机缓存覆盖 | tools/build-layout.local.json（忽略，不自动选择） |
| 原生输入归档 | 仓库 devices/u30pro/build-inputs/（普通 Git 文件） |
| 提取后的模板与板级资源 | 工作区 cache/u30pro-inputs/templates、artifacts/u30pro-board |
| 固定版本原生安装器产物 | 工作区 artifacts/u30pro-installers/<固定提交>（公开 Release 下载并校验） |
| 日志 / 状态 | out/build-logs/、out/build-state/ |
| 后续正式交付 | release/ |

原生构建输入归档随仓库提供，逐成员校验后将通用启动模板提取到
工作区 `cache/u30pro-inputs/templates/`，不再访问原作者的私有 Release。
安装器仍以目标设备自己的启动容器和槽位生成镜像。
缺失输入必须报出，不能从 MU300 或 E5 包里补一个相似内核/根。
登记的现成对象缓存不等于新源已编译；修改驱动后要重编 Image 和完整模块。

## 检查与离线测试

在 WSL Ubuntu-22.04 执行：

```sh
cd /mnt/d/Git/u30pro_openwrt
python3 tools/build-release.py build --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --jobs 4
python3 tools/build-release.py check --config tools/build-layout.local.json --workspace /home/kano/openwrt-build
python3 tools/build-release.py run --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label u30pro-native-regression -- \
  taskset -c 14,15 nice -n 19 ionice -c 3 sh tools/test-u30pro-native.sh
```

`check` 校验源文件来源、显式输入、公开启动模板及其摘要；不访问实机。
测试使用合成 PTY 和临时目录，不连接真实 AT 端口或 NV。

内核编译入口（需要重编时再运行）：

```sh
python3 tools/build-release.py run --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label u30pro-kernel -- \
  taskset -c 14,15 nice -n 19 ionice -c 3 python3 tools/u30pro-build.py kernel --jobs 2
```

内核 builder 在登记的现有源/对象树增量构建，使用 U30 Pro 配置断言。
不会寻找原作者 `/home/sunyi` 路径，不新克隆 Linux，也不创建第二份根文件系统。
`--configure-only` 可仅解析配置，但仍修改登记的配置/准备树，必须经过 `run`。
不要直接运行 native 参考目录中的历史 builder 或尝试它未导入的旧流水线。

## 发布状态

U30 Pro 采用 MU300 mu300root 容器，根文件系统内是 /openwrt，绝不采用参考库
的独立 overlay 或固定扇区。动态三镜像只适配启动硬件，原 Android 槽不写入。

准备依赖后的固定根 staging 分阶段操作：

```sh
python3 tools/build-release.py run --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label runtime -- python3 tools/u30pro-runtime.py
python3 tools/build-release.py run --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label sources -- python3 tools/u30pro-package.py sources
python3 tools/build-release.py run --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label root -- python3 tools/u30pro-package.py finish
python3 tools/build-release.py run --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label native-boot-test -- python3 tests/u30pro_boot_adapter.py
python3 tools/build-release.py run --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label target-root-test -- python3 tools/test-u30pro-root.py
python3 tools/build-release.py package --config tools/build-layout.local.json --workspace /home/kano/openwrt-build --label u30pro-release
```

首次且 staging 不存在时，先在 runner 中运行 bootstrap、dependencies；不能在准备根
上重新解包基础归档。sources 仅刷新本工具所管理的源/模块；finish 物化配置和服务。
失败的 package staging 保留供检查，不得手动覆盖。发布只包含一个 rootfs 和一个
规范 boot，实际设备三镜像在电脑端使用本机模板构造。

Windows/Android/macOS 安装器复用公开 Release 中经源码指纹和文件摘要校验的
固定产物；变化才重编，绝不调用旧目录的构建 worker。

也支持与 E5/MU300 相同的 `OPENWRT_GUI_ARTIFACT`、
`OPENWRT_GUI_MACOS_ARTIFACT`、`OPENWRT_GUI_ANDROID_ARTIFACT` 显式输入。
本机三仓库安装器提交一致时，也可显式指向某个已验证的共用产物目录；
默认由公开 Release 下载，不需要 E5 仓库或被 Git 忽略的 `installer/artifacts/`。
只构建一次，不复制 SDK、Cargo、
Gradle 或整份原生工具。每项仍独立校验当前源码与哈希，
校验失败不会改选默认目录；未指定的项目才使用 `build-layout.json` 登记的本仓库默认值。

不迁移到 C 盘，不重复 SDK/node_modules/Cargo/根文件系统，不自动删除缓存、
旧包、设备备份或失败 staging。Mac 安装器需原生 macOS CI 时再使用已获授权的
上游 CI，不寻找用户不存在的 Mac Agent。

## 2026-11-02 完整安装包构建记录

当前安装器产物登记到本仓库 installer/artifacts，Windows/Android 本机原生构建，
macOS 使用固定 installer 提交的 Apple Silicon CI，三者均先校验源码指纹，不能
从旧包复制 EXE/APK 冒充新构建。完整安装包不再使用 preview1 文件名后缀；这不
等于已完成所有硬件验收。

复用已有 Rust target 时，要确认当前 Android 项目 generated/ 下存在 TauriActivity.kt、
WryActivity.kt 等官方生成类。切换工作区后若 Cargo 复用了旧目录的生成步骤，可对
既有生成类更新时间戳，触发原版 build.rs 重生成；不要复制或修改第三方模板。
Windows C/D 跨盘 Kotlin 缓存报 different roots 时，本次构建通过进程环境设置
ORG_GRADLE_PROJECT_kotlin.incremental=false 和
ORG_GRADLE_PROJECT_kotlin.compiler.execution.strategy=in-process，不改全局 Gradle
设置、不清 SDK/依赖缓存。命令和回执保留在 out/build-logs/。

固定 staging 重新收录源码用 sources，接受 root-ready 和 packaged 状态；随后 finish。
刷新前核对缓存归属、OpenWrt 基底及 U30 Pro 机型标记，不依赖上一版 ZIP 是否仍在原目录。
Image.wrapped 若属于旧 Image，先检查并运行
clean-staging，仅清本工具拥有的组包/包装输出，再由 canonical_boot 重生成。

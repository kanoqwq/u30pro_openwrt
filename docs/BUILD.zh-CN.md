# 从公开源码构建 U30 Pro 固件

支持 Linux x86_64；Windows 可使用 WSL2 的 Ubuntu。构建不需要连接设备，
不需要个人分区备份、NV、其他固件仓库或 GitHub 登录。

原生硬件输入随仓库提供。安装器子模块、三平台预编译输入和下载摘要使用同一固定
提交；安装器缓存目录由该提交自动生成。源码指纹或文件摘要不一致时仍会停止，
不能跳过校验或用旧二进制冒充新版。
缓存位于 `{workspace}/artifacts/openwrt-tools/<提交前7位>/`，与 E5 使用相同目录规则。

## 准备主机

Ubuntu 22.04 / 24.04 安装依赖：

```sh
sudo apt-get update
sudo apt-get install -y git python3 build-essential clang llvm lld cmake ninja-build \
  pkg-config bc bison flex libelf-dev libssl-dev libncurses-dev rsync cpio \
  xz-utils zstd lz4 patch curl ca-certificates openssl file kmod \
  docker.io qemu-user-static binfmt-support
```

启动 Docker。构建中的 ARM64 OpenWrt 容器使用
QEMU/binfmt；安装上述软件包后可执行 `sudo update-binfmts --enable qemu-aarch64`。
WSL2 也可以使用已启用 WSL 集成和 ARM64 模拟的 Docker Desktop。

## 克隆并构建

```sh
git clone -c core.autocrlf=false --recurse-submodules https://github.com/kanoqwq/u30pro_openwrt.git
cd u30pro_openwrt
sudo python3 tools/build-release.py build --workspace "$HOME/openwrt-build" --jobs 4 --label public-build
```

默认构建 U30 Pro。F50 Pro（MU3356）使用同一仓库的独立机型配置，命令增加
`--profiles f50pro-6.12`；两款顺序构建使用 `--profiles all`。
F50 Pro 的实机验收状态见 [F50PRO-PORTING.zh-CN.md](F50PRO-PORTING.zh-CN.md)，
源码／构建入口接入不代表全部硬件已经验收。

默认工作区为 `~/openwrt-build`。首次构建需要下载、解压及编译依赖；后续使用同一
工作区增量构建，不再复制 Linux 源码、SDK 或根文件系统。最终 ZIP 和 SHA-256
位于仓库 `release/`，日志位于 `out/build-logs/`，最新状态位于
`out/build-state/latest.json`。

完整根文件系统的组装需要 root 权限，以保留系统文件的所有者和访问权限；因此
构建命令使用 `sudo`，并在提权前展开当前用户的工作区路径。不要改用另一个 HOME
再创建一套缓存。只读 `check`／`status` 不需要提权。

只准备依赖时使用 `bootstrap`；依赖准备后可以只读检查：

```sh
sudo python3 tools/build-release.py bootstrap --workspace "$HOME/openwrt-build" --jobs 4
python3 tools/build-release.py check --workspace "$HOME/openwrt-build"
python3 tools/build-release.py status
```

可用 `--workspace /absolute/path` 明确选择工作区。以 root/sudo 调用时应明确传入
原有工作区，避免因用户 HOME 不同再下载一份缓存。

## 输入从哪里来

所有默认下载 URL 和 SHA-256 固定在
[`tools/public-inputs.lock.json`](../tools/public-inputs.lock.json)：

| 输入 | 公开来源 |
| --- | --- |
| Linux 6.12.94 | kernel.org 官方源码归档 |
| OpenWrt 根文件系统、ARM64 musl 工具链 | OpenWrt 25.12.5 官方下载站 |
| json-c / libubox / ubus / UCI 开发库与头文件 | 从 OpenWrt 对应版本的公开源码归档编译，供链接使用；不替换系统运行库 |
| BusyBox | busybox.net 官方源码，本仓库编译为静态 ARM64 程序 |
| AT 传输和硬件服务、屏幕程序 | 本仓库和已固定的原生源码，现场编译 |
| 启动模板、AIC 固件和基带 XML | 本仓库 `devices/u30pro/build-inputs/`，13 个必要文件的精简归档，按成员摘要提取 |
| Aurora 主题 | 作者公开的固定版本 APK |
| Windows / Mac / Android 安装器 | 公共安装器仓库 `build-tools-ab2f30c` 公开 Release，与安装器子模块提交及构建指纹绑定 |

构建会校验下载文件及提取成员，复核安装器文件和源码指纹。失败即报告具体输入，
不会读取旁边的 E5/MU300 目录、旧安装包、个人备份或任意其他缓存来填补缺失项。
安装器二进制来自对应原生平台的构建；Linux 不伪造 macOS App，APK 不包含私钥。
安装器源码始终通过 `installer/` 子模块公开；需要修改安装器时，应在相应原生
平台重编并更新所选构建输入的版本及校验值。

原生输入已经纳入普通 Git 文件，不通过 Git LFS 或私有 Release 下载。
原作者的 `u30pro-build-inputs-20261025.tar.xz` 仅是历史来源，已不是普通用户的构建依赖。
精简包、来源和逐成员摘要见
[`devices/u30pro/build-inputs/README.md`](../devices/u30pro/build-inputs/README.md)。

公开启动模板只供构造通用分发载荷和离线测试。实际安装仍从**目标设备本身**读取
Android 槽的 boot / vendor_boot / init_boot / dtbo，保留其 DTB、启动容器和槽位关系；
不把模板设备的分区位置或启动镜像直接写到用户机器，也不把任何用户 NV 打入固件。

## 已有维护机的缓存

已有维护机可以显式选择 `--config tools/build-layout.local.json`，文件通过
`"extends": "build-layout.json"` 覆盖本机缓存、已登记内核源或编译器位置。
它不进入 Git，不是其他用户的必要输入，也不会被默认自动选中。
本机 `/home/kano/openwrt-build` 的操作规则见
[LOCAL-BUILD.zh-CN.md](LOCAL-BUILD.zh-CN.md)。

刷新已经打过包的根文件系统不依赖旧 ZIP 是否还在；仍核对工作区归属、系统基底、
机型、当前源码、Image/模块及原生运行程序。失败的下载或组包现场保留供排查，
不自动清理用户备份、历史包或编译缓存。

# Agent：U30 Pro 构建入口

先读 [公开构建指南](BUILD.zh-CN.md)、[LOCAL-BUILD.zh-CN.md](LOCAL-BUILD.zh-CN.md) 和
[U30PRO-PORT.zh-CN.md](U30PRO-PORT.zh-CN.md)。

- 本地路径 `D:/Git/u30pro_openwrt`，独立仓库 `kanoqwq/u30pro_openwrt`，维护分支 `main`。
- 基底为用户的 `minikano-openwrt-feats`，不得改用 MU300 main。
- 内核为 U30 Pro 原生 6.12.94，不是 MU300 的 7.2/6.18。
- F50 Pro / MU3356 已有独立产品配置：`--profiles f50pro-6.12`。
  平台 ABI 仍为 u30pro，产品标记为 f50pro；不要把它当作旧 F50 的安装布局，
  不要复制另一套内核或 rootfs。两款共享内核对象，产品构建按顺序使用固定 staging。
- `tools/build-layout.json` 默认只使用公开依赖；首次运行 `build` 会自动准备并校验。
- 本机复用原有内核缓存时，显式传 `--config tools/build-layout.local.json --workspace /home/kano/openwrt-build`。
  这个被忽略的本机配置只覆盖缓存选择，不是其他用户的构建前提，也不自动搜索其他仓库。
- 编译/测试通过 `tools/build-release.py run --label <名称> -- <真实命令>`；
  默认低占用，现有工作区锁与 E5/MU300 共用。禁止生成临时发布 worker。
- 测试命令、内核命令及目录归属见 LOCAL-BUILD。
- 当前为稳定维护固件；通过 build/package 入口组装 U30 Pro 的根、驱动和启动容器，
  不能把 MU300 ZIP 改名交付。每轮新改动的离线检查仍不代表新的实机验收。
- 原 U30 Pro 程序采用三镜像、自己的显示程序与基带加载器；槽位及几何必须动态。
- 用户提供的两个参考工作区和原 MU300/E5 均只读；不对它们做 reset/clean 或清缓存。
- 实机默认只读，试启动/刷写/重启另需用户对具体动作的授权。禁止 fastboot/SPD。
- NV 和 IMEI 不改。离线通过不等于硬件验收。

## 热修必须回到构建链路

每轮热修同时更新正式源码、机型配置和组包安装路径；新增服务必须核对启动顺序，
新增翻译必须同时收入 PO/LMO。驱动修改须重新生成匹配的 Image/模块，不能仅改实机。
`work/` 中的备份、临时日志和手动实验配置不作为正式输入。

当前热修入口：CP 加载和原生驱动在 `devices/u30pro/native/`，本机硬件服务和屏幕
适配在 `devices/u30pro/overlay/`，AT/短信/IPv6 与看板修改在公共源目录。
`tools/u30pro-runtime.py` 编译辅助程序；`tools/u30pro-package.py sources/finish`
复制上述文件、模块、翻译并启用服务。发布前执行 `tools/test-u30pro-root.py`，
它会比对关键热修源文件和构建根内容，不能仅凭旧 root-ready 状态认定已收录。

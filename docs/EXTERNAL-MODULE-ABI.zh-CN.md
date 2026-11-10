# 外部模块 ABI 元数据

正式 sources 组装在核验 Image／模块收据后生成 `/usr/share/mu300/kernel-abi.json`，
两款 Pro 产品共用其实际平台内核的结果。它仅包含格式版本、kernel release、
运行镜像 Build ID 和外部模块接口摘要，不包含任何私有插件或 DSP 启动逻辑。

`tools/kernel-abi.py` 计算配置、Module.symvers、公共和 ARM64 内核头文件、
生成布局头文件的确定性摘要；排除仅描述构建时间的 compile.h、utsversion.h。
同接口下的实现修改可以改变 Build ID，而不改变 ABI 摘要。外部模块消费者必须
同时核对本文件的 Build ID 与实际运行内核，以免在 OTA 待重启期间误认 ABI。
接口摘要相同才能复用模块；摘要缺失／不同不能作为强制加载的理由。

该 JSON 属于普通 rootfs 更新输入，差异更新随实际内核／系统版本更新。
`tools/test-u30pro-root.py` 比对当前登记源码／对象生成的结果，拒绝遗漏或陈旧值。
生产构建继续使用既有 `tools/build-release.py` 和共享源码／对象缓存。

# U30 Pro 可选高刷新与视频转换修复

来源：[33333s/U30pro-openwrt 791ca4e](https://github.com/33333s/U30pro-openwrt/commit/791ca4e20c45b5c5d4e66f18be1b10d580cd74d2)。

## 界面与兼容性

在本仓库已有的“屏幕壁纸”页面增加“高刷新”开关，沿用看板主题和中、英、土耳其语。
默认关闭，保存到 `u30pro_native_control.display.fast_panel`，通过现有 panel reload 应用。
旧版调用不带此字段时保留设置。该页面与屏幕服务仅在 U30 Pro 启用，F50 Pro 不启动屏幕。

启用后翻页、拖动及高于 26 fps 的动态壁纸使用 96 MHz SPI、4 ms TE 启动窗口；
操作停止约一秒回到原厂 48 MHz，息屏、关闭选项或程序正常退出立即恢复。
96 MHz 超过原厂屏幕参数，界面说明出现花点、错位、颜色异常时应关闭。
上游在其设备上测得最高约 53 fps；这不是本次本机实测结果。

壁纸网页提供 50 fps 转换，面板和上传校验接受 1–60 fps，继续兼容旧 JPEG 帧与
U3LW v2 无损 tile 格式。没有改变基带、安装布局、壁纸路径和插件接口；RPC 仅增加可选字段。

## 异步传输

移植驱动双缓冲异步 SPI 及用户态提前转换帧。SPI 未完成时不得复用消息、缓冲或
销毁驱动对象；超时告警后仍等待控制器归还所有权，记录传输错误。初始化首帧完成
后才点亮背光，保留此前开机无黑屏的交接。休眠丢弃尚未提交的预备帧。

## 视频错误

LuCI 在自己的词法作用域内 eval 页面模块，那里 `Response` 是 XHR 包装类，构造
时会调用 `getAllResponseHeaders()`。视频压缩却给它传入 ReadableStream，因此报错。
改用浏览器 `window.Response` 接收 CompressionStream 输出。图片上传不经过此步骤。
回归在页面模块中注入同名 XHR 构造器，测试真实 Chromium 压缩、视频转换与上传流程。

离线测试与编译记录在 `out/build-logs/`。没有在未授权的设备上刷写、重启或开启高刷；
是否有花屏、撕裂和实际帧率仍须单独实机验证。

本轮已完成：原生时钟策略、滑动、电源事件、充电开关、壁纸场景／持久化／格式回归，
Chromium 下 24 组主题／语言／尺寸及真实 50 fps 视频转换上传流程，无损压缩独立解码，
6.12.94 Image 与配套模块编译、原生屏幕程序编译、sources/finish 收录及准备根 22 项检查。
对应回执为 `20261105-160350-high-refresh-native-regression-94894`、
`20261105-161121-high-refresh-browser-kernel-95898`、
`20261105-162127-high-refresh-prepared-root-99728`。

# U30 Pro 壁纸缩放修复

来源：[33333s/U30pro-openwrt d88a20295c03af93fa198e64cb827cf8ed78e0e0](https://github.com/33333s/U30pro-openwrt/commit/d88a20295c03af93fa198e64cb827cf8ed78e0e0)。
只移植该提交 `ui/native-control/overlay/www/luci-static/resources/view/system/u30pro-wallpaper.js`
的 `shrink`、`cover`、`screenSize` 改动，保留上游实现及署名历史来源。
本地位置增加前缀 `devices/u30pro/native/`，来源摘要登记在 `adaptations.json`。

该提交还修改 USB、内核、SIM、软件源和电池统计；这些不属于本次壁纸修复，未一起导入。
本地已有的公共硬件控制、主题、多语言、临时提示、存储路径和上传协议保持现有实现。

图片和视频帧先居中裁成正方形，再逐次缩小一半，最后生成 480px 网页副本和
240px 实屏副本。中间画布复用于视频帧，并在每次绘制前清空，避免透明内容残留。
JPEG 及 U3LW 动态壁纸版本、尺寸和打包格式不变，无需修改内核或屏幕播放程序。
已生成的旧壁纸文件无法恢复丢失的细节，更新网页后需重新选择原图／视频转换并应用。

离线浏览器检查：
- `tests/u30pro_wallpaper_scale_browser.py`：真实 Chromium Canvas，4K 横竖图裁剪、
  缩放步骤、透明帧清理、画布复用、小图放大、240px JPEG 和真实 Video 元素帧。
- `tests/u30pro_wallpaper_browser.py`：官方/Aurora 主题、明暗色、手机/桌面、
  中英土语言及保存、取消、删除、转换、上传失败重试，网络接口均为隔离模拟。

这些不是实屏验收；本轮未部署设备、未覆盖已有发布包。

# Pro：切换频段后的自动信道列表

依据 MU300 上游 [PR #432](https://github.com/dikeckaan/mu300-linux/pull/432)。
仓库继承的 Wi-Fi 初始化会为 5 GHz 保存非 DFS 信道列表，LuCI 切换到
2.4 GHz／自动信道后列表可能保留。旧公共生成器只处理 DFS，没有过滤该
列表，因而存在相同的 ACS 无可用信道缺口；这不是 AIC 的天线或 SDIO 速率问题。

在所选频段的实际 wiphy 频率上检查单个信道和范围端点。保留合法项；全部
无效时移除生成配置中的 chanlist，让该频段 ACS 正常运行。反向切换也覆盖，
不覆写 UCI 用户设置、不改变频宽、AX／加密策略和既有 DFS 回落规则。
拒绝畸形、多端点和倒序范围。

适配同时用于 U30 Pro 和 F50 Pro：

- 通用 rootfs 构建在原 DFS 补丁后应用独立的 wifi-scripts-chanlist-band.patch。
- Pro 正式 sources/finish 路径接入 tools/stage-wifi-patches.py。保留原 DFS
  补丁内容及摘要不变；旧构建根先核验原来源与结果，再叠加新补丁并记录真实
  的合成结果，重复运行仍可校验。未知文件变化或补丁来源变化仍拒绝，不靠
  覆写指纹绕过旧根校验，也不复制或重建整份 rootfs。
- test-u30pro-root.py 对最终 hostapd 文件及两份来源／合成结果摘要做只读检查。

离线证据：OpenWrt 25.12.5 feed 的真实 wifi-scripts、假 wiphy 配置生成及
原有 AX／频宽切换测试通过，共 21 项；另覆盖 stock／SAE 两种生成器布局、
旧缓存迁移、重复运行、fresh root、输出／来源篡改拒绝。没有访问或修改实机，
没有重新编译内核或生成发布包，不将配置生成测试称为硬件热点验收。

主要日志：out/build-logs/20261109-050215-wifi-chanlist-regression-96761/command.log。

## 屏蔽不支持的 160 MHz 选项

U30 Pro／F50 Pro 共用 LuCI 频率控件通过 limit-wifi-widths 隐藏 VHT160／
HE160／EHT160 及 80+80，保留 20／40／80；不改变 N／AC／AX 及用户配置。
构建、独立 Pro finish、插件安装、uci-defaults 和现有 UI 服务启动均接入，
无需增加守护进程或轮询。旧宽度用隐藏、禁用占位保留，保存时提示选择有效
宽度，不自动清空或降档。最终根检查要求该控件策略已实际应用。
4 项真实控件／幂等／异常不写入／构建入口离线回归通过，日志
out/build-logs/20261109-051415-wifi-width-choices-4186/command.log。

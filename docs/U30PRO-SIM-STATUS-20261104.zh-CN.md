# U30 Pro 未插卡状态、查看卡槽布局与 USB 速率

## 已确认的缺口

- 屏幕 feeder 原来只传入 connected/disconnected，原生页面把普通断开统一显示
  为“拨号中”，没有接入公共 SIM 缓存的 absent／locked 等状态。
- 公共 AT owner 只在已知 SIM 上电后接受 CPIN 的缺卡回读，这条约束必须保留。
  但原先 RF-off 会同时删除已确认的缺卡快照，网页也强制要求上电标记，导致
  真实缺卡最终被显示成“无线电已关”。
- 冷启动的 CME 10 也可能表示 SIM 未上电。U30 Pro 原来没有复用 U30 Air 已有的
  有界上电确认步骤；不能把任何失败、空 ICCID 或 CFUN=0 直接当作缺卡。

## 源码与构建接入

`mu300-dual-radio` 只对 U30 Air／U30 Pro 冷启动的 CME 10 歧义复用原有 SFUN=2
步骤，再读取 CPIN；该步骤不重复执行。普通卡启动顺序不变，无新增固定延时；
F50／V50 不进入此分支，用户保存的 RF 禁用选择仍约束后续 SFUN=4。

被动缓存只保留“已上电并确认缺卡”的快照，后续关闭 RF 不抹掉该证据。
真实卡槽变化提示会使快照失效，再交给原来的恢复 owner 核验；更换 AT 描述符
owner／基带重启同样清空旧状态。超时、SIM busy、无上下文回复不能制造 absent。
shell 与 ucode 缓存保持一致，网页只读公共状态，不新增 AT 读取端。

屏幕 feeder 按所选逻辑卡区分缺卡、SIM 锁定、识别中、RF 关闭、数据关闭及基带
不可用，只有具备可拨号条件时才显示拨号中。缺卡清除旧 IP、运营商和信号。
原生文案在 `tools/ui/pages.h`，摘要已登记 `adaptations.json`；
`tools/u30pro-runtime.py` 重编对应面板，正式 root 仍由公共 sources 路径收入。

主页查看卡槽改为 hero 卡片内的 SIM 1／SIM 2 小按钮：桌面跟在“已运行”右侧，
600 像素及以下放在 hero 右上角；其他页面恢复原来的整行折叠卡片。不拖动，
不使用全局悬浮或主题页头坐标。展开说明、选择和中英土翻译保留；只改查看
对象，不调用上网卡／射频切换。主页弹层支持 Esc、点击外部关闭，离开页面
释放监听；没有新增轮询。

设备管理 USB 角色新增 USB 链路速率。只读 sysfs，在现有状态读取／刷新时
计算，无新增服务或定时器。设备模式读取选定 UDC 的 `current_speed` 和状态，
不使用 `maximum_speed`；断开后不显示旧速率。主机模式先定位本 C 口控制器，
再读取它的第一跳外设 `speed`，排除其他控制器、根 Hub 能力、接口和下游设备。
USB2／USB3 双总线扩展坞可显示两个实际链路；无法分辨的 SuperSpeedPlus
只显示其名称，不猜测 10／20 Gbit/s。速率是协商值，不是实时吞吐或充电功率。
中英土文案和正式复制／目标根校验均已接入。

语义依据 Linux 的 [UDC ABI](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/ABI/stable/sysfs-class-udc)
与 [USB device ABI](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/ABI/stable/sysfs-bus-usb)。

## 验证及本次实机部署

- 61 项回归通过：真实 ARM64 ucode、三种 shell、模拟空卡／单卡／双卡、禁用 RF、
  busy、卡槽事件、网页快照和真实 C 屏幕文案；其中屏幕载荷覆盖 18 种组合。
- 60 组真实浏览器布局通过：Aurora／官方主题、明暗、中英土、320–1920 像素。
  验证 hero 中的位置、手机右上角、主题页头独立、其他页面原样、弹层边界、
  随卡片滚动、取消、重复挂载／清理及只读选卡。
  原有逻辑卡 RPC、V50 四种和 U30 Pro 七种硬件布局回归也通过。
- 用户授权后热部署六个状态／面板文件和查看选择器；原件备份保留在忽略目录
  `work/u30pro-no-sim-hotfix/` 与 `work/u30pro-floating-sim-hotfix/`，不作为构建输入。
- 实机 Linux `6.12.94-u30pro-p1`：SIM1 原状态 unknown、CFUN=0，SIM2 ready。
  部署时仅重载 ucode policy、rpcd 和屏幕，C AT transport 的 PID 未变，未重启
  整机或基带；网络与 RF 持久配置摘要不变，没有写分区、NV 或 IMEI。
- 本次旧启动缓存需要一次存在性核验：持有原有控制／RF 互斥，临时只给 SIM1
  上电，SFUN=2 后 CFUN 仍为 0、CPIN 为 CME 10，随后 SFUN=5 恢复 RF 关闭。
  这次有界验收没有写入持久配置，也没有加入产品的周期动作。
- 回读确认网页 SIM1=absent、SIM2=ready；屏幕收到 waiting-sim、connected=false、
  空 IP，feed 正常；实际屏幕文字仍由用户观察确认。此前页头悬浮方案已按用户
  要求替换为 hero 内布局，其他页面恢复原样。

本轮主页和 USB 变更已同步到 MU300 与 E5 公共插件，各自保留原有 AT、数据卡
跟随、USB 角色与外部供电适配器。三边 USB helper 摘要相同；MU300、E5 的
8 个真实目标 ucode/sysfs 用例和各 60 组浏览器布局通过，既有角色、数据卡、
IMEI／漫游及页面回归通过。U30 Pro 本次仅更新五个网页／USB 文件，无服务或
整机重启。实际网页桌面和手机尺寸确认 hero 与原样其他页，USB 回读 480 Mbit/s。
主机／扩展坞速率本轮仍仅做合成 sysfs 检查，不冒称实物验收。
备份为 `work/u30pro-hero-sim-usb-hotfix/`。

打包依照用户要求保持停止。此前中止的组包现场保留，新修改尚未进入正式 ZIP。
恢复发布时先按规范检查并 clean-staging，再 sources／finish／package；安装器
源码未变，可校验并复用已发布的 cd971d0 三平台安装器，面板使用本轮的新回执。

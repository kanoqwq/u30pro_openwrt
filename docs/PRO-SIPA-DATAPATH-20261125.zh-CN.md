# Pro SIPA 数据通路修复（2026-11-25）

范围仅为用户确认的五项：发送失败后的 skb 所有权、重试包头回退、普通
USB NCM 旁路误触发、TX 完成回收、RX DMA 同步。U30 Pro 和 F50 Pro 共用
这些 UMS9632 驱动；不修改 AIC、网页、AT owner、射频、选频、充电或基带镜像。

参考提交为 33333s/U30pro-openwrt
[`2d4c266`](https://github.com/33333s/U30pro-openwrt/commit/2d4c266deebd5e34e3c7ee772ec8c40bc2ab1b29)。
保留 GPL 源文件及原版权。发送和 USB 隔离借鉴其修复；完成回收与 RX DMA
按本仓库已有流控、缓冲区所有权和 DMA 映射方式重新核对，不整体移植参考固件。

## 修复

1. `sipa_eth_start_xmit()` 在线性化或扩展头部失败后，释放 skb 并返回
   `NETDEV_TX_OK`。实际发送仅在 `-EINPROGRESS/-EAGAIN` 时将未消费 skb
   交还队列；其他失败记为丢包并释放一次，避免永久错误反复重排。
2. raw-IP 包通过 `skb_cow_head()` 保证头部可写且空间足够，用局部 `pushed`
   记录本次是否添加了 14 字节头。失败时只撤回本次添加的头，不再根据已经
   改变的 headroom 判断。原实现对初始 headroom 14～27 字节的回退会失败。
3. `usb0` 的旁路开关仅在 `IS_ENABLED(CONFIG_UNISOC_SIPA_USB)` 时生效，
   并使用完整名称比较。当前原生 NCM 配置没有启用 SIPA USB，不再误改 IPA
   模式及电源引用；保留 legacy SIPA USB 启用时的 UP/DOWN 配对行为。
4. TX 完成描述符未匹配时，在 `send_lock` 外限次重新同步 DMA，再继续处理
   批次后面的正常项。读指针只前进实际读取的数量，额度只归还确实匹配并
   取走所有权的 skb。未知／重复描述符只丢弃该完成记录并限速报错，不盲目
   释放其他 skb，也不虚构额度。实际仍在途的 skb 保留在发送链表；如果硬件
   永久丢失其完成记录，本改动不能凭空重建该记录，不自动重置射频掩盖问题。
   匹配项先在锁内脱离链表并处理映射，随后使用局部 skb 在锁外执行回传或
   释放，避免回调重入发送锁。既有 RM/FIFO 流控串行化保持不变。
5. 池化接收页同时承载设备写入的数据和 CPU 修改的 `skb_shared_info`，统一
   使用 `DMA_BIDIRECTIONAL` 映射。初始化和复用前先交还 CPU，完成元数据
   初始化并成功加入软件所有权队列后，再以相同方向交给设备。保留独立 skb
   的 `DMA_FROM_DEVICE` 映射／解除方式。
   收包先恢复 CPU 所有权，再执行可能访问元数据的长度检查或异常释放。
   初始化分配失败后按实际缓冲区偏移生成 DMA 地址，软件环入队失败不发布
   描述符；避免失败后继续使用上一缓冲区地址。没有新增定时器或轮询服务。

DMA 同步规则参考 [Linux DMA 指南](https://docs.kernel.org/core-api/dma-api-howto.html)，
发送所有权参考 [网络驱动约定](https://docs.kernel.org/networking/driver.html)。

## 离线验证

| 轮次 | 检查 | 结果 |
| --- | --- | --- |
| 1 | HEAD 旧代码运行新增 TX／完成回收／USB 场景 | 17 项中 14 项按预期失败，确认可捕获旧缺陷 |
| 2 | 修正后的数据通路、已有流控和缓冲区首轮 ASan/UBSan | 36 项通过 |
| 3 | 补齐初始化与真实收包／异常释放后的 RX 生命周期矩阵 | 8 项通过，覆盖四种生产／回收路径及故障注入 |
| 4 | 最终 SIPA、SDIO 时钟／发送／恢复、USB 角色、移植边界、现有 AIC 通知序列化回归 | 78 项全部通过 |
| 5 | 登记的 Linux 6.12.94 源码／对象缓存完整 Image 和 modules 增量构建 | 通过 |
| 6 | U30 Pro／F50 Pro 两个组包入口调用既有 verified_kernel，并比对正式源／准备树／收据及 modules.order 实际选择的 253 个模块 | 通过，详见本机产物核对记录 |

新增测试直接提取并编译生产函数，不另写一份发送或回收算法。覆盖
0～63 字节头部空间、已有以太头／raw-IP、克隆标记、每包连续 16 次 BUSY、
线性化／COW／永久发送失败、重复及未知完成、延迟可见描述符、部分批次、
锁外回传、空发送队列和 2000 轮双线程争抢同一完成记录。既有流控测试另覆盖
10000 轮并发资源切换。RX fixture 追踪 CPU／设备所有权、页引用、映射和
解除次数，以及发布的每个 DMA 地址是否对应实际 skb。

本机任务日志位于 `out/build-logs/`：

- `20261125-082540-pro-sipa-datapath-first-65858`
- `20261125-082713-pro-sipa-rx-lifecycle-66008`
- `20261125-083120-pro-sipa-baseline-73568`
- `20261125-083209-pro-sipa-final-matrix-77623`
- `20261125-083016-pro-sipa-kernel-69806`
- `20261125-083313-pro-sipa-artifact-verification-84152`
- `20261125-083500-pro-sipa-module-order-verification-84193`

初次构建先因未显式指定本机既有安装器目录被输入检查拦住，补充原有路径后，
又因历史对象为 root 所有而无法覆盖。随后按构建规范以 root 使用原工作区
完成编译；未改权限、未清缓存或替换内核树，也未重编安装器。

## 交付边界

四个修改均在共用原生内核 overlay，来源和内容摘要登记于
`devices/u30pro/adaptations.json`。新增测试已接入 `tools/test-u30pro-native.sh`。
既有 sources/finish、完整包／普通更新／差分 OTA 路径继续通过 Image 和匹配
模块交付；没有新增设备端文件、依赖或需要迁移的用户配置。

本轮已编译并核验内核／模块，没有生成新 ZIP，也没有部署或重启设备。
离线 CPU/DMA 所有权模型不能代替真实 DMA 缓存、吞吐、功耗和休眠唤醒验收。

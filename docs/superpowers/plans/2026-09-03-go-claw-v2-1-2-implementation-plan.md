# GO CLAW v2.1.2 实施计划

日期：2026-09-03；定稿：2026-09-04
状态：v2.1.2 正式签名构建与 F 盘真实 A/B 升级验收已完成并发布 GitHub Release（2026-09-05）；生产在线更新镜像尚未切换，U 盘故障诱发自动回滚仍作为开放全量更新前的独立门禁
设计：[v2.1.2 详细设计](../specs/2026-09-03-go-claw-v2-1-2-design.md)
合同：[v2.1.2 目标接口、持久化与兼容边界](../../contracts/v2.1.2/README.zh-CN.md)

阅读约定：下文“新增/修改/实现/退出条件”是计划任务；以本节进度表区分已完成部分，不表示整阶段通过。
当前可核查源码基线为 `cd365aa`（2026-09-04）；实施前重新确认 HEAD。本文已存在的源路径已核对，
大括号和通配符表示计划新增的文件组，不是可直接执行的命令。

### 2026-09-04 代码实施进度

| 批次 | 当前已落地 | 尚未完成 |
| --- | --- | --- |
| Phase 0 | 带更新器候选在 NTFS、F exFAT 均完成 staging 完整包下载/验签、安装及自动重启；API/UI/标记均 2.1.1，无安装锁或错误；空聊天索引/身份摘要未变，F 额度前后同值 | 历史包媒体/模型档位 readiness 不通过；基准聊天为空，非空消息/归档/附件保留待 Bridge fixture；原始无更新器构建需手动 Bridge；生产充值复核、产品版本统一提升 |
| D1 / Phase 4 | 技能 Banner 精确文案、右端按钮、深浅色/窄屏样式；沿用 market query 和原 HeaderActions；返回刷新；空/有技能/加载中与键盘自动测试 | 浏览器真实 320px/深浅色视觉验收 |
| D1 / Phase 6 | 充值整数输入与已移除灰色说明回归通过，未改金融逻辑 | 原四方对账与跨版本余额保留用例 |
| D2 / Task 1.1–1.3 | schema/fixture、精确归属、确定性 ZIP、组件/manifest/index/catalog 签名链及 CI/draft Release 接线完成；实际 1.43GB Full staging 两次分包的 8 个输出逐一 SHA-256 相同；缺媒体种子拒绝构包 | 同 commit 正式签名资产验证 |
| D3 / Task 2.1–2.3 | PortableState/槽位、独立 binary、staging/bootstrap/recovery、Windows 进程绑定、故障注入与真 TLS；Bridge headless/正常 UI 均由 NSIS 3.11 编译，headless 可执行合同通过 | 真实签名大包及 Windows 产品子进程/U 盘验收 |
| D3 / Task 2.4 | HTTP v2 状态/动作和 SSE 接独立引擎；空 body 兼容、目标冻结、重复请求合并、恢复快照、同源校验；签名历史目录已接有界 release catalog | 真实安装联测 |
| Task 2.5 / 身份保留 | 损坏旧 ID 保留而不再生成新身份；固定路径旧盘证据阻止重新开户；损坏 billing profile 保留；CLIENT_VERSION 复用唯一版本源；时序/维护检查同步；provision/billing 20 项回归通过 | 真实旧版聊天/余额前后对比仍待实机 |
| D4 | 双橙点/单进度条统一更新 UI；交付产物收集、持久化、鉴权媒体票据、打开/定位、历史恢复和窗口化媒体轨道；附件 AT-03 单次 URL 语义修复 | 浏览器真实缩放/触屏与 provider 多模态验收 |
| D5 | 产品版本 2.1.2；Rust/Python/前端核心回归与 Bridge 可执行合同完成；正式签名 Main Build 成功；F 盘从 2.0.1 完成真实 A/B 升级、自动重启、数据摘要/额度保留；五员工、三档模型、充值接口、真实图片/视频生成、交付产物和中文附件上传通过 | 生产在线更新镜像原子切换；在独立 U 盘测试目录诱发候选健康失败并核对自动回滚，不阻塞已发布 GitHub Release，但阻塞生产全量更新 |

本轮验证命令/工具边界见 [组件合同说明](../../contracts/update-v2/README.zh-CN.md)；
自动测试不替代真实 USB 更新或前端布局验收。新增身份保护已同步当前运行文档；A/B 代码已接线但
生产入口未启用，发布状态未改变。Rust 当前 63 项库、22 项 CLI、38 项合同/故障注入通过；Python
全量曾得到 5837 项通过、62 项跳过、12 项失败；安全临时目录/UTF-8 复跑后仅余 1 项旧 Windows
非管理员沙箱环境假设失败，不能写成全绿。本轮关键后端定向回归 265 项通过。充值隔离回归 63 项
通过、3 项因无 PostgreSQL 测试 DSN 跳过。前端全量 1243 项通过，跨平台换行断言修复后相关 19 项
复核通过；Windows 前端全量 165 文件/1244 项、TypeScript 和 production build 通过。构建仍报告
原 vendor 循环分包与大 chunk 警告，未扩大本批范围修改全站打包策略。

启动取证、同版本构建差异和哈希见 [本次干净样本准备](../../incidents/2026-09-04-v201-clean-sample-preflight.zh.md)。
用户已允许 F 盘创建独立测试目录；`F:\GC201-TRY-0904` 已复制并核对双程序哈希，未改动 F 根目录产品/聊天/余额，
已通过旧后端下载及独立验签并完成 U 盘安装/自动重启（09-05 00:01，详见 incident）。事务成功不等于
完整产品可用，旧媒体兼容失败已补真实种子迁移回归。新引擎已补 body 断流的完整 range 回退重试，
以及 journal 已冻结目标字段，防止同交易被刷新/恢复偷偷改成其他版本或槽位；
loopback 真 TLS 已覆盖 HTTPS/ETag/Range/无 Range/断流/超时，公共 CDN 真实大包与产品协调验收仍未完成。

2026-09-05 接线补充：新增健康回执 20 项、portable 6 项、bootstrap 4 项（含 11 个中断点）通过；
维护 8 项通过，工具检查 9 顺序/6 图；Debug/Release binaries 编译检查通过。健康失败不清理用户数据，
固定根文件备份全部验证后恢复，恢复不完整保留锁。此离线 harness 绕过签名只限内部合成测试，
公共安装入口另有未签名拒绝用例。未真实执行 v2 安装、不代替 Full Build/USB/聊天读取验收。
候选保持旧 active 指针直至健康并停止后提交，详见运行时序 §6A；这不是普通启动锁绕过。

同日后续：loopback 真实 TLS 7 项通过，覆盖续传、取消、断流、200 fallback、ETag/跳转和缓存隔离；
大包/60s 无进展/全部重试耗尽已纳入 Rust HTTPS 合同；不把小型签名向量当实际下载性能验收。
Python v2 DTO、journal reader、双快照 StatusStore 已连接 HTTP manager/SSE。复用失败追加组件下载、
签名历史目录、Bridge、统一 UI 与交付物已实现；实际 Full staging 体积/确定性分包和 F 隔离复制已完成。
隔离 RC 已于 09-05 真实启动：后端 2.1.2/health ok、5 员工加载、两个媒体插件 loaded/enabled，
技能 Banner 与充值入口页面可见。公共包不含客户凭据，因此额度 404、模型档位 503 和充值初始化中是
未绑定态结果。经用户授权临时复制最小绑定文件后，额度条、模型三档、充值配置/余额和账本 UI 均恢复；
未创建订单或调用付费 provider，不能替代正式签名 A/B、非空聊天回读或真实 provider 调用。

2026-09-05 Main Build 证据：NSIS 622564466 字节，SHA-256
`261eda38833fa41e9bfb018a7f71beff1ea71de06b24b4994422d8b7f44cabcb`；portable ZIP 634905818
字节，SHA-256 `08b945378715f07f64abc482606554c22ad4df988793189c5894e5310a19f610`。
归档含 13264 条目，解压 1432526282 字节；本地未提供 Tauri 发布私钥/正式 sidecar 签名链，只可作为 RC。
EXE 的 Authenticode `NotSigned` 与 updater 签名相互独立；沿用此前 Windows 交付策略时 Authenticode
不是 v2.1.2 发布门禁，后续可为可信发布者/SmartScreen 体验单独接入。
`F:\GO-CLAW-v2.1.2-RC-0905` 文件数/字节数及 8 个关键文件哈希与 D staging 一致，F 根产品/数据未改。
启动时产品壳和后端均从该路径运行；生产 `release-index-v2`/`release-catalog-v2` 及签名当前均为 404，
所以检查更新在 discover 阶段返回 `DOWNLOAD_REJECTED`，未改生产更新源。
已绑定 RC 内真实调用生图一次与文生视频三次：前者被上游周配额 429 拒绝，后者被上游分组负载饱和
429 拒绝；工具检测、调用和视频最低规格参数传递已通过，但未生成文件，待 provider 恢复后补产物验收。

2026-09-05 正式签名验收补充：Main Build run
[`33947367539`](https://github.com/GresonKwan/GO-Claw-2.0/actions/runs/33947367539)
在提交 `f50bcfcee9a6efd23d3095a8b641f5c0c913041f` 成功。CI Full ZIP 内部 SHA-256 为
`d804f3136823f0c3c1cc0a123c58b573526db994f3c9c491686709585ecb6f94`，manifest 13,981
项逐项校验无失败。`F:\GC201-V212-SIGNED-0905-01` 从 2.0.1 经隔离 staging 完成交易
`3a69aec7-71ee-4693-90f6-6770cb5e2000`，最终 `COMMITTED/100%`、活动槽 A、无 failure；
下载 533,652,013 bytes，完整版本 620,465,208 bytes，证明组件差分而非全包覆盖。升级前后的
`instance.id`、credentials、master key、config、token usage 及全部既有 `chats.json/history.db`
摘要一致；额度从升级前到首次启动后仍为 `2.3/0.8745/38%`，之后只因本次付费媒体验收正常消耗。
五员工均 idle，每个员工返回 economy/balanced/performance 三档；图片/视频插件均
`loaded=true, enabled=true`。真实生成 2048×2048 PNG（1,372,291 bytes）和 3 秒 720P
MP4（391,708 bytes），两者均进入 `goClawDeliverables`；再以中文文件名上传 PNG/MP4 均返回
HTTP 200，无 UTF-8 错误。GitHub Release `v2.1.2` 已提升为非 draft、非 prerelease 的 latest；
生产 `https://goclaw.host:8443/updates/latest.json` 仍保持 2.1.1，未随 Release 自动切换。

## 1. 分支、合并与发布边界

1. 从 `codex/compute-recharge` 创建 `codex/v2.1.2`，保留已验证充值提交；
2. 只写 `GresonKwan/GO-Claw-2.0`；任何 GitHub 写操作前显式核对 repository；
3. 不合并 main、不创建 v2.1.2 tag/Release、不切换生产更新镜像，直到完整门禁全部通过；
4. 当前 v2.0.1 → v2.1.1 事故仍按未关闭处理。A/B 架构不能替代旧现场取证；Bridge 必须从干净
   v2.0.1 和 v2.1.1 样本分别验收；
5. 更新时序变化必须在同一变更更新规范文档、维护合同、测试和变更台账。

## 2. Phase 0：事实与版本冻结

### Task 0.1 合并充值基线

- 确认 `codex/compute-recharge` 与目标分支无漂移；
- 只读对账后把带日期、脱敏订单号、四方一致结果的 ￥1 证据写入事实基线；当前基线“默认关闭”与
  历史支付成功报告不一致，在消除差异前禁止发布，不为文档核查再次收费；
- 将金额合同从“最多两位小数”统一修订为“客户端整数元输入”，服务端继续使用整数分；
- 产品版本的唯一源是 `src/qwenpaw/__version__.py`，升到 `2.1.2`；继续用
  `scripts/pack-tauri/sync_tauri_version.mjs` 生成被忽略的 `tauri.version.conf.json`。不手工给受跟踪的
  `tauri.conf.json` 加 version，不把当前 npm `0.0.0`、Cargo `0.1.0` 当产品版本强行同步。
  用 `tests/unit/scripts/test_sync_tauri_version.py` 与最终 EXE/API/manifest 一致性检查验收，不创建 tag。

### Task 0.2 更新事故取证

- 严格按 `GO-CLAW-v2.1.1-Windows在线更新调试交接.zh.md` §7 从干净样本复现；
- 记录 NTFS 与 U 盘的首个失败 stage、进程路径、锁、版本标记和哈希；
- 不修改生产 manifest；
- 将结果作为 Bridge 的兼容验收输入。

2026-09-04 实机补充：不能仅凭 `2.0.1` 版本字符串判断旧端具有 GO CLAW 在线更新器。
原始基准的浏览器入口只显示上游 pip/uv 更新说明且 `/api/updates/status=404`，与本机另一份
同版本带更新器基准不同。保持两个来源的哈希和验收记录分离；禁止补丁注入旧包后宣称原包
可在线更新。无更新器来源需要用户手动启动同一已签名 Bridge 的一次性入口，不允许覆盖数据的
Full ZIP 或上游 pip 升级作为替代；具体手动入口及来源校验纳入 Task 2.3，不增加后台扫描。

退出条件：事实文档与代码同日一致，目标版本和兼容来源明确。

### Task 0.3 附件核查与证据冻结（不阻塞无关功能）

- 已完成有限核查：[PNG 上传/预览/对话流证据](../../incidents/2026-09-03-chat-attachments-utf8-investigation.zh.md)，
  后续已在 AT-03 复现特殊字符路径的 URL 二次解释并完成单点修复；真实视频 provider 理解、UI 选取、
  受控干净样本尚未覆盖；
- 不把媒体 bytes 转 UTF-8；只保留经失败用例证明的路径段编码/单次解码和明确媒体 magic 错误；
- 若发现可重复失败，记录 first stage、媒体 magic/大小/摘要、agent、模型能力、脱敏状态码及调用栈，
  只修改该 stage，禁止用重新编码客户原始媒体“兜底”。

## 3. Phase 1：冻结更新合同与确定性构建

### Task 1.1 新增合同文件

新增：

- `docs/contracts/update-v2/release-index.schema.json`
- `docs/contracts/update-v2/windows-release.schema.json`
- `docs/contracts/update-v2/transaction.schema.json`
- `docs/contracts/update-v2/README.zh-CN.md`
- `docs/contracts/v2.1.2/update-status.schema.json`
- `docs/contracts/v2.1.2/deliverables.schema.json`
- `tests/unit/scripts/test_v212_contracts.py`

机器合同由本次已建立的 `docs/contracts/v2.1.2/README.zh-CN.md` 落地；固定 schema version、组件名、
路径规则、签名原始字节、HTTP 状态映射、错误码、删除清单、槽位状态和 crash recovery。为新旧
客户端分别提供合法/非法 fixture，未知字段可兼容、未知主 schema fail closed；同一字段不得双重解释。

### Task 1.2 组件归属器

新增：

- `scripts/pack-tauri/update_components.py`
- `scripts/pack-tauri/build_component_packages.py`
- `scripts/pack-tauri/build_release_index_v2.py`
- `tests/unit/scripts/test_update_components.py`
- `tests/unit/scripts/test_release_index_v2.py`

实现：

- 路径规范化和大小写冲突检查；
- 每文件唯一 component；
- 组件与整包 SHA-256；
- bytewise 稳定排序、固定 ZIP timestamp、禁止 symlink/重解析点；
- 相同输入连续构建两次 manifest 和组件摘要完全相同；
- 输出下载体积报告，记录 full vs changed component bytes。
- 组件归属使用精确清单而非相互覆盖的目录 glob；PyInstaller 重型依赖从 backend-core 中排除，插件
  种子只归 bundled-plugins；console、壳、插件当前混合位置通过 manifest mount 显式映射。
- 用户已有 legacy 树没有可信组件摘要时，只有在 download/planning 阶段后台流式计算；check 不阻塞
  扫盘；校验不能复用的组件才下载。拒绝仅凭 size/mtime 判定一致。

### Task 1.3 Release verifier

修改：

- `scripts/verify/windows_release_contract.py`
- `.github/workflows/desktop-build.yml`
- `.github/workflows/desktop-publish.yml`
- `.github/workflows/desktop-release.yml`
- `.github/workflows/desktop-promote.yml`

新增断言：

- legacy `latest.json` 与 v2 index 指向同一 commit/version；
- Bridge、release manifest、每个 component 都能用包内公钥验签；
- 组件覆盖目标程序树且互不重叠；
- 任何 mutable 路径、凭据或支付密钥都不进入组件包；
- 已发布资产不可覆盖。

退出条件：本地与 CI 可稳定生成签名 v2 合同，不写生产源。

## 4. Phase 2：独立更新引擎与 A/B 槽位

### Task 2.1 更新引擎

新增 Rust binary：

- `console/src-tauri/src/bin/go-claw-update-engine.rs`
- `console/src-tauri/src/update_engine/{manifest,planner,download,extract,slots,state,verify}.rs`
- `console/src-tauri/src/update_engine/{progress,recovery,bootstrap}.rs`
- `console/src-tauri/tests/update_engine_contract.rs`

职责：

- 拉取/读取 release manifest；
- 验证 minisign、SHA-256、HTTPS 和长度；
- 计算组件差异与所需空间；
- 支持续传到 `.part`，完成后原子 rename；
- 安全解压，拒绝绝对路径、`..`、ADS、symlink、junction 与大小写碰撞；
- 构建目标槽位并校验完整文件树；
- 写 transaction 状态；
- 停止应用、切槽、启动或回滚；
- 日志只输出 version/component/stage/hash 短前缀。
- 独占锁限定 product-root，幂等请求不产生第二个 updater；冻结目标 manifest 摘要，下载中 check 不得
  偷换版本；超时/重试/取消和退出码依合同处理。
- 不通过 `read_bytes()` 把完整包载入内存；下载、摘要、解压均有大小与磁盘预算，验签实现必须提供
  有界内存处理；不支持的签名格式失败，不自行换签名算法。
- staging 失败不碰活动槽位；安装期才创建 installing.lock。pending transaction 的断电恢复与普通
  启动严格分离。旧壳/槽位/metadata 三者完整恢复后才删除锁。
- 提供无网络的虚拟文件树/故障注入 harness，分别在日志 flush、文件 rename、切指针、健康确认、
  回滚恢复点断电；保留前一有效 journal 与校验值，不仅依赖单文件 rename 在所有 U 盘上都耐断电。

### Task 2.2 PortableState 槽位解析

修改：

- `console/src-tauri/src/portable.rs`
- `console/src-tauri/src/backend/command.rs`
- `console/src-tauri/src/backend.rs`
- `console/src-tauri/src/lib.rs`

具体修改：

- `PortableState` 新增 `program_root`、`active_slot`、`last_known_good`；
- `root/working_dir/secret_dir/backup_dir` 沿用旧盘；只把程序定位改到 `program_root`。普通启动与
  engine 恢复启动共用同一环境构造，断言 `QWENPAW_WORKING_DIR=root/data`、
  `QWENPAW_SECRET_DIR=root/secrets`、`QWENPAW_BACKUP_DIR=root/backups`，不从槽位 cwd 推导数据根；
- 在 `portable.rs` 既有测试和 `update_engine_contract.rs` 已规划测试中补路径一致性断言，含盘符/根
  位置变化，不新增目录扫描或单独的守护进程；
- 启动早期读取并严格验证 `runtime/active-slot.json`；
- backend、Python runtime、Node runtime 均从 `program_root/binaries` 解析；
- legacy 无 `runtime` 时继续按根 `binaries` 启动，保证 Bridge 前兼容；
- pending transaction 时只允许恢复流程；
- 新 slot 健康启动绑定 transaction、generation、manifest 摘要和一次性本机挑战；环境变量中的
  `GO_CLAW_UPDATE_TRANSACTION_ID` 仅作关联，不能授权绕过安装锁；普通启动入口继续阻断；
- 所有路径日志脱敏为槽位和相对程序路径。

### Task 2.3 Bridge

新增：

- `console/src-tauri/nsis/go-claw-update-bridge.nsi`
- `scripts/verify/test_portable_update_bridge.ps1`

保留现有 `go-claw-update.nsi` 作为 legacy 回退和事故对照，不直接删除。

同时修改 `console/src-tauri/src/updates.rs` 的新版本安装移交，新增 Bridge 单进度条实现（复用 engine
progress DTO）。旧 Tauri 已先停 backend，不可等待一个已退出的 HTTP 服务汇报进度；Bridge 继承
交易进度并独立显示，新客户端重启后读持久化状态。根壳替换必须等待原 exe 退出并单独可回滚。

Bridge 测试：

- v2.0.1 legacy 根；
- v2.1.1 official 根；
- v2.1.1 带 UI/插件热修复根；
- legacy backend cwd、子进程和外部句柄；
- 路径含中文/空格；
- 目标槽位校验失败；
- 切换前/后断电；
- 新版启动失败自动恢复旧 launcher 和旧程序。

### Task 2.4 后端更新状态机

重构：

- `src/qwenpaw/app/go_claw_updates.py`
- `src/qwenpaw/app/routers/updates.py`
- `tests/unit/app/test_go_claw_updates.py`

新增：

- `src/qwenpaw/app/go_claw_update_contract.py`
- `src/qwenpaw/app/go_claw_update_state.py`

具体修改：

- 去除重复常量声明；
- status 增加 `changedComponents/downloadBytes/fullBytes/activeSlot/targetSlot/transactionId`；
- 按合同额外提供 `schemaVersion/revision/enginePhase/progressPercent/installationStarted`；旧 `phase`
  使用兼容映射，不能直接把 uppercase 引擎状态发给旧 UI；
- check 只下载小 manifest，不 hash 整个活动树；
- download/install 调用独立 engine；
- 状态从 transaction 文件恢复，不依赖单进程内存；
- 增加 `GET /api/updates/events` SSE；
- 现有 status/check/download/install 路径保持兼容；
- releases 历史安装也走 A/B，不允许原地覆盖。
- `install_version(version,url,signature)` 的旧 body 仅用于匹配已验签的历史目录；HTTPS 本身不足以
  授权下载，传入 URL/signature 与目录不符必须拒绝；新版使用 target digest 和 transaction id。
- 将旧 `downloaded/total` 字段保持为网络字节，不能写进百分比或本地复制字节；SSE 重连按 revision
  发送最新快照，丢旧事件，退避合并 focus/online/check 请求。

### Task 2.5 健康确认与回滚

修改：

- `scripts/verify/desktop_verify.py`
- `scripts/verify/go_claw_maintenance_contract.py`
- `tests/unit/scripts/test_go_claw_maintenance_contract.py`
- `docs/GO-CLAW-运行时序与维护规则.zh.md`
- `docs/GO-CLAW-变更台账.zh.md`

新增本机回执 API 或启动壳内部 probe，固定检查 version、进程槽位、员工、媒体插件、媒体工具、
quota；有 billing profile 时额外记录充值 readiness，但它是 degraded 指标而非核心阻断条件。
健康检查不重新 provisioning，不因禁用某员工而改用户选择。数据迁移保证 N/N-1 可读，不允许“回滚
程序同时恢复旧聊天/账本快照”；任何不可逆数据迁移从本版本范围移除。

2026-09-04 细化：上述 N/N-1 改为**实际来源版本可读**，包括 v2.0.1 → v2.1.2 失败后回到 v2.0.1。
新增无损要求只并入原有步骤，不新设验收流水线：

- `src/qwenpaw/app/chats/session.py`、`src/qwenpaw/app/chats/repo/json_repo.py` 的旧格式 reader/迁移
  以现有逻辑为先；在 `tests/unit/app/chats/test_session.py`、`test_repo.py` 中补小型旧格式 fixture。
  保留员工、chat/session ID、正文/归档/附件引用；若必须迁移，先备份待改文件再原子写，不全量备份。
- 更新后本地路径沿用原数据根即可进入现有就绪流程；历史内容检查放在 §9.2 的测试样本，不在客户
  每次开机枚举/读取全部会话。只拒绝已确认的数据根错位或破坏性身份写入，既有异常不靠重置修复。
- quota 复用现有请求与超时，老盘原已缺身份导致不可读的情况按设计 §3.9 记录，不因此重新开户；
  不增加远端账户审计 API 或第二轮阻塞式就绪轮询。

退出条件：小型 probe、完整 NTFS 样本和 U 盘样本都证明不原地改活动槽位、失败可回旧槽位。

## 5. Phase 3：更新提示 UI

### Task 3.1 统一 context

新增：

- `console/src/contexts/UpdateContext.tsx`
- `console/src/contexts/updateAdapters/portableHttp.ts`
- `console/src/contexts/updateAdapters/tauriDesktop.ts`
- `console/src/contexts/UpdateContext.test.tsx`

修改：

- `console/src/contexts/DesktopUpdateContext.tsx`
- `console/src/App.tsx`（把现有 DesktopUpdateProvider 接入统一外层，避免双重轮询）
- `console/src/layouts/Header.tsx`（移除版本号橙点与便携模式 PyPI 判断，保留版本展示）
- `console/src/layouts/Header.customer.test.tsx`
- `console/src/layouts/Sidebar.tsx`
- `console/src/layouts/SidebarSettingsPanel.tsx`
- `console/src/layouts/UpdateSection.tsx`
- `console/src/api/modules/updates.ts`
- `console/src/layouts/index.module.less`
- `console/src/locales/zh.json`
- `console/src/locales/en.json`

具体行为：

- 设置齿轮和设置弹出面板消费同一状态；保留既有点击齿轮弹出式组件，不新增全屏更新页；
- 便携浏览器模式不再用 PyPI 版本猜测 GO CLAW 更新；
- 启动/focus/online/SSE 事件刷新；
- 版本号不显示橙点；设置齿轮和“检查更新”按钮右上角共用同一 update-available 橙点状态；
- 橙点贯穿发现更新、下载和下载完成等待安装阶段，在安装实际开始时同时消失；
- 只保留一条连续进度条：下载 0–90%、等待安装保持 90%、安装 90–100%，不增加多阶段卡片、
  进度环或复杂状态图标；
- 更新面板展示“需下载体积”而非完整包体积；
- 无弹窗打扰、无自动安装。

测试：版本号无点、齿轮与检查按钮双橙点、点击齿轮打开既有弹出组件、下载完成仍有点、安装开始
双点消失、单进度条连续、无更新不显示、SSE 断线回退、重复事件不重复下载、暗色与窄屏快照。

## 6. Phase 4：技能 Banner

新增：

- `console/src/pages/Agent/Skills/components/SkillMarketBanner.tsx`
- `console/src/pages/Agent/Skills/components/SkillMarketBanner.test.tsx`

修改：

- `console/src/pages/Agent/Skills/index.tsx`
- `console/src/pages/Agent/Skills/index.module.less`
- `console/src/pages/Agent/Skills/components/index.ts`
- `console/src/locales/zh.json`
- `console/src/locales/en.json`

断言：Banner 位于 header 与 toolbar 之间；一级标题固定为“从技能中获得专业能力”，二级标题固定为
“从11万个技能中，找到效率最优解”；桌面端“浏览技能”按钮靠最右，移动端纵向铺开；按钮进入
`?view=market`；返回后技能刷新；空技能页也显示 Banner；320px 不溢出；键盘可操作；现有
HeaderActions 入口仍存在。

## 7. Phase 5：交付产物

### Task 5.1 后端登记与持久化

新增：

- `src/qwenpaw/app/deliverables/models.py`
- `src/qwenpaw/app/deliverables/collector.py`
- `src/qwenpaw/app/deliverables/store.py`
- `src/qwenpaw/app/deliverables/security.py`
- `src/qwenpaw/app/routers/deliverables.py`
- `tests/unit/app/deliverables/*`
- `tests/unit/app/routers/test_deliverables.py`

修改：

- `src/qwenpaw/agents/tools/send_file.py`
- `src/qwenpaw/agents/tools/file_io.py`
- `plugins/tool/qwen-image/qwen_image_tool.py`（生成/编辑成功后的本地 URLSource）
- `plugins/tool/wan27/wan27_tool.py`（三种视频能力成功后的本地 URLSource）
- `plugins/tool/qwen-image/plugin.json`、`plugins/tool/wan27/plugin.json`（修改插件代码后从 1.1.1 升至
  1.1.2；当前 host 兼容上限 2.2.0 已覆盖 2.1.2，无需凭空改上限）
- `tests/unit/app/test_go_claw_bundled_plugins.py`、`tests/unit/plugins/test_go_claw_media_plugins.py`
  （已有 1.1.1 原子升级到 1.1.2；插件配置/用户禁用选择保留；旧 host 可回滚运行）
- `src/qwenpaw/app/channels/console/channel.py`
- `src/qwenpaw/app/routers/__init__.py`
- `src/qwenpaw/app/chats/manager.py`（delete_chats 清理映射；archive 不删除产物）
- `src/qwenpaw/app/chats/api.py`（历史批量读取授权与删除联动）
- `src/qwenpaw/app/chats/models.py`（历史响应新增可选元数据）
- `src/qwenpaw/app/chats/utils.py`（保留 response/turn 关联，不从“最后一条”猜轮次）

实现：

- ContextVar 绑定 chat/turn/workspace；
- 在 `ConsoleChannel.stream_one` 的 `_process` 前 set、finally reset，确保并发员工/异常不串轮次；
  工具需要线程执行时显式传播 context，不用进程全局“当前 chat”。新增 collector API 延迟导入且无上下文
  时 no-op，插件仍可在旧 host 单独使用，原 ToolChunk 不变；
- 强产物与候选产物分层；
- `go_claw_bundled_plugins.py` 只有种子 version 更高才升级已安装插件，不能只改源插件代码而不升
  plugin.json；新登记 helper 无 host 支持时安全 no-op，但不能吞掉工具本身异常；
- completed response 前 finalize；
- turn manifest 原子持久化并与 response id 关联；
- 历史 session 加载可重建展示 DTO；
- 历史批量端点按响应 ID 查询，独立清单是持久化权威；metadata 只是快照。旧会话无清单返回空列表，
  不扫描磁盘猜历史产物，不把用户附件自动当交付物；清单写失败不能把已完成回答变为失败；
- 删除 chat 时清理映射；
- open/reveal 只接受 artifact id 和固定 action。
- thumbnail/content 只接受 artifact id；图片缩略图有尺寸/像素/耗时上限和缓存淘汰，图片原图流式返回，
  视频实现单 Range 与正确的 `206/416` 合同；所有内容响应强制 inline、nosniff 和受控 MIME。

### Task 5.2 前端

新增：

- `console/src/api/modules/deliverables.ts`
- `console/src/pages/Chat/components/DeliverablesPanel/index.tsx`
- `console/src/pages/Chat/components/DeliverablesPanel/index.module.less`
- `console/src/pages/Chat/components/DeliverablesPanel/DeliverablesPanel.test.tsx`
- `console/src/pages/Chat/components/DeliverablesPanel/MediaDeliverablesRail.tsx`
- `console/src/pages/Chat/components/DeliverablesPanel/ArtifactPreviewDialog.tsx`
- `console/src/pages/Chat/components/DeliverablesPanel/mediaDeliverables.test.tsx`
- `console/src/pages/Chat/deliverables.ts`

修改：

- `console/src/pages/Chat/HostBubbles.tsx`
- `console/src/pages/Chat/sessionApi/index.ts`
- `console/src/pages/Chat/index.tsx`
- `console/src/locales/zh.json`
- `console/src/locales/en.json`

实现：

- 只在 response completed 且 items 非空时 append；
- `HostResponseCard` 的插件 `renderFn` 可能不调用 fallback；统一 host-owned append 层确保插件自绘时
  仍显示且仅显示一次，不覆盖原 `contentAppend`。验证普通 renderer、插件 renderer、历史 replay 三条路径；
- 单项/多项、折叠、文件缺失和危险类型状态；
- 每行右侧只渲染一个 `打开` 拆分下拉按钮；下拉菜单只包含 `在文件夹中显示`，危险类型禁用
  主按钮但保留安全定位；
- image/video 从普通文件列表分离为单行横向轨道，支持触控拖动、触控板、Shift+滚轮、键盘和
  scroll-snap；桌面 hover/focus 时封面变暗并显示眼睛/文件夹，粗指针设备操作常驻；
- 原生滚动条永久隐藏；在固定 wrapper 内用 absolute 覆盖层绘制可拖动滑块，`:hover` 或节流后的
  `isScrolling` 状态只切换 opacity/pointer-events；最后一次 scroll 事件后 800ms 清除状态，滑块
  宽度和位移通过 ref + requestAnimationFrame 更新，不改变高度/内外边距，不触发 React 重渲染或版面回流；
- 眼睛按钮在当前聊天页打开图片 Lightbox 或视频播放器；弹层设置 aria-modal、背景 inert、焦点锁定，
  Esc/关闭按钮可退出并恢复触发按钮焦点；文件夹按钮调用本版新增产物 open API 的 reveal action，不暴露路径；
- 打开成功/失败 toast；
- 不显示绝对路径；
- 历史对话保持；
- 使用带认证 header 的媒体请求或受限短期媒体票据，不能把长期 bearer token 拼进预览 URL；视频 Range
  请求必须保持同等会话授权，不能因原生 video 标签缺少 header 而开放匿名任意文件；
- 流式过程中不提前闪现。

### Task 5.3 安全与兼容测试

必须覆盖：路径穿越、junction/symlink、大小写碰撞、伪造 artifact id、跨员工/跨 chat、文件被移动、
可执行扩展名、同一文件去重、取消任务、shell 临时文件不误报、中文文件名、U 盘重新插入后盘符
变化、伪造图片扩展名、图片解码炸弹、视频多 Range/越界 Range、预览关闭焦点恢复、触屏无 hover、
横向轨道键盘与窄屏可用性。另做布局断言：滚动指示条隐藏、hover 显示、滚动显示三个状态下，媒体
轨道和后续文件列表的 bounding rect 必须一致，交互导致的 CLS 必须为 0。
敏感文件守卫复用 `src/qwenpaw/security/tool_guard/guardians/file_guardian.py` 的既有规则；新产物
API 不能绕过原文件预览限制，`.env`、密钥、凭据和内部账本不得登记或直接打开。

## 8. Phase 6：充值系统回归

自动化：

- 订单/回调/ledger/outbox 幂等；
- 客户端整数金额和页面文案快照；
- 额度/账本 focus 与事件刷新；
- 更新保留 billing profile；
- A/B 切槽、自动回滚后 account/newapi user/order/ledger 均不变。

把原额度保留并入上条既有回归：固定同一 NewAPI 用户，有/无 billing profile 都验证原余额继续可读；
没有业务交易时 quota 相等，有交易只核对已入账净变动，不用新账本记录总和或 UI 百分比代替余额。
复用同一次 staging 支付/对账结果，不按旧版本、文件系统、回滚次数重复收费或新增人工签核。

真实 staging：再支付 ￥1，核对微信、Billing、NewAPI、客户端四方；重启客户端后仍显示；执行一次
A→B 和一次强制 B 失败回 A，账本不增加、不丢失。
需要真实扣款时先通知用户确认；本次文档工作不创建订单或重新收费。

具体复核点（已有文件，按失败证据才修改）：

- `console/src/pages/Settings/ComputeRecharge/components/AmountCard.tsx` 及测试：整数默认值、1–100000、
  10/50/100/200 快填、￥1 对应 500 万，不恢复用户已要求删除的灰色说明；
- `console/src/pages/Settings/ComputeRecharge/index.tsx`、`console/src/api/modules/recharge.ts`：支付到账
  与额度/账本刷新；无客户自助退款按钮；
- `src/qwenpaw/app/go_claw_billing.py`、`src/qwenpaw/app/routers/recharge.py`：存量绑定迁移和代理兼容；
- `src/qwenpaw/app/go_claw_provision.py::_provision/_load_or_create_instance_id` 与
  `go_claw_credentials.py`：在升级来源或初始化前旧凭据/导入标记表明是存量盘时，不因 instance.id
  缺失/无效而重新开通、赠额或覆盖旧凭据；新盘初始化保持原流程，不能以 prepare 新建的空 data
  目录误判。`go_claw_billing.py::_load_legacy_identity/_ensure_billing_enrollment` 对异常返回可恢复
  状态，不写空 profile；已有正常 profile 不重复绑定；
- `scripts/provisioning/provision_server.py::complete_billing_enrollment` 的既有
  tokenFingerprint/proof 分支只用于确认现存 NewAPI 归属，不新增用户或改 quota。缺少可证实原实例
  关系时保留旧凭据并推迟充值初始化，不在本版扩建通用身份恢复服务；
- 上述分支复用 `tests/unit/app/test_go_claw_provision.py`、`test_go_claw_credentials.py`、
  `test_go_claw_billing.py`，以及 `scripts/provisioning/test_provision_server.py`、
  `scripts/billing/tests/test_accounts.py` 的参数化 fixture：正常旧盘、历史静态凭据、缺失/坏 ID、
  绑定冲突；断言没有创建新 NewAPI 用户/余额写入，且源文件不被覆盖。这些不新增 CI job/全量 build；
- `scripts/billing/go_claw_billing/application/{payment_service,quota_service,refund_service}.py`：回调与
  NewAPI 入账幂等，退款仅客服后台人工指定金额；账本 append-only；
- `docs/contracts/compute-recharge/`：不改换算或幂等键，条款经营主体依法保留在可访问条款中，
  不重新塞入主界面。详细支付合同沿用原专题，本版不复制第二份权威定义。

## 8A. Phase 6A：多模态附件回归与条件修复

### 已有代码定位

| Stage | 文件与入口 | 验证内容；只有失败才改 |
| --- | --- | --- |
| AT-01 选择/上传 | `console/src/pages/Chat/index.tsx::handleFileUpload`、`console/src/api/modules/chat.ts::uploadFile` | SDK 文件对象进入 FormData；不把媒体读成 UTF-8；上传成功/413/服务端异常响应分开 |
| AT-02 存储 | `src/qwenpaw/app/routers/console.py::post_console_upload` | 原始 bytes 落盘、大小限制、安全文件名；不改原媒体编码 |
| AT-03 预览引用 | `console/src/api/modules/chat.ts::filePreviewUrl`、`console/src/pages/Chat/utils.ts::normalizeContentUrls`、`src/qwenpaw/app/routers/files.py::preview_file` | 中文、空格、#、%、+、Windows 两种分隔符只正确编码/解码一次，URL query 不进入路径 |
| AT-04 内容组装 | `src/qwenpaw/app/channels/console/channel.py::build_agent_request_from_native`、`src/qwenpaw/agents/model_factory.py`、`src/qwenpaw/providers/capping_formatter.py` | image/video URL 或 rb→base64，不解码原始二进制；不支持的模型能力给明确错误 |
| AT-05 提供商 | 同上 formatter 到 provider 请求 | HTTP 错误、超时、模型不支持与 UTF-8 异常分开；mock 对 payload 断言，真实调用需保存可复核结果 |
| AT-06 流式/历史 | `console/src/pages/Chat/index.tsx::customFetch`、`console/src/pages/Chat/sessionApi/index.ts` | 多字节汉字跨 SSE chunk 正确重组，刷新历史仍保留附件引用 |

### 测试落点

- 修改 `console/src/api/modules/chat.test.ts`、`console/src/pages/Chat/utils.test.ts`，用真实二进制 fixture，
  覆盖成功/非 JSON 错误响应/取消/路径往返；
- 新增隔离 `console/src/pages/Chat/attachments.test.ts`；必要时把上传流程提取为同目录
  `attachments.ts` 再测，不用整个 SDK 重型 mock 掩盖问题；
- 注意 `console/vite.config.ts` **当前排除了** `ChatPage.test.tsx`。不得把传入该文件名当作已执行；
  修复测试隔离后解除排除，或让新独立测试实际运行，并核对测试文件清单；
- 补充 `tests/integration/test_console_header.py` 与 `tests/unit/app/channels/test_console_channel.py`：
  当前大小测试不能替代真实图片/视频，新增 PNG/JPEG/WebP/MP4 合法 fixture 与跨员工断言；
- 新增 `tests/unit/app/routers/test_console_upload.py`、`tests/unit/providers/test_attachment_formatting.py`：
  上限、损坏媒体、空文件、provider能力/格式分离；
- 加入最终 portable 验收记录：UI 添加真实 PNG 和 MP4、预览、发送、历史重放；无真实 MP4 证据
  时保持“待验证”，不宣称“多模态问题已修复”。

退出条件：有 bug 则附同样本修复前失败与修复后通过；无 bug 则记录矩阵全过且明确“未复现，未加编码补丁”。
可以先实现更新/技能/交付物，不因暂缺视频样本暂停整个版本；正式发布仍须完成此矩阵。

## 9. Phase 7：CI 与设备验收

### 9.1 自动门禁

1. console lint/typecheck/unit/build；
2. Python unit/contract/integration；
3. Rust unit 与 update-engine contract；
4. maintenance contract；
5. Windows Bridge 与 A/B executable probe；
6. release determinism（双构建摘要一致）；
7. secret scan、path traversal、mutable-path exclusion；
8. Full ZIP、Bridge、v2 manifests/components 全部验签；
9. 产物下载体积报告；
10. 附件真实二进制与错误路径回归，确认测试未被 exclude/skip；
11. 交付物权限/路径/Range 与视觉滚动条零位移断言。

现有工作流落点：前端 `.github/workflows/frontend-tests.yml`，Python `.github/workflows/tests.yml`，
充值 `.github/workflows/billing-tests.yml`；Windows 完整包 `.github/workflows/desktop-build.yml`。
新增测试必须被这些 job 实际收集；门禁报告保存 commit、命令、测试数、排除项与 artifact SHA。

### 9.2 实机矩阵

| 来源 | 文件系统 | 场景 |
| --- | --- | --- |
| 干净 v2.0.1 程序 + 确定性旧格式测试数据 | NTFS 短路径 | Bridge → v2.1.2，复用本行核对聊天/账户/余额 |
| 干净 v2.0.1 程序 + 同一测试数据 | 目标 U 盘 | 同上，不用失败污染盘替代 |
| 干净 v2.1.1 程序 + 确定性旧格式测试数据 | NTFS 短路径 | Bridge → v2.1.2，复用本行核对聊天/账户/余额 |
| 干净 v2.1.1 程序 + 同一测试数据 | 目标 U 盘 | 同上，含原有余额且未建 billing profile 的情形 |
| v2.1.1 + 历史数据/充值 profile | 目标 U 盘 | 保留全部数据 |
| v2.1.2 A | NTFS + U 盘 | 增量 A→B 成功 |
| v2.1.2 A | NTFS + U 盘 | 锁/断电/校验失败回 A |

每次记录：release SHA、组件下载字节、active/target slot、transaction、进程路径、API version、
员工/插件/quota/recharge readiness、聊天与文件 hash。

上述聊天 hash **仅限小型测试 fixture**；合法迁移会改变 JSON 排版/元数据时比较规范化内容与 ID，
不机械要求原始字节完全一致。复用本矩阵的成功/回滚运行，仅增加两组断言，不扩成组合爆炸：

1. **历史可读**：fixture 覆盖默认/自建员工、普通/归档会话及一份附件。比较原有 chat/session ID、
   消息正文与附件可读性；按旧 API 读取，确认回滚到实际来源版本后仍可打开。磁盘文件未删不等于通过。
2. **额度归属和数值**：复用既有 staging 只读对账，核对相同 NewAPI 用户及原余额；有 profile 则
   account 也不变，无 profile 则新建的 billing account 仍绑定原用户。无交易前后相等，有交易按
   合同 BILL 的整数差额核对，不为对账发起新支付。

缺失/损坏 ID、静态凭据、归属冲突由 Phase 6 的快速参数化单测覆盖，不再为每项新增实机全流程。
已有安全/断电/签名/干净设备门禁保持；这两组断言合入原报告，不增加独立签核或上线等待窗口。

## 10. 性能目标

- update check 只取小 release index 与组件摘要，总下载 < 500 KiB；逐文件完整清单在 download/planning
  阶段获取，不把重型运行库数万文件列表算作每次后台 check；
- 状态 API P95 < 100 ms，不扫描整个程序树；
- heavy runtime 未变时不得下载对应组件；
- v2.1.1 → v2.1.2 的实际下载目标较旧 477 MB 全包下降至少 60%，最终数值以 CI 报告冻结；
- 设置齿轮与“检查更新”按钮橙点：SSE 正常时同步 < 2 s；断线轮询时 <= 10 s + 单次请求耗时；
- 100 个产物中普通文件默认只展开 3 项；媒体仅挂载可视窗口及相邻卡，不把媒体限制为 3 项；
- 打开/定位 API 不全量读取文件；类型校验只读有界文件头，P95 < 200 ms（不计系统应用启动时间）。
- 媒体轨道只预取当前卡及前后各一张缩略图，不预取原图/视频；缩略图单项目标 < 300 KiB；
  视频使用浏览器 Range 播放，不经 JS 全量 Blob 缓存；图片由浏览器正常解码，限制解码像素，不能
  声称浏览器看图不占用完整解码内存；
- check/download/SSE 每产品只设一份调度；复制/hash 用后台有界 I/O，不占 UI 主线程；
- 老用户保护不新增启动全盘遍历、聊天全量 hash/备份或远端调用；路径校验为固定数量字段，身份
  判断复用已加载标记/凭据。额外内容核对只在现有测试中运行，不进入 UI 首屏或每次请求路径；
- 固定 320/768/1440px 与 Windows 125%/150% 缩放验证 overlay 滚动条零位移；鼠标、键盘、触屏均可操作。

若确定性构建导致 heavy runtime 摘要无意义漂移，先修构建，不通过放宽下载目标掩盖问题。

## 11. 发布顺序

1. 部署只读 staging manifest/components；
2. 使用环境变量 endpoint，只在干净样本测试；
3. 完成全部设备矩阵；
4. 创建自有仓库 draft Release；
5. 从 draft 重新下载并验签全部资产；
6. 小范围内部盘升级；
7. 经发布授权后，先公开同一组不可变资产并验证两种 manifest 均可访问；
8. 再在受控窗口原子切换生产入口（GitHub latest 与镜像不能跨系统原子提交，逐一核对目标版本与 SHA）；
9. 观察 24 小时 update transaction、rollback、充值和核心 readiness；监控须另行配置，不以文档承诺后台监听。

如使用 OSS，工作流只读取 `GO_CLAW_OSS_BUCKET`、`GO_CLAW_OSS_PUBLIC_BASE_URL` 以及同名前缀的
三项 Secret；不提供上游兼容默认值。配置缺失或目标包含 `qwenpaw`/`agentscope` 时必须在任何上传前
失败，不能退回源项目的存储桶。

生产回滚只切回上一份不可变 manifest；绝不覆盖已发布资产。

## 12. 完成定义

- [x] 视觉方案确认，布局和交互已记录；
- [x] 具体代码落点、目标接口/兼容合同、成功/失败/产物时序已文档化；
- [x] v2 更新合同与确定性组件构建通过；
- [x] 本地未签名 Main Full Build、portable 结构/凭据边界及 F 盘隔离复制/哈希核对通过；
- [ ] 旧客户端可通过签名 Bridge 进入 A/B（Bridge 可执行合同已通过，真实签名产品盘待验收）；
- [ ] 只下载变化组件的网络证据达到性能目标；
- [ ] A/B 成功、断电恢复、自动回滚均在 NTFS 和 U 盘通过，原聊天在实际来源版本/目标版本均可读；
- [x] 设置齿轮与“检查更新”按钮自动橙点在便携浏览器模式生效，版本号无点，安装开始时双点消失（自动回归）；
- [x] 技能一级页 Banner 可进入并返回市场（自动回归）；
- [x] 普通交付产物可通过右侧拆分下拉按钮安全打开/定位；图片/视频可横向浏览、悬浮操作并在
  当前页面安全预览；历史对话可恢复；
- [ ] 复用一次充值真实 ￥1/对账回归，原账户余额与账本跨更新保留，不重置、不重复赠额（￥1 的
  微信回调、订单、唯一额度增量和双分录已于 2026-09-05 只读核对；仍待实际 A/B 前后余额复用）；
- [x] 附件自动矩阵完成并单点修复 AT-03；
- [ ] 真实 UI 选择器/多模态 provider 项保持待验收；
- [x] 维护时序、事实基线、变更台账和产品文档同步；
- [ ] 所有资产来自同一 commit/build，签名和 SHA 一致；
- [x] 不存在向 QwenPaw 上游的任何写操作；桌面 OSS 发布配置缺失时 fail closed，并拒绝
  `qwenpaw`/`agentscope` 目标。

## 13. 实施顺序与交付批次

1. **D0 文档定稿（本次）**：design/plan/目标合同/附件证据；不改运行代码或外部状态。
2. **D1 低耦合前端**：Phase 4 技能 Banner；现有充值 UI 回归。独立测试通过后保留审查快照。
3. **D2 合同与纯逻辑**：Phase 1 schema/组件构建 + Phase 5 collector/store/security，先 mock 和离线 fixture。
4. **D3 更新事务**：Phase 2 引擎/Bridge/锁/恢复，先小样本故障注入再完整盘；Phase 3 接真实进度。
5. **D4 产物体验与附件**：Phase 5 UI/预览/历史集成 + Phase 6A，完成冻结的视觉验收。
6. **D5 发布候选**：Phase 6/7 完整回归、四方对账、同 commit Main Full ZIP 与 staging 设备验收。

每批做独立小提交；本表是依赖关系，不表示要创建新任务或使用并行代理。任何一批出现新证据只修
对应 stage。正式 build、CI 通过、实机通过、正式发布分别记状态，不能互相替代。

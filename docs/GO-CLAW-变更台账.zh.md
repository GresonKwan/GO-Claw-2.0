# GO CLAW 变更台账（历史变更单一记录）

> 本文件是 GO CLAW 二次开发所有**已发生变更的唯一历史记录**。当前部署与发布状态见
> `GO-CLAW-项目事实与发布基线.zh.md`。规则见 `GO-CLAW-文档规范.zh.md`。
> 每条条目：改动内容 / 原因 / commit / 验证方式 / 关联文档。
> 基线：QwenPaw v2.0.1（`24813b3` 导入）。文档目录见文末索引。

---

## 2026-09-05 · v2.1.2 功能接线与发布候选验收（未发布）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 接通组件 manifest/index/catalog、CI 构建与 draft 发布资产；新增独立 Bridge 单进度页和持久结果 | 让 legacy 客户端进入签名 A/B，正式资产只含变化组件 | 未提交 | 更新/构建/发布/维护合同 126 项；Rust 63+22+38 项；Bridge headless 可执行合同和正常 UI 脚本由 NSIS 3.11 编译 | update-v2 README、实施计划 Phase 1–3 |
| 设置齿轮与检查更新按钮双橙点、同一弹窗和单进度条；技能页右侧“浏览技能” Banner | 落实已确认视觉并避免重复轮询 | 未提交 | TypeScript、production build、更新/技能定向前端测试通过；真实缩放/触屏待验收 | 设计 Phase 3–4 |
| 新增逐轮交付产物收集/持久化/归属鉴权/短期媒体票据；普通文件拆分下拉，媒体横向窗口化、悬浮预览/定位，滚动条覆盖层不占布局 | 让产物在当前轮及历史会话安全恢复，100 项时不预取全部媒体 | 未提交 | Python deliverables 合同与前端组件测试通过；窗口化 100 卡只挂载首屏和相邻卡 | 目标合同 DL、实施计划 Phase 5 |
| 修复附件路径段未编码、服务端二次 URL 解码；保留原始 PNG/JPEG/WebP/MP4 bytes，损坏/空媒体返回明确错误，补四字节 SSE 分块回归 | 解决特殊字符路径被截断/二次解释导致的 UTF-8 表象，不用宽泛二进制转码掩盖 | 未提交 | 后端附件 9 项、前端附件/交付物相关测试通过；系统文件选择器与真实多模态 provider 待实测 | 附件 incident、Phase 6A |
| Main Build 支持显式隔离 Node/npm/Python 与可写 npm 缓存；Tauri hook 由固定 Node 显式执行一次；NSIS 资源改从 include 目录解析；前端测试脚本改为 Windows/POSIX 通用 Node 参数；产品唯一版本提升到 2.1.2 | 避免旧系统 npm 自带 Node、外置 Cargo target、Program Files 缓存与 POSIX 环境变量语法破坏 Windows 构建/验收 | 未提交 | 本地未签名 Main Build 成功：NSIS 622564466 字节、portable ZIP 634905818 字节；包装/品牌合同 46 项、前端 1244 项通过 | `build_win_pyinstaller.ps1`、`nsis-hooks.nsh`、`console/package.json` |
| 在完整 staging 上两次生成 7 个互斥组件并复制 RC 到 F 盘独立目录 | 验证真实 1.43GB 产品布局的精确归属、确定性以及不覆盖客户数据 | 未提交 | 两轮 7 个 ZIP + draft 共 8 文件逐一 SHA-256 相同；组件压缩总计 634241874 字节；F 盘 13264 文件/1432526282 字节及 8 个关键哈希一致 | 实施计划 D2/D5、事实基线 |
| 启动 F 盘隔离 RC 并核对进程归属、API、插件和真实页面 | 将静态构包证据提升为未绑定态产品启动证据，避免误用 F 根客户数据 | 未提交 | 版本 2.1.2、health ok、5 员工加载；qwen-image/wan27 loaded/enabled 且 5 workspace 注入；技能 Banner/充值入口 UI 可见；无异常栈 | 实施计划 D5、事实基线 |
| 经用户授权把 F 根最小账号绑定状态临时复制到隔离 RC 并重启，只读验收额度/模型/充值 | 区分公共包未绑定降级与已绑定老用户兼容，不复制聊天数据库 | 未提交 | 四个 API 200；真实 UI 显示 41% 额度、模型三档、整数充值及 10/50/100/200 快捷按钮、既有账本；未下单/未调用付费 provider | 实施计划 D5、事实基线 |
| 在隔离 RC 内实际调用生图与最低规格文生视频，并重评 Windows 签名门禁 | 验证“工具可调用”而非只看注册日志；避免把 Authenticode 与 updater 完整性签名混为一谈 | 未提交 | 生图到达上游后周配额 429；视频三次到达上游后负载饱和 429，参数正确、无产物；CI Tauri key/pubkey 已存在且匹配，Authenticode 降为后续体验优化 | 实施计划 D5、事实基线 |
| 配置 New API 媒体双管线：Token Plan #3 为 priority 10 主路，阿里直连 #2 为 priority 0 备用；清理文字渠道 #1 的错误媒体声明，`RetryTimes` 调为 2 | Token Plan 周额度/容量故障时自动转入协议兼容的阿里直连，避免有 GO CLAW 额度的用户仍无法生成 | 运营变更，无代码 commit | 变更前 SQLite backup + 前后 integrity `ok`；图片日志 `use_channel=["3","2"]` 并返回真实图片；3 秒文生视频日志 `重试：3->2`，约 100 秒返回真实 MP4 | 事实基线 4.1；备份 `one-api-before-media-fallback-20260905T020257Z.db` |

本批未推送、未触发 GitHub CI、未创建 tag/Release、未切换生产更新源，也未写 QwenPaw 上游。
正式签名大包、独立 F 盘 A/B、已绑定真实账号/多模态 provider 和跨版本余额回读必须与自动测试分开记录。
隔离 RC 不含客户 provision/credentials，额度 404、模型档位 503、充值初始化中属于未绑定态；生产 v2
索引/目录及签名当前均为 404，检查更新因此在 discover 阶段 `DOWNLOAD_REJECTED`，本轮未改生产源。

## 2026-09-05 · HTTP/SSE 与独立引擎交接（实施中）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 新 ComponentUpdateManager 接 status/check/download/install/events，保留旧字段及空 body；目标摘要/交易绑定、同产品请求合并、持久 revision、同源保护 | 将新引擎接到现有后端入口，阻止旧全量 EXE 路径被继续调用 | 未提交 | 本批基础回归 79 项通过；新增规划阶段冻结/进程边界等继续回归；非真实安装 | Task 2.4、`go_claw_component_updates.py` |
| 独立 engine 缓存到槽位外，参数化隐藏进程、限制输出、不继承客户密钥；下载观察不占会阻塞 Python 退出的默认线程池 | 保证安装引擎能在后端退出后继续事务，避免退出等待下载 | 未提交 | 9 项进程适配测试（包含模拟进程，不是真实产品退出）；实际双 2.0.1 样本只读 source-version 均返回 2.0.1 | `go_claw_update_engine.py`、native source-version |
| 真 TLS 矩阵增至 10 项；完成 partial 断电后免网络提升；活动数据流与空闲/总超时分别限制；回滚增加受控来源探测 | 避免大包源不支持 Range 时活动响应被固定短总时限截断；恢复先验证再解锁 | 未提交 | Rust 最新已完成批次 library 62 / integration 36，通过（共享测试重复，不相加）；reconcile 新用例另计后续结果 | download/bootstrap/native |
| Full staging/manifest 将独立 engine 设为必需程序；Windows 构建先 build engine，再复制入 binaries | 防止新更新 API 入包但引擎 EXE 遗漏 | 未提交 | 本地构包合同回归待本批输出；尚未 Full/Main build 或运行 CI | `build_win_pyinstaller.ps1`、assemble/stage |

本节是接线前阶段记录；历史目录、Bridge、统一前端和交付物的后续状态以上一节为准。完整签名
构建与实机验收仍未完成。未发布、未改生产更新源、未修改 F 根产品。

## 2026-09-05 · HTTPS 故障矩阵与持久化状态读取（开发中）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 小索引和签名共享 15s 预算；损坏缓存隔离；本地内容复用失败仅追加相应组件下载，保留已显示进度 | 固定目标和网络字节语义，避免损坏片段污染包 | 未提交 | 7 项 loopback 真 TLS 测试通过：正常证书、Range/取消续传、body 断流、200 重下、ETag/降级跳转拒绝、坏 partial/cache；非实际大包/无进展超时全矩阵 | update-v2 README、staging/download |
| 后端新增 v2 DTO 和有界 journal reader、双快照 StatusStore | 为统一 HTTP/SSE 准备重启后递增 revision，status 不扫描程序/聊天 | 未提交 | 26 项通过；读取 Rust 原始紧凑字节计算 hash，避免浮点重序列化差异；未变状态不重复写盘 | `go_claw_update_contract.py`、`go_claw_update_state.py` |
| 安装锁独占创建；未完成预备份隔离后可重试；Windows 路径比较支持大小写/分隔符/verbatim/短路径别名 | 避免覆盖另一安装锁或误判进程不属于当前产品 | 未提交 | Rust library 56 项、integration target 30 项通过（包含共享模块重复执行，不相加作为独立用例）；Python 状态/回执/维护共 56 项；维护 9 顺序/6 图 | 运行时序 §6A |

状态模块尚未接入 HTTP manager；没有新增在产品盘执行的安装。真实签名大包、Bridge、UI、交付物
及数据保留实机矩阵继续推进；上述结果不代表 v2.1.2 完整验收或正式发布。

## 2026-09-05 · A/B 启动与独立安装协调器接线（开发中）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| PortableState 解析验签槽位；后端/Python/Node 从 program_root 定位，共享数据根不变 | 将已测试的槽位合同接到实际启动代码 | 未提交 | portable 6 项通过；Debug binaries 和 Release binaries 检查通过，非 Full Build | 运行时序 §2、plan Task 2.2 |
| 独立 engine 增加 discover/stage/status/install/recover；备份固定根文件、移动非活动槽、健康后提交指针；失败完整恢复、保留首错 | 补独立事务与断电恢复骨架，避免原地改动活动 binaries | 未提交 | bootstrap 4 项通过，含 11 个持久化/文件移动中断点；未签名入口在停进程/加锁前拒绝 | 运行时序 §6A、update-v2 合同 |
| Windows 本机探测绑定监听 PID/映像/一次性挑战；候选使用 Job 收拢生命周期；健康回执单独报告员工/插件/工具/quota、本地 billing profile | 不再将缓存端口/API version 或 HTTP 200 当作产品可用 | 未提交 | Python 回执 20 项通过，覆盖禁用员工、缺插件/工具、额度异常、缓存、Origin/远端拒绝；只读 TCP PID 用例待本批完整 Rust 输出 | `update_readiness.py`、`update_engine/native.rs` |
| 固定候选健康并退出后才发布 active/lastKnownGood 的时序；增加安装/回滚可执行顺序 | 首次 legacy→A 不能提前声称 A 已知可用；保留原数据期间新增消息 | 未提交 | Python 维护 8 项通过；维护工具 9 顺序/6 图通过 | 运行时序、设计与实施计划 |

未在 F 根产品或独立 USB 样本执行此新引擎，未改变生产更新源。当前协调器仍需补齐真实签名包与
Windows 子进程故障验收、来源版本回滚后的 API 可读性确认、Bridge 及后端/统一 UI 接线。
没有 Full/Main Build、CI、Release 或完整 v2.1.2 验收完成结论。

## 2026-09-05 · F exFAT 历史更新事务及无损证据边界

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| F 独立 2.0.1 样本经旧 API 下载/验签/安装并自动重启 2.1.1；同步事实与计划 | 完成交接要求的另一文件系统真实事务取证 | 未提交 | API/UI/版本一致、无锁/错误；双程序哈希同 NTFS；额度 2.3/0.9456/41 前后相同；五员工 running，但媒体兼容与档位加载失败 | 当日 incident、事实基线 §1 |
| 修正聊天验收统计和完成范围 | 原基准五个聊天索引为空；旧模糊匹配多算两份技能说明为 chat/session | 未提交 | 前后 1107 文件无缺失；5 空索引/12 身份凭据摘要未变；非空消息/归档/附件尚未证明 | v2.1.2 plan Phase 0/7 |
| journal 持久化拒绝同交易目标版本/槽位/摘要变更 | 落实下载目标冻结，不允许刷新/恢复悄悄换包 | 未提交 | Rust 17 项通过，八个目标字段分别改变均拒绝且不覆盖原 journal | `update_engine/state.rs`、update-v2 README |

本次未改生产源、历史包、F 根目录产品；测试目录和旧程序备份保留。没有 v2.1.2 Full/Main Build，
新引擎仍未接线，历史包 readiness 失败不能当成当前另一生产包的失败证据。

## 2026-09-04 · NTFS 完整 staging 安装取证及媒体回归

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 新引擎 body 断流/短读回退完整 range 检查点后有限重试，重试不重复拼接损坏后缀 | 之前只重试取得响应头失败，响应体中断直接退出；保持有界内存/增量 hash | 未提交 | Rust 16 项通过；本地 Read 故障注入，不代表真实 HTTPS/ETag 矩阵；模块仍未接线 | update-v2 README、`update_engine/download.rs` |
| 扩大现有产品就绪与模型选择回归 | 核对当前开发代码与历史 staging 故障的边界 | 未提交 | Python presets/plugins/product/router/provision/billing 六组 100 项，前端 ModelSelector 9 项通过；不与被包含的 21/20 项重复相加 | v2.1.2 实施计划 |
| Rust 清单要求固定可运行入口/运行库/媒体种子；槽位原始清单先验签再解析 | 对齐 v2 签名及完整产品合同，防止签名正确但内容不完整被规划安装 | 未提交 | Rust 14 项通过；新增逐项缺失拒绝及错误签名先于 JSON 解析测试；仍未接入产品启动 | update-v2 README、`update_engine/manifest.rs`、`slots.rs` |
| 修正生产公共 manifest 的日期化事实，区分历史 staging | 只读 HTTP 当前返回 2.1.1，而旧文档仍称生产 2.1.0 | 未提交 | 两 URL 的 version/pub_date/资产 URL/签名字段，只读；未下载生产包、未核对服务器软链 | 事实基线 §1 |
| 记录带更新器 2.0.1 在 NTFS 安装 477MB staging 包并自动启动 2.1.1；分开记录媒体兼容失败 | 程序替换成功不能替代产品 readiness | 未提交 | API/UI/标记一致；无安装锁/错误；聊天身份摘要未变；旧媒体插件因 `<2.1.0` 上限禁用，未关闭事故 | 事实基线、当日 incident |
| 增加真实仓库媒体种子对旧 1.0.0 插件的迁移回归，覆盖 host 2.1.1/2.1.2、重复执行与聊天身份哨兵 | 固定本次现场暴露的历史兼容条件，验证已有迁移代码 | 未提交 | bundled plugin 测试 21 项通过；Flake8、维护合同通过；非真实媒体生成测试 | `tests/unit/app/test_go_claw_bundled_plugins.py` |
| 从同一未更新基准复制 F 独立样本 | 继续交接要求的真实 U 盘验收 | 未提交 | `F:\GC201-TRY-0904` 共 14971 文件复制无失败，根壳/后端哈希同基准；尚未启动 | 当日 incident、v2.1.2 plan Phase 0 |

未修改历史 staging 包、生产源或 F 根目录产品；未发布、未完成 v2.1.2 Full Build。

## 2026-09-04 · 旧版更新入口差异取证（安装前阶段）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 记录原始 v2.0.1 与带更新器候选基准的双程序哈希；实施计划区分自动在线与手动签名 Bridge 入口 | 用户启动后的原始样本更新 API 404，真实浏览器只显示上游 pip/uv 升级；不能按版本号假设兼容 | 未提交 | `/api/version=2.0.1`、进程路径、真实设置/版本弹窗；候选历史日志更新状态 API 200，当前运行待核验 | `incidents/2026-09-04-v201-clean-sample-preflight.zh.md`、plan Task 0.2/2.3 |
| 带更新器候选完整下载、独立验签；新增只读取证脚本和监听进程归属记录 | 测试后端退出后，旧端口被 F 盘产品复用，必须防止把其他产品版本当作升级成功 | 未提交 | staging 完整包 477092325 字节、交接哈希及 ED 签名通过；D 程序哈希未变、无安装日志；停机后 1107 项数据摘要可读，未执行安装 | 同上；`scripts/verify/capture_portable_update_evidence.ps1` |

未安装或修改两个基准程序，未执行上游升级命令，未修改生产源或 F 盘。此项不是 NSIS 失败 stage，
也不证明带更新器候选来源或升级成功；仅修正已被实机证据否定的基准能力假设。

## 2026-09-04 · v2.1.2 组件基础与旧身份保留（本地开发，未发布）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 已知 PyInstaller 布局自动归属、组件签名装配；缺壳/运行库/两个媒体插件种子拒绝构包 | 避免生成漏媒体工具的组件包，保持精确互斥归属 | 未提交 | 构建/机器/维护合同合计 99 项通过，包含新装配和默认布局用例 | update-v2 README、plan Task 1.2 |
| 新增 Rust 更新引擎基础模块，分块摘要/签名、路径与 ZIP 校验、差异规划、journal 回退、独占锁、共享数据根、进度逻辑 | 为 A/B 提供可测试基础；不先改变现行安装流程 | 未提交 | Rust 12 项通过（含 minisign 公共测试向量）；下载代码已编译但真实 Range/中断矩阵待测；未接应用启动或更新按钮 | update-v2 README、plan Task 2.1 |
| 旧 ID 损坏/缺失有旧盘证据时保留原件，禁止新建账号；损坏 billing profile 不覆盖；billing 版本复用产品唯一版本源 | 保护原额度归属，不靠重新开户伪装恢复；固定路径检测无聊天扫描 | 未提交 | 新增 8 个回归用例，provision/billing 合计 20 项在隔离环境通过；Flake8 和维护校验器通过；运行图和初始化先后约束同步 | 运行时序 §3、plan Task 2.5 |
| 按交接创建新的 NTFS v2.0.1 样本并核对程序哈希 | 真实安装验收不可由新引擎纯测试替代 | 未提交 | 双哈希与只读基准一致；启动 EXE 请求遭本机工具策略拒绝，未绕过、未进入安装 stage | `incidents/2026-09-04-v201-clean-sample-preflight.zh.md` |

未合并 main、未触发 CI、未创建 tag/Release、未改生产更新源或服务端。尚无完整 v2.1.2 build。
F 盘独立目录测试已获用户许可，现有产品和客户数据未动。D 盘安装隔离 Rust/Python 测试环境；
不把本地依赖安装或 Rust 合同测试称为 Main Build。其余 A/B/Bridge、统一更新 UI 和交付物按实施计划继续。

## 2026-09-04 · v2.1.2 首批代码落地（本地开发，未发布）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 技能一级页新增固定文案 Banner，按钮靠右；复用市场 query、保留原入口、返回刷新；空/非空/加载中均可进入 | 落实已确认 UI，不新增市场 API 或常驻请求 | （待推送） | SkillMarketBanner/index 两组测试与充值回归共 8 项通过；TypeScript 和前端 production build 通过（既有分包警告保留）；真实窄屏视觉待验收 | v2.1.2 plan Phase 4 |
| 新增更新 index/manifest/transaction 与 status/deliverables 五份机器 schema；新增安全精确归属、确定性分包、流式 ED 验签与索引工具 | 将更新安全边界转为可执行构建合同，先验证纯逻辑再接引擎 | （待推送） | 三组新增 scripts 测试共 90 项通过，既有维护合同测试 6 项通过；Flake8、维护校验器、diff check 通过；只用临时数据与测试签名 key | `contracts/update-v2/README.zh-CN.md`、v2.1.2 plan Task 1.1–1.3 |

新工具尚未接入正式 workflow，A/B/Bridge/交付物运行流程未实现；不代表完整 v2.1.2 build、CI、
USB 升级或旧用户无损验收完成。本轮未改生产源、服务器、客户盘、账户或运行时序。

## 2026-09-04 · v2.1.2 设计与实施合同定稿（仅文档）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 固定已确认的双橙点/弹出组件/单进度条、右侧技能 Banner 按钮、逐轮交付区与覆盖层滚动指示条；补齐组件 A/B、Bridge、锁、回滚和接口兼容目标 | 将用户已确认方案落实到具体代码落点与验收，避免“下载后自动安装”、旧壳停后端丢进度和历史产物丢失 | （待推送） | 代码入口核对；文档链接、Mermaid 和维护合同校验；不等同功能测试或发布通过 | `superpowers/specs/2026-09-03-go-claw-v2-1-2-design.md`、`superpowers/plans/2026-09-03-go-claw-v2-1-2-implementation-plan.md`、`contracts/v2.1.2/README.zh-CN.md` |
| 记录附件 UTF-8 报告的有限证据：当前 F 盘 PNG 上传/预览/SSE 未复现；UI 选取与视频待验证，不保留推测性编码补丁 | 区分未复现、已修复与未覆盖，避免再次按最终错误提示猜根因 | （待推送） | 2026-09-03 本机 API 取证及源码阅读；待按矩阵补真实媒体/错误路径 | `incidents/2026-09-03-chat-attachments-utf8-investigation.zh.md` |
| 按用户要求细化“老用户聊天与原额度不丢失”：固定数据根/旧会话映射、保留原账户与余额、异常身份禁止重置；实际来源版本可回读。保护并入既有逻辑，测试仅补历史/余额两组断言，不新增启动全盘扫描、联网审计或发布流水线 | 解决 review 中数据仍在却不可见、额度 200 却换账户、旧盘身份异常未覆盖的缺口，同时控制运行开销 | （待推送） | 路径/初始化/绑定代码复核、文档一致性与维护合同校验；行为仍待实施与原有测试验收 | v2.1.2 design §2.5、plan Task 2.2/2.5、Phase 6、§9.2、目标合同 UP-C4/BILL |

本条仅记录设计冻结与核查文档，不表示 A/B/交付物已实现、CI/Main Build 已完成或 v2.1.2 已发布；
未更改当前运行顺序、生产更新源、服务器或产品盘。充值生产状态差异仍需按计划 Phase 0 只读复核。

## 2026-08-13 ~ 08-14 · Windows 便携包

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 便携包自包含 staging（backend/python/node 三件套）与 ZIP + SHA-256 产物 | 插 U 盘即用 | 8cee6fd | `scripts/verify/launch_tauri_windows_portable.ps1` |
| 禁用安装版自动更新、强制单实例 | 便携包不应被上游更新覆盖/多开 | 87d66ad | Rust 单测（updates.rs/client.rs） |
| CI 修复：console lockfile 入库、Node 堆内存、无签名降级、subst 盘符兼容 | Windows 打包链路可用 | c8b1390, 2092ed2, b95c5c9, 767d77e | desktop-build 绿 |
| 产物改名 GO-CLAW-Portable-*、二进制兼容修复、消费方对齐 | 品牌一致性 | 0275186, dd17b3d, 622d456 | 08-19 构建 run-32240355388 成功 |

关联文档：`docs/superpowers/plans/2026-08-13-qwenpaw-windows-usb-portable-launch.md`（状态：已完成）

## 2026-08-14 · 客户可见层换牌 + 中文锁定 + 预设员工

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 设计规格与实施计划 | — | f32d8e2, 8591545, 2844a91 | 用户逐节确认 |
| GO CLAW 品牌资产、界面文案、头部导航简化 | 客户产品形态 | a2ba09a, 25c527c, 1f14a0b, a690f8d, 462a3f8, 9ef7b9b | `Header.customer.test.tsx` 等 |
| console 锁定中文、语言切换失败兜底 | 目标客户只说中文 | a943bf9, 0b9e043, e0d1cd3 | `fixedChineseLanguage.test.ts` |
| 4 个专家数字员工 + 首启迁移（幂等、跨进程锁、crash 恢复） | 开箱即有员工 | 6e59e1a, 09e17ae, 3d6970e, d2ac582, 14d199f, f6c112d, 5c2357b, dfb33cb, 56cee54 | `tests/unit/app/test_go_claw_presets.py`（21 例） |
| 桌面壳/安装器换牌 | 品牌一致性 | fb0c288, 62d36f5 | 启动冒烟测试 |

关联文档：`docs/superpowers/specs/2026-08-14-go-claw-customer-rebrand-design.md`、`docs/superpowers/plans/2026-08-14-go-claw-customer-rebrand.md`（状态：已完成）

## 2026-08-15 · 运行时品牌 + 批次凭证交付

| 改动 | 原因 | commit |
|------|------|--------|
| 运行时提示词自称 GO CLAW | 品牌一致 | 71f094b, f4ef5e2 |
| 批次凭证一次性导入（`GO-CLAW-Config/credentials.json`）、交付模板入包、批次网关 endpoint | 免手动配 key | e71a9b4, 6dd68dc, 1f009a4, 720b3a2, 3813734 |
| 交付 key 校验（拒绝截断 key） | 防坏凭证 | 9594ca8 |

关联文档：`docs/superpowers/specs/2026-08-15-go-claw-runtime-brand-and-batch-credentials-design.md` 及同名 plan（状态：已完成）

## 2026-08-16 · 媒体工具 + 成本控制

| 改动 | 原因 | commit |
|------|------|--------|
| 捆绑 qwen-image / wan27 媒体插件并随包安装（竞态安全、防符号链接逃逸） | 员工开箱可用生图/生视频 | 1a6bbea, e4cdbb4, e24f027, b1d7cd9, 51f3466 |
| 媒体工具凭证回落到全局 DashScope provider | 免逐工具配 key | 7a655f7, 63c0361 |
| 媒体工具低成本默认模型 | 控制成本 | bd21752 |
| 进程内媒体频次配额（图 60s/6 张·时，视频 2 次/时单并发） | 防客户刷量 | 54bc5f0 |

关联文档：`docs/superpowers/plans/2026-08-16-go-claw-media-first-call-and-cost-controls.md`（状态：已完成；注意其中模型默认值已被 08-19/08-20 决策取代，见下）

## 2026-08-19 · 首启自动开通 + NewAPI 计费体系

| 改动 | 原因 | commit |
|------|------|--------|
| 首启自动 provisioning 客户端（instance.id、HMAC 签名、失败重试不阻塞启动） | 客户零配置 | fb894dc |
| provisioning 服务端（验签、幂等、建子用户、签发令牌、写额度） | 自动开户 | dc6ac28 |
| 媒体工具双协议：aliyuncs 走 DashScope SDK，其余走 NewAPI OpenAI 兼容 + 任务轮询 | 媒体流量走中转 | 47709d5 |
| CI 从 secrets 注入 provision.json 入包 | 构建期注入 | 27aa5a6 |
| 交付 key 校验放宽接受 NewAPI 格式 + 未知模型自动注册 extra_models | 中转模型名兼容 | 676a00b |

关联文档：`docs/go-claw-auto-provisioning.zh.md`（持续更新）

## 2026-08-20 · 现场问题修复批次 1

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 媒体频次放宽：图 20s/15 张·时，视频 4 次/时 | 客户工作流撞限 | 29500a7 | test_media_quota.py |
| "空响应"修复：恢复被 agentscope 吞掉的取消语义 + 空流加固 + 前端 stop 竞态 | 停止/插队重发被误报为空响应 | 03fafa4 | test_retry_chat_model.py（新增 2 例） |
| 媒体模型不可用自动降级（只对不可用类错误）+ 编辑默认模型对齐中转渠道 qwen-image-2.0 | 编辑接口 503、默认模型无渠道 | e14008f | test_media_openai_mode.py（新增 3 例） |
| provisioning 加固：必填配置启动校验、拒收掩码 key、用户名扩 48bit、限流只计新实例、文档路径修正 | 空 secret 可无鉴权开户、掩码 key 永久坏档、撞名永久 502 | 686eeac | test_provision_server.py（8 例） |
| 微信渠道失败可见可恢复：死 token 停转+清档+健康如实上报、去重 key 退化修复、restart 支持热加载 | 上游原生 bug 被便携包形态放大 | 6a51a39 | test_wechat_failure_paths.py / test_channel_hotload.py（6 例） |

背景证据：`../../GO-CLAW-debug计划.md`（工作区，含 New API 侧排查记录）

## 2026-08-21 · 现场问题修复批次 2

| 改动 | 原因 | commit |
|------|------|--------|
| 新签令牌默认不限额（用量仅受用户账号额度约束） | 令牌层限额导致"充值不生效"错觉 | 8561e1d |
| 微信扫码成功自动启用+自动保存 | "登录成功"假象，配置从未落盘 | 7c74bd3 |

## 2026-08-24 · 规范化

| 改动 | 原因 | commit |
|------|------|--------|
| 文档修正：provisioning 公网路径/nginx 重写、用户名格式、额度模型 | 文档与部署不符 | ae6a839, e1e41dc |
| CI 存量还债：pre-commit 卫生、pylint 测试惯式放行、过期测试对齐 GO CLAW 行为、渠道注册告警 | CI 长期红 | 48ae45a |
| feishu 渠道 pkg_resources shim 移到 lark_oapi 传递导入之前 | setuptools≥82 环境 feishu 渠道无法加载 | 6a4472e | registry 含 feishu（本地 setuptools 84 验证） |
| `.gitignore` 的 `AGENTS.md` 规则改为 `/AGENTS.md` 并补录 6 个模板文件 | 裸规则误伤 md_files 模板，CI/打包缺 AGENTS.md | 6a4472e | CI test_agents_router |
| 测试 regex 对 Windows 路径用 re.escape；`.gitattributes` 强制 SVG LF | Windows 测试失败/资产哈希不一致 | 6a4472e | test_go_claw_bundled_plugins / branding 测试 |
| test_offload_while_running 在 Windows 隔离（skipif win32） | 同一机制的其他用例在 Windows 全过，仅此用例 entry 永不出现；无 Windows 环境可调试，功能在 mac/Linux 有覆盖 | 3526338 | 标注待有 Windows 环境后复查 |
| 建立变更台账与文档规范，旧 plan 补状态标记 | 规范化（用户要求） | f4d93e9 |

## 2026-08-24 · 产品迭代：侧边栏精简

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 侧边栏隐藏 11 个专业/低频入口（工具/MCP/ACP/心跳/环境变量/安全/Token消耗/备份/语音转写/调试/插件管理），路由保留 | 非技术客户精简界面 | 5103c4bd | console/src/layouts/registry/builtinMenu.test.ts |
| 侧边栏左下角逐增额度进度条（仅百分比，低额度变红）+ provisioning /api/quota + 后端代理 /api/console/quota；数值=剩余÷签发额（clamp 0-100） | 客户对剩余额度无感知 | 8458ddfe | test_provision_server.py +3 / test_quota_router.py +3 / QuotaBar.test.tsx +3 |

关联计划：`docs/superpowers/plans/2026-08-24-go-claw-sidebar-quota.md`

## 2026-08-25 · 产品迭代：界面精简第 2 轮 + 模型可用性

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 隐藏侧边栏"运行配置"入口（同第一轮机制） | 非技术客户精简界面 | 82ada36c | builtinMenu.test.ts |
| 隐藏对话下方 Loop 模式选择器，固定默认模式 | 客户无需理解模式 | 82ada36c | 前端全套件 |
| 额度条去掉悬停金额 tooltip，只留进度条+百分比 | 用户要求 | 82ada36c | QuotaBar.test.tsx |
| 模型选择器：跨 provider 按 id 去重 + GO CLAW 可用模型白名单（deepseek-v4-pro/v4-flash/qwen3.7-max/qwen3.7-plus/glm-5.2/qwen3.6-flash/qwen3.8-max）+ 移除 FREE 页签 | 重复选项、不可用选项必 503 | 82ada36c | ModelSelector.test.tsx 12 例 |
| 空响应根治：取消路径改发 turn_interrupted 错误信封（"本轮对话已停止"） | cancel 产出 Completed+空 output 与空成功无法区分 | 82ada36c | envelope 既有测试 + retry_chat_model 测试 |
| extra_models 追加去重结论：has_model 已覆盖目录+extra，现有逻辑天然去重，无需改动 | 评估后关闭 | — | — |

## 2026-08-25 · 审查修复批次（全项目 review 后）

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 交付模型默认改 `deepseek-v4-flash`（服务器 .env + provision_server 默认值 + .env.example + 文档） | 交付模型须在白名单内，解决选择器空列表风险 | 9b8c6750 | 服务器已重启生效 |
| 模型白名单零命中兜底（回退去重后全量）+ 去重时已配置 provider 优先 | H1 解耦兜底 / H2 顺序隐患 | 9b8c6750 | ModelSelector.test.tsx |
| 额度语义：`granted = 剩余 + 累计净消耗`（NewAPI 数据恒等式，严格覆盖充值；弃用初版 max(签发,剩余) 近似） | 进度条严格反映 New API 实际额度 | 61647c04 | test_provision_server.py（含 quota_data）+ 服务器实测 granted=$8.00/percent=76（已部署） |
| 微信扫码仅首次配置时强制 enabled | 不覆盖既有用户的启用选择；表单其它字段随提交保存 | 9b8c6750 | ChannelDrawer 逻辑审查 |
| runtime 注释与实现对齐、额度条瞬态失败防闪烁、simple 白名单清理、删除 LoopInput 死代码 | 卫生 | 9b8c6750 | tsc + 前端 1203 全量 |
| 在线更新计划并入 11 条审查修正（白名单打包防凭证泄露、portable.json 兼容、自装路径改道、三处密钥一致、缓存迁移、回滚独立通道、/D= 安全拼接、发布架构、安装锁、国内镜像、CI 共存） | review 抓出的硬伤/泄露风险 | — | docs/superpowers/plans/2026-08-25-go-claw-online-update.md 第六节 |

## 2026-08-26 · 在线更新系统实施

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 在线更新全链路：后端 Python 编排（go_claw_updates.py + /api/updates/* 路由 + 6h 定时检测）、minisign/Ed25519 验签、NSIS 更新包（白名单+备份+锁+自动重启）、CI 构建/签名/manifest/发布、前端版本区块（检查/下载/一键安装/历史回滚）、公钥随包分发 | 客户一键更新到新版本 | 58b5fbe8 | test_go_claw_updates.py（验签往返+篡改拒绝）、tsc、前端全量、pre-commit 全钩子 |
| Rust 侧：portable.json updates 字段（serde default 兼容）、便携放行、安装 /D= raw_arg 安全拼接、缓存迁便携根、install_update_from_url 回滚命令 | 便携模式兼容 | 58b5fbe8 | cargo check |
| 修正：更新编排从 Rust 改为 Python（便携浏览器模式无 Tauri IPC） | 架构事实 | — | — |
| D2 密钥落地：生成 GO CLAW 专用 Tauri 签名密钥，公钥同步到代码/GitHub Variable/入包链，私钥非空口令加密并做跨磁盘备份；Python 验签兼容 Tauri CLI 的 Base64 minisign 文本格式 | 建立可恢复的密钥保管制度，并修正真实 CI 产物的验签格式断层 | 2f0ab644 | 本地 Tauri 签名探针 + `test_go_claw_updates.py` | `docs/GO-CLAW-在线更新签名密钥运维.zh.md` |

## 2026-08-31 · v2.1.0 在线更新事故与 v2.1.1 修复

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| NSIS 在 `.onInit` 立即把 cwd 切到 `updates`；Python Popen 同时显式使用缓存目录 cwd | v2.0.1 后端和更新器共同继承 `binaries/qwenpaw-backend` cwd，更新器自行锁住待备份的 `binaries` | `5921dc41` | U 盘 `stage=backup:binaries` + 30 秒重试时间线；Python/NSIS 合同测试 |
| 回滚逐项检查，回滚失败保留 `installing.lock`；Tauri 在启动后端前拦截未完成更新；记录无敏感信息的安装阶段日志 | 禁止失败恢复产生新旧混合版本后仍自动启动 | `5921dc41` | NSIS 静态事务合同 + Rust 锁测试 + Windows run `33369481282` |
| 生产 NSIS + 极小 probe payload 的 Windows 成功/目录锁回滚/自动重启测试加入签名前 CI | 原测试只检查脚本文本，未真实执行 NSIS；明确覆盖更新器继承 backend cwd | `5921dc41`, `50a1460b` | `scripts/verify/test_portable_update.ps1`；Windows run `33369481282` 通过 |
| 版本升级为 v2.1.1；发布只允许 draft 且禁止覆盖同名资产 | v2.1.0 的 tag 与后来 `--clobber` 覆盖的资产来源不一致 | `5921dc41` | release workflow 合同测试 |
| staging 启动器先结束旧单实例，再注入 v2.1.1 endpoint 并从绝对路径启动 EXE | 旧托盘实例保留生产 endpoint，导致第二次启动被单实例转发后仍只看到 v2.1.0 | `77f7916e` | `test_portable_staging_launcher.py` + 更新脚本合同共 13 例；仅验证启动合同 |
| 建立 Windows 新机在线更新事故交接，记录分支/提交/CI/staging/运行时合同、未决假设和失败后最小取证流程 | 完整 staging 包再次实机失败，必须消除聊天上下文依赖并区分 probe 通过与真实更新失败 | `e5877f87` | 路径/URL/提交/CI/服务器 SHA 只读复核；Markdown 与仓库合同检查 | `docs/GO-CLAW-v2.1.1-Windows在线更新调试交接.zh.md` |

## 2026-09-02 · 维护规则、运行时序与仓库边界

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 新增根级维护规则，固定干净样本、按首个失败 stage 单点修复、便携盘安全、发布门禁和 GO CLAW 唯一可写仓库 | 将连续调试中形成的有效做法变成后续执行者默认规则，并阻止误向 QwenPaw 源仓库写入 | `92be9d0` | 维护合同、pre-commit、正式 Windows 构建门禁 | `AGENTS.md`、`GO-CLAW-运行时序与维护规则.zh.md` |
| 固化启动、产品就绪、更新成功、完整回滚和不完整回滚五张 Mermaid 时序图，并以可执行合同检查真实代码顺序 | 防止文档顺序与 Python/Rust/NSIS 实现漂移，避免只验证 HTTP 启动而漏掉员工、插件或额度未就绪 | `92be9d0` | `test_go_claw_maintenance_contract.py`；合同脚本直接通过 | `GO-CLAW-运行时序与维护规则.zh.md` |

## 2026-09-03 · 算力充值功能开发（默认关闭）

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 冻结 ￥1–￥100,000、￥1=500万展示算力、1分=750 NewAPI 单位的整数合同；新增 OpenAPI、事件 Schema、PostgreSQL 账本 SQL 和服务条款模板 | 防止人民币、展示算力与 NewAPI 内部单位混用，并为支付/退款/审计建立可机器验证边界 | 待本变更提交 | OpenAPI/JSON Schema/PostgreSQL parser 合同 | `contracts/compute-recharge/*`、算力充值设计与实施计划 |
| 新增默认关闭的 Billing Service 骨架、存量 challenge/proof enrollment、本机凭据隐藏代理、侧边栏充值页、本地微信二维码和额度即时刷新事件 | 让 v2.0.1/v2.1.1 存量用户未来可无感开通，同时保证计费故障不影响原产品能力 | 待本变更提交 | 金额/账本/幂等/凭据隔离/兼容/前端合同测试；生产模式在耐久仓储完成前 fail closed | `GO-CLAW-运行时序与维护规则.zh.md` |

## 2026-09-01 · v2.1.1 新盘额度与媒体工具 P0

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 捆绑图片/视频插件版本提升并允许 v2.1.1 host；启动时原子升级旧 manifest；恢复预置员工和缺失 workspace；迁移遇到不可读旧 profile 时跳过并交由内置恢复流程重建 | 正式 v2.1.1 中旧插件兼容上限为 2.1.0，两个员工 workspace 还可能损坏或缺失；旧 profile 损坏不得中断后续恢复 | `5bec4dc`、`0b7ded0`、`250843d`、`fb50f05`、`512ba07` | 插件/员工单测；G、F 盘 `/api/plugins` 均确认两个插件 loaded/enabled，五个员工 running；完整 Tests run `33497130435` 通过 | `GO-CLAW-项目事实与发布基线.zh.md` |
| Main Full ZIP 从静态 `credentials.json` 改为唯一 `provision.json`；manifest 升级 schema 3；打包和发布 verifier 禁止混装/静态凭据并校验 provisioning 哈希 | 新空盘没有 `instance.id`，额度接口不可用；共享静态 token 也违背每实例额度合同 | `565cd13` | 打包、Full ZIP、发布合同、桌面额度验证共 54 项针对性测试 | `go-claw-auto-provisioning.zh.md` |
| Windows portable CI 新增 `/api/console/quota` 运行门禁；构建期七模型 key 只做预检，不再写入客户包；临时 provisioning 源在组包后清理 | 旧 CI 只验证文件结构和应用启动，无法发现新盘缺额度条 | `565cd13` | 54 项针对性测试通过；最终代码头 `512ba07` 的 Windows Full run `33497201586` 成功，artifact ID `9797474948`，额度/媒体插件/五员工/三档模型门禁均 PASS | `GO-CLAW-项目事实与发布基线.zh.md` |

## 2026-08-26 · v2.1 四计划现场 review 与事实基线

| 改动 | 原因 | commit | 验证 | 关联文档 |
| --- | --- | --- | --- | --- |
| 建立当前项目事实/发布基线，记录生产服务器、New API revision/digest、真实网关、签名状态、GitHub/CI 和更新镜像现状 | 防止把旧聊天、计划目标或另一台网关误当成生产事实 | `5ac46580` | SSH/Nginx/Docker/SQLite/GitHub/HTTP 只读复核；现有 updater 私钥签名后由项目 verifier 验证通过 | `docs/GO-CLAW-项目事实与发布基线.zh.md` |
| 四份原计划统一受一份 review 后总执行计划约束；修正员工页模型泄漏、重复签名密钥、后端失败错误回退和更新镜像等问题 | 原计划之间存在可导致模型泄漏、更新验签分叉和不可用启动的合同冲突 | `5ac46580` | 文档交叉检查、路径/route/symbol 复核、服务器只读核对 | `docs/superpowers/plans/2026-08-26-go-claw-v2-1-reviewed-execution-plan.md` |
| 按用户确认的最小实施原则修订 v2.1 计划：Full ZIP 保留本地低额度 API key；取消激活/ticket/provisioning v2；媒体只替换 Token Plan 模型和中性名称 | 前一版 review 将未证实风险扩展成了新开户系统、新媒体渠道和 New API 私有补丁，与已工作链路及产品体验冲突 | `5c247e89` | 现有插件 URL/body/轮询代码复核；计划冲突扫描；`git diff --check` | `docs/superpowers/plans/2026-08-26-go-claw-v2-1-reviewed-execution-plan.md`、`docs/superpowers/plans/2026-08-26-go-claw-token-plan-media-plan.md` |
| 媒体插件改为中性工具名并固定 Token Plan 目标模型；移除工具级 key/endpoint/model 和自动模型回退；保留现有 New API 请求体 | 收敛客户界面和模型选择，不改变客户端协议 | `cf6b0597`, `e2490713` | 媒体/迁移/客户合同相关测试 223 例 | 同上 |
| 真实媒体调用推翻“只增加模型名即可”的现场假设：新模型挂在 OpenAI 文字渠道会返回 400 `url error`，旧插件实际由独立 `type=17` 阿里渠道承载 | 防止把 `/v1/models` 可见性误判为媒体协议可用 | `9546eebb` | 服务器 SQLite 只读核对；New API 与上游各一次图片调用；New API 一次视频调用；阿里云 Token Plan 官方媒体接口文档 | `docs/GO-CLAW-项目事实与发布基线.zh.md` |
| 经用户授权新增 Token Plan `type=17` 媒体渠道 3；在不修改 New API 镜像的前提下，插件通过 `metadata.input.media` / `metadata.parameters` 适配固定 Ali task adaptor | 保持客户端 New API 公开 endpoint 不变，让五项媒体能力全部进入 Token Plan | `753a8646` | 数据库备份完整性 `ok`；图片生成/编辑、文生/图生/参考图生视频五项真实调用成功；相关单测 146 例 | `docs/GO-CLAW-项目事实与发布基线.zh.md`、媒体分计划 |
| 签名规则 fail-closed、规范 Full ZIP assembler、真实字节验签和唯一公开发布路径 | 确保 Main Build 产出一个可冷启动完整包，且机密 Full ZIP 不进入公开 Release | `85b5c062`, `5677a17c`, `e02e9f67`, `7172a224`, `fdfed0db` | assembler/签名/发布策略单测，Actionlint | release signing plan |

## 运营侧变更（非代码，无 commit）

| 日期 | 变更 | 原因 |
|------|------|------|
| 08-20 | New API 渠道 #1 上游 TokenPlan 周配额耗尽（08-24 04:07 UTC 重置）；`deepseek-v4-flash` 模型名与渠道 `deepseek-v4-flash-0731` 不匹配 | 供应商侧，待续费/补模型名 |
| 08-21 | 4 个存量 `go-claw-auto` 令牌 DB 直改 `unlimited_quota=1`；管理员 access token 过期导致 provisioning 502，已同步 `.env` 并重启服务；仓库转 public 用免费 Actions 额度 | 现场修复 |
| 08-26 | 备份 `one-api.db` 后通过 New API 管理 API 新增渠道 3 `阿里百炼_TokenPlan_媒体`；备份位于 `/opt/new-api/data/backups/one-api-before-token-plan-media-20260826T145110Z.db` | 将 Token Plan 原生媒体请求与文字 compatible-mode 分离，现有渠道未修改 |
| 08-26 | 创建七模型限定、非无限额度的交付令牌 ID 29，并不经本地输出直接更新 GitHub Secret `GO_CLAW_DASHSCOPE_API_KEY`；备份为 `/opt/new-api/data/backups/one-api-before-main-delivery-token-20260826T153608Z.db` | 为 Main Full ZIP 使用用户已接受的本地低额度 API key，不引入激活系统 |
| 08-26 | 在 8443 Nginx server 增加 `/updates/` 静态 location，配置备份为 `newapi-8443.conf.before-updates-20260826`，`nginx -t`/reload 通过；生产软链尚未切换 | 为后续原子发布更新资产建立独立静态入口 |
| 08-28 | 发布 GitHub Release `v2.1.0`（固定 `f6732aa`，仅四个在线更新资产）；服务器落盘 `/srv/go-claw-updates/releases/2.1.0`，完成 Actions digest、SHA-256、Ed25519 验证后原子切换 `updates -> releases/2.1.0`；公网 manifest 200，更新文件 Range/MZ/长度合同通过 | 开放已安装 v2.0.1 到 v2.1.0 的线上更新检查与下载链；真实 Windows 安装/重启/数据保留验收由用户完成 |
| 08-31 | 新增隔离 `/updates-staging/2.1.1/`，部署 run `33369481282` 的完整更新包、manifest 和测试启动器；生产软链保持 `releases/2.1.0-a9ab44b`；用户完整包实测仍失败，事故保持开放 | 在不影响生产的前提下复现 v2.1.1；实际失败说明 CI 小型 probe 不能作为发布结论 |
| 09-01 | 在当天新拷贝的 G、F 空产品盘分别复现额度条缺失和媒体工具不可用；每块盘先备份旧凭据 marker/插件 manifest，再补入受信 provisioning 配置并提升插件兼容范围；重启后额度接口 200、媒体插件加载、五个员工运行。F 盘备份位于 `F:\backups\P0-local-repair-20260901-171414` | 立即恢复现场产品盘，同时保留可回滚证据；生产更新源未修改 |
| 09-05 | 只读复核 Billing 公网/本机 readiness、systemd、Nginx 和用户已支付的最新 ￥1 订单；订单为 `PAID/APPLIED`，支付/额度 journal、CREDIT adjustment、已处理回调各唯一，双分录按资产平衡，无退款或未解决对账项；F 盘计费 profile 仅核对 schema/字段存在性 | 将此前真实支付从口头结果升级为脱敏的客户端与服务端证据；未发起新支付、未写服务端或生产更新源 |
| 09-05 | 正式签名 Main Build run `33947367539` 成功；F 独立目录从 2.0.1 完成 v2.1.2 A/B `COMMITTED`、自动重启和旧身份/聊天/额度保留；五员工、三档模型、真实 PNG/MP4 生成、交付产物及中文附件上传通过；GitHub `v2.1.2` 提升为 latest | 用真实 U 盘、真实签名包和真实媒体调用关闭“仅结构/仅注册”证据缺口；生产在线更新镜像仍为 2.1.1，故障诱发自动回滚作为开放全量更新前门禁 |
| 08-25 | deepseek-v4-flash 不可用三层修复：渠道 #1 models 名单补名 + `abilities` 表补路由行 + `options.ModelRatio` 补定价 0.25 + `model_mapping` 映射到 deepseek-v4-flash-0731（上游只认带日期型号）；实测 chat completion 200 | 模型选择器调用必 503 |
| 08-25 | provisioning 服务器 `CHAT_MODEL_ID` 由 qwen3.7-plus 改为 `deepseek-v4-flash` 并重启；服务端 quota 语义更新已部署 | 交付模型与白名单对齐 / 充值语义 |

---

## 文档索引（唯一索引，新增文档必须登记）

| 文档 | 角色 |
|------|------|
| 本文件 | 已发生变更的唯一历史记录 |
| `GO-CLAW-项目事实与发布基线.zh.md` | 当前代码、生产部署、GitHub/CI、签名和发布门禁的权威基线 |
| `GO-CLAW-文档规范.zh.md` | 文档编写与维护规则 |
| `GO-CLAW-运行时序与维护规则.zh.md` | 启动、产品就绪、更新和回滚顺序的唯一人类可读合同 |
| `go-claw-auto-provisioning.zh.md` | 开通/计费专题（持续更新） |
| `GO-CLAW-在线更新签名密钥运维.zh.md` | 更新签名密钥的保管、发布前检查、恢复与轮换规则 |
| `GO-CLAW-v2.1.1-Windows在线更新调试交接.zh.md` | 未解决的 v2.0.1 → v2.1.1 Windows 在线更新事故接手、取证和验收入口 |
| `superpowers/specs/*`、`plans/*` | 设计规格与实施计划（带状态标记） |
| `contracts/compute-recharge/*` | 算力充值 API、事件、账本与服务条款合同 |
| `superpowers/specs/2026-09-03-go-claw-v2-1-2-design.md` | v2.1.2 已确认视觉、技术目标与 UP/DL 时序（待实施） |
| `superpowers/plans/2026-09-03-go-claw-v2-1-2-implementation-plan.md` | v2.1.2 逐文件实施顺序、附件核查与发布验收门禁 |
| `contracts/v2.1.2/README.zh-CN.md` | 更新状态/签名/事务、交付物 API/安全/持久化与旧版本兼容的目标合同 |
| `contracts/update-v2/README.zh-CN.md` | 组件更新机器 schema、本地纯构建工具、签名验证与后续接线边界 |
| `incidents/2026-09-03-chat-attachments-utf8-investigation.zh.md` | 附件 UTF-8 报告的有限证据、未覆盖项与条件修复规则 |
| 工作区 `GO-CLAW-debug计划.md`、`GO-CLAW-修改计划.md` | 现场排查原始记录（快照，不再更新） |

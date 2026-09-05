# GO CLAW v2.1.2 目标合同

日期：2026-09-04
状态：发布候选验收中，**不是已上线 API**。机器 schema/fixture、分包签名链、更新状态/动作/SSE、
签名历史目录、Bridge、统一前端和交付物均已完成代码接线。尚无生产发布或完整设备验收结论。
上层：[设计](../../superpowers/specs/2026-09-03-go-claw-v2-1-2-design.md) ·
[逐文件实施计划](../../superpowers/plans/2026-09-03-go-claw-v2-1-2-implementation-plan.md)

本文的“必须”是验收约束。现行运行顺序仍以 [运行合同](../../GO-CLAW-运行时序与维护规则.zh.md)
为准；不能通过修改本设计提前绕过安装锁。支付商业合同仍由 [充值合同包](../compute-recharge/README.zh-CN.md)
管理，本合同只约束跨版本兼容。

## 1. 已有与目标边界

| 子系统 | 已有代码事实 | v2.1.2 目标 |
| --- | --- | --- |
| 更新 | `/api/updates/status/check/download/install/install-version/releases`；完整 EXE | 路径保留，新增可选目标绑定、v2 状态及 SSE；组件 A/B 引擎 |
| 版本 UI | DesktopUpdateProvider；UpdateSection 自行轮询；Header 有旧提示 | UpdateContext 唯一来源；齿轮/检查按钮提示，版本号无点 |
| 技能 | `?view=market` / MarketPanel | 增加 Banner，不新增安装 API |
| 交付物 | 工具消息可返回本地文件，无逐轮交付清单 API | 新增 ID 化登记/查询/打开/预览，旧消息结构不变 |
| 附件 | FormData → bytes 落盘 → preview → content URL → 模型 | 保持现有协议；按真实失败 stage 决定是否最小修复 |
| 充值 | 当前分支有本机代理/客户端/Billing 代码 | 保留 account 与账本；生产启用状态另查证，不由此表推断 |

所有新写 API 沿用本机认证，额外校验 Host/Origin，拒绝非预期跨站请求；不把 `X-Agent-Id` 或客户端
`chatId/user_id` 当作授权凭据。浏览器只访问本机同源 API，不接收更新签名私钥、支付 token 或管理密钥。

## 2. UP 合同：发布与本机更新

### UP-C1 签名、组件和路径

- index 的原始 UTF-8 字节、release manifest 原始字节、每个组件压缩包、Bridge 均使用既有 GO CLAW
  公钥链验签；验证字节后才解析 JSON，不先反序列化再重新编码验签。未知算法/主 schema 拒绝。
- index 含 schemaVersion、version、buildCommit、platform、channel、minUpdaterVersion、组件摘要摘要表、
  fullBytes、releaseManifest 引用、legacyBridge 引用。后台 check 不下载逐文件清单，不 hash 活动树。
- manifest 含 files（relativePath/sizeBytes/sha256/component/mount）、components
  （id/archiveUrl/archiveBytes/unpackedBytes/sha256/signature/contentDigest）、deleteFiles、
  minFreeBytes、readinessVersion、entrypointId。entrypointId 只能选择内置的启动实现，不能携带 shell 命令。
- component 固定为 desktop-shell/backend-core/backend-heavy-runtime/python-runtime/node-runtime/
  bundled-plugins/product-docs；contentDigest 对规范化、稳定排序的文件清单计算，不含构建时间戳。
- mount 仅允许 `slot`、`bootstrap`、`root-docs`，实际根由本机程序确定，不接受 manifest 任意绝对目录。
  程序文件恰好归属一个组件；分包不得同时包含同一 PyInstaller 依赖或插件种子。
- archiveUrl 只允许受信发布 host 的 HTTPS；重定向逐跳检查，最多 3 跳，不允许 HTTPS 降级。下载长度、
  解压总量/文件数/单文件量与签名 manifest 一致；流式 SHA 与签名验证不读取整个大包到内存。
- 拒绝绝对路径、`..`、UNC、盘符、ADS、保留设备名、尾随点/空格、大小写重复路径、symlink/junction；
  解压前和实际创建时都检查。deleteFiles 只清理非活动目标槽位的程序文件，不能操作 mutable 根。
- `data/secrets/logs/cache/backups/updates/GO-CLAW-Config/portable.json` 永不进入更新覆盖集合；
  Full ZIP 仍 provisioning-only，不含客户静态凭据、支付密钥或构建预检 key。
- 同一版本的已发布资产不可变。历史降级必须显式用户操作并匹配受信签名历史目录；普通 check 不自动降级。
- 旧 Bridge 内嵌确认目标的 version/manifest SHA，下载期即使 latest 已变化也只能安装该目标；
  不能让“下载了 v2.1.2 桥接器”实际安装另一个未确认版本。

### UP-C2 状态 DTO 与旧客户端映射

`GET /api/updates/status` 保留旧字段意义，新增字段如下；下面是目标 TypeScript 描述，不是现有代码：

```ts
interface UpdateStatusV2 {
  schemaVersion: 2;
  revision: number; // 每产品持久化递增，重启不归零
  enabled: boolean;
  currentVersion: string;
  phase: "idle" | "checking" | "available" | "downloading" |
         "downloaded" | "installing" | "failed"; // 旧 UI 合同
  enginePhase: "IDLE" | "CHECKING" | "AVAILABLE" | "PLANNING" |
    "DOWNLOADING" | "STAGED" | "SWITCH_PENDING" | "VERIFYING" |
    "COMMITTED" | "FAILED" | "ROLLING_BACK" | "ROLLED_BACK" | "BLOCKED";
  latest: {
    version: string;
    notes: string;
    pubDate: string;
    isNewer: boolean;
  } | null; // 保留旧 latest 结构；额外字段只做可选扩展
  targetManifestSha256: string | null;
  transactionId: string | null;
  activeSlot: "legacy" | "A" | "B";
  targetSlot: "A" | "B" | null;
  changedComponents: string[];
  downloadBytes: number; // 本次计划实际网络字节；check 时可为保守估计
  fullBytes: number; // 同目标完整组件包网络字节总量
  estimateOnly: boolean;
  downloaded: number; // 已接收网络字节，不含本地复制
  total: number | null; // 未知时保留 null；确定后等于 downloadBytes
  progressPercent: number | null;
  installationStarted: boolean;
  notifyAvailable: boolean;
  error: string; // 保留旧无错时空串；只给脱敏人类可读说明
  failure: { code: string; stage: string; retryable: boolean } | null;
}
```

| 引擎状态 | 旧 phase | 橙点 | 单进度条 |
| --- | --- | --- | --- |
| IDLE / COMMITTED | idle | 无 | 未开始为空；本交易成功 100% |
| CHECKING | checking | 保留上一已确认提示，不因刷新闪烁 | 不重置已有交易 |
| AVAILABLE | available | 有 | 未开始为空 |
| PLANNING / DOWNLOADING | downloading | 有 | 0–90% |
| STAGED | downloaded | 有 | 90% |
| SWITCH_PENDING / VERIFYING | installing | 无 | 90–99% |
| ROLLING_BACK | installing | 无 | 保持最后进度，简短“恢复旧版本” |
| FAILED | failed | 安装前且仍有已确认更新则保留 | 保留末次值，不伪造完成 |
| ROLLED_BACK / BLOCKED | failed | 无；重新 check 后可重新提示 | 保留末次值及错误 |

`notifyAvailable` 是权威提示字段，统一 context 同时驱动两处橙点；版本号永不显示橙点。
`installationStarted` 仅在 engine 已持久化 SWITCH_PENDING 和 installing.lock 后变为 true，用户点击
安装或请求失败不能提前清点。STAGED 必须等待用户确认，不能自动切槽。

下载进度按已知网络字节映射 0–85%，目标树校验映射 85–90%；零网络字节时也需本地完整校验才能到
90%。安装按已完成持久化里程碑映射 90–99%，提交成功才到 100%。显示值同一 transaction 单调不减；
若本地复用失败追加下载，更新 total 但不倒退已显示进度。不存在虚假的按时间涨到 100%。

### UP-C3 动作、并发与恢复

| API | 目标请求 | 成功与兼容约束 |
| --- | --- | --- |
| POST check | 空 body | 200 最新状态；同产品同时一个检查；check 不改变活动交易目标 |
| POST download | 可选 `{targetVersion,targetManifestSha256}` | 200 状态；后台工作。旧空 body 固定最近一次已验签目标；没有目标则拒绝 |
| POST install | 可选 `{transactionId,targetManifestSha256}` | 200 状态；仅 STAGED 可接受。相同交易重复请求返回同状态，不再启动进程 |
| POST install-version | 保留 `{version,url,signature}` | 必须匹配已验签历史目录；不允许仅凭客户端 HTTPS URL 执行安装 |
| GET releases | 无 | 保留旧返回结构，目录必须验签 |
| GET events（新增） | `Last-Event-ID` 可选 | `text/event-stream`，event `update.status`，id=revision，data=完整状态 DTO |

新 API 错误使用适当 HTTP 状态加 `{error, failure:{code,stage,retryable}}`，不抛原始绝对路径：
404 updates_unavailable；409 UPDATE_BUSY/TARGET_CHANGED/NOT_STAGED；422 INVALID_TARGET；
502 NETWORK_FAILED；失败状态还可能含 SIGNATURE_INVALID/HASH_MISMATCH/DISK_SPACE_LOW/
UNSAFE_PATH/STOP_TIMEOUT/READINESS_FAILED/ROLLBACK_INCOMPLETE。签名/路径/未知 schema 不自动重试。

- 单产品独占交易；用户新请求不能抢占安装或回滚。锁含 transaction/PID/进程创建时间，不能仅凭 PID
  存在删除锁。跨产品不互相停止进程。
- 事务冻结 version、from/to slot、manifest 摘要、shell old/new 摘要、generation、已完成 stage、
  revision、下载摘要与失败原因；不写凭据/聊天内容。每次 flush 后再报告进度，保留前一有效 journal。
- 检查总超时 15s；下载连接 15s、无进展 60s，瞬态失败最多 3 次退避，超出预算进入可重试失败，
  不无限“加载中”。阶段总预算根据签名包大小配置且有上限。停止 30s、产品健康 180s、回滚 180s；
  不满足时明确首错 stage，不用“HTTP 能访问”替代产品就绪。
- 续传必须校验已缓存字节、服务器 Range/ETag 与冻结摘要；不支持时重下该组件。签名失败的缓存隔离，
  不污染已验证包。空间预检包含完整目标槽位、下载包、旧壳备份与安全余量；空间不足不删旧可用版本。
- SSE 15s 心跳，重连发最新完整快照；前端忽略旧 revision，断线退到 10s 轮询；页面隐藏降频，返回
  focus/online 合并刷新，不每个组件开一条连接。保留六小时后端检查权威，不自动下载。
- 切槽后不得同时运行新旧后端写 data；普通启动看到 installing.lock 必须拒绝。受信 engine 的恢复
  通道核验交易、进程映像和一次性挑战，transactionId/环境变量不是独立授权。断电时由同一 engine
  重新核验 journal/程序树再恢复，无法证明完整则 BLOCKED 并保留锁。
- lastKnownGood 不在健康确认前更新；根壳、指针、版本 metadata 均完整提交或恢复后才解除安装锁。
  对实际来源版本的数据兼容是回滚前提，包括 v2.0.1 Bridge 来源而不只 N/N-1；聊天/账本不得回滚成更新前快照。

### UP-C4 老用户数据保留：固定路径、禁止重置、复用验收

这是 UP-C3 既有安装/健康/恢复步骤内的约束，不新增状态、API、常驻任务或客户操作。

| 保留对象 | 升级与回滚的固定规则 | 执行位置 |
| --- | --- | --- |
| 产品数据根 | `root` 仍为根启动壳所在产品目录；只有 `program_root` 切换槽位。`QWENPAW_WORKING_DIR=root/data`、`QWENPAW_SECRET_DIR=root/secrets`、`QWENPAW_BACKUP_DIR=root/backups` 不随槽位变更 | 普通启动与引擎健康启动共享同一路径构造，常量数量的路径比较 |
| 聊天记录 | 沿用既有员工 workspace、`chats.json` 与 `sessions`，包括归档会话、正文和附件引用；不按版本重建员工 ID/会话映射，不扫描磁盘猜一个新数据根 | 既有配置加载与按需历史读取 |
| 身份与余额归属 | 保留 `data/instance.id`、导入 marker、`GO-CLAW-Config/credentials.json`、provider secrets 及已有 `.go-claw-billing.json`；新充值只扩展原账户能力 | 既有 provisioning/import/enrollment 的幂等分支 |

重插后按当前根壳位置解析相对路径，不把旧盘符当身份。已有自定义 workspace 仍按原配置解析，不因
本版默认目录变化而迁回默认位置。已确认的数据根错位属于本地配置错误，在会写入新空数据目录之前
拒绝该启动/切换并走原有恢复；这不等于对全部聊天逐文件检查。

如果必须改写旧格式，先备份**本次要改写的文件**再原子提交；无迁移则不额外复制聊天和媒体。迁移
必须兼容实际旧版本；确认可回退前不删除其映射或格式。正常停机复用既有保存流程，不把结束进程
误当作尚未保存消息已持久化。用户取消的未完成输出与已有已保存历史分开处理。

旧盘判定复用升级来源和初始化前已存在的凭据/导入/账本标记；不能只因 `instance.id` 缺失而判为新盘，
也不能因本轮 prepare 刚创建了空 data 目录就判为旧盘。异常处理仅限以下分支，不增加全盘探测：

- 正常旧身份：复用原实例、原 token；已有 billing profile 则跳过重复 enrollment，不重新 provisioning。
- 身份缺失/损坏但旧凭据仍在：保持凭据和损坏原件，不生成新用户/赠额、不静默替换 instance.id。
  复用现有 tokenFingerprint/challenge-proof 能够确认原绑定时才恢复；缺少原实例映射、共享 token
  归属不唯一或证明失败时，仅将新增充值初始化标为待恢复，原有聊天及可用凭据照常使用。
- 本来不可读的历史文件：保留原件并给出可定位错误，不通过写空 chats.json、重建员工或清零余额
  将错误伪装成成功。修复损坏数据是单独处理，不作为所有正常用户的新增升级步骤。

运行成本固定：不新增递归遍历/聊天摘要计算；不为无损检查新增远端调用或轮询。身份校验复用已有
初始化读取和服务端绑定验证，不在每次启动审计 NewAPI。原签名、程序树验签和安装锁门禁不削弱。
聊天内容与余额前后比对只作为现有升级/回滚用例的两项断言，测试细则见实施计划 §9.2。

## 3. DL 合同：交付产物

### DL-C1 轮次与持久化

每轮使用服务端分配且稳定的 turnId，对应实际 responseId；agentId/chatId 由认证后的服务器上下文
解析，不接受工具/客户端任意指派 owner。仅本轮成功的显式发布或被引用候选登记；不抓取自然语言
绝对路径、不扫描磁盘、不把输入附件当输出交付物。并行员工用 ContextVar 隔离，finally 必须 reset。

目标响应 metadata 增加可选 `goClawDeliverables`，不改变原 response/output/tool content：

```ts
interface DeliverablesEnvelope {
  schemaVersion: 1;
  agentId: string;
  chatId: string;
  turnId: string;
  responseId: string;
  revision: number;
  status: "ready" | "unavailable";
  items: Array<{
    id: string; // 随机不透明 ID；不是路径编码
    turnId: string;
    name: string;
    kind: "document" | "image" | "video" | "audio" | "archive" | "code" | "other";
    mimeType: string;
    sizeBytes: number;
    exists: boolean;
    directOpenAllowed: boolean;
    previewAllowed: boolean;
    previewKind: "image" | "video" | null;
    createdAt: string; // UTC RFC3339
  }>;
}
```

清单位于 `data/deliverables/<agent>/<chat>/<turn>.json`；ID 必须校验为服务端 ID，不能由 URL 段直接
拼路径。内部映射存 `rootKind + relativePath + size + modified/file identity`，不把绝对盘符持久化为
权威。同一轮同一规范文件去重，响应重放复用原 ID/revision。原子临时写→flush→replace；失败记录
脱敏 stage，回答仍正常完成，交付区为空且 status=unavailable。禁止后台偷偷重跑生成工具。

SSE 在提交清单后发 completed metadata；崩溃在清单提交后、SSE 前，历史查询可恢复。取消/失败/
超时轮次不 finalize 为 ready。metadata 是快照，历史由清单权威恢复；删除聊天清理映射与缓存，
归档保留；源文件不自动删除。旧聊天没有清单就是空列表，不能伪造历史产物。

### DL-C2 API

下列均为新增接口；响应 ID 到 chat/agent 的授权由后端查询，不因持有 ID 就放行。

| API | Body/参数 | 响应 |
| --- | --- | --- |
| POST `/api/console/deliverables/query` | `{chatId,responseIds:string[]}`，1–50 个 | 200 `{schemaVersion:1,turns:DeliverablesEnvelope[]}`；未知/无清单返回空项；越权统一 404 |
| POST `/api/console/deliverables/{artifact_id}/open` | `{action:"open"|"reveal"}` | 200 `{ok:true,action}` 仅代表系统调用已发起，不能保证外部应用已打开 |
| POST `/api/console/deliverables/{artifact_id}/media-ticket` | 无 body，认证且当前 chat 已授权 | 200 `{ticket,expiresAt}`；只授权该 artifact 的 thumbnail/content GET |
| GET `/api/console/deliverables/{artifact_id}/thumbnail` | artifact id；认证或受限媒体票据 | 200 受控栅格图；不得把远端 URL 当本地文件拉取 |
| GET `/api/console/deliverables/{artifact_id}/content` | artifact id；可带单 Range | 200/206 受控媒体流；416 无效 Range |

JS query/open 使用既有认证 header；媒体 DOM 标签使用随机短期票据（5 分钟），不泄漏长期 API token。
票据绑定本会话/员工/产物与读媒体用途，允许播放器多次 Range，不能用于 open/query/其他文件；即使
带票据也重新检查文件与授权。票据不落盘、不写日志，过期仅由已认证页面续签，退出/聊天删除即失效；
`Cache-Control: private, no-store` 和 `Referrer-Policy: no-referrer`，媒体页不能对外发送票据。

错误合同：401 AUTH_REQUIRED；404 ARTIFACT_NOT_FOUND（含越权）；410 FILE_MISSING；
409 FILE_CHANGED（文件身份/元数据变化，重新登记前不执行）；403 ACTION_DENIED；415 UNSUPPORTED_MEDIA；
416 RANGE_NOT_SATISFIABLE；500 OPEN_FAILED。body `{error:{code,message,retryable}}` 不含绝对路径。
旧主响应渲染器忽略新 metadata；新 UI 遇到旧后端 404 query 时隐藏交付区，不影响正文/附件。

### DL-C3 安全与性能

- 每次调用用当前 product/workspace 重新解析 relativePath。拒绝出根、软链接/junction、网络路径、
  设备文件/ADS 和目录；预览在安全打开句柄上流式读取并校验最终路径，降低检查后被替换风险。
- 复用现有敏感文件守卫并在登记和访问时各执行一次；凭据/密钥/内部账本等敏感文件不因文件位置、
  安全扩展名或工具显式发布而自动放行。新 API 不继承“允许 workspace 外预览”作为扩大允许根的许可。
- 系统 `open` 仅在 allowlist 文档/文本/音频/压缩包上可用，危险脚本/可执行/快捷方式直接拒绝。
  allowlist 不能仅靠扩展名；浏览器 UI 禁用不替代服务端判断。参数化 opener/Explorer，不拼 shell；
  定位仅打开允许根内文件的父目录。目录产物不进入本版。
- 原地改写/替换已登记文件默认 FILE_CHANGED，不无提示打开变化后的内容；清单不是不可变文件副本，
  不声称拥有字节级防篡改能力。UI 显示缺失/变化并停用按钮。
- 预览图片仅支持经 magic 验证的安全栅格格式；SVG/HTML 不 inline 执行。视频首版 MP4/WebM，浏览器
  不支持 codec 给“无法预览，可在文件夹中显示”。所有响应 nosniff、受控 MIME、inline 安全文件名。
- 视频支持一个 bytes Range，返回正确 Content-Range/Content-Length/Accept-Ranges；拒绝多 Range
  及越界。流断开释放句柄；不全量复制视频到 JS Blob。
- 缩略图默认最长边 512px、解码不超过 40MP、单任务超时 5s，解码子进程/worker 并发上限 2；
  视频只抽一帧，失败显示静态占位，不使聊天失败。缩略图缓存初始预算 256MiB，LRU 淘汰，位于
  `cache/deliverables`。超限原图拒绝预览但可安全定位。
- POSIX 0600；Windows 继承产品数据 ACL，exFAT 不保证多账户隔离；接口授权仍必须实施。
  不以隐藏本机路径声称可防御同 OS 用户任意进程。

## 4. UI 合同与测试 ID

| ID | 冻结要求 | 自动/实机断言 |
| --- | --- | --- |
| UI-UP-01 | 齿轮与检查按钮右上橙点，版本号无点 | 两点读同一 notifyAvailable；刷新/下载完成保留；实际安装开始消失 |
| UI-UP-02 | 既有弹出组件、单进度条 | 只一个 progressbar；STAGED 90%；旧 Bridge 独立接续，新页面恢复交易 |
| UI-SK-01 | 标题“从技能中获得专业能力”；副标题“从11万个技能中，找到效率最优解” | 一级技能页空/非空都显示；右端按钮“浏览技能”复用 market route |
| UI-DL-01 | 普通文件右侧一个“打开”拆分下拉按钮 | 文件夹操作在下拉；危险类型禁主按钮；默认最多 3 个普通文件 |
| UI-DL-02 | 图片/视频单行横向；hover/focus 暗罩与眼睛/文件夹 | 触控操作常驻；当前页预览，Esc 关闭及焦点恢复 |
| UI-DL-03 | 滚动指示条不参与布局 | 默认隐藏；hover/focus/滚动显示；最后滚动后 800ms 且不 hover/focus 时隐藏；固定绝对定位，显隐前后 bounding rect 一致 |

轨道不以媒体数量拉高页面，媒体只挂载可视项与相邻项；原生滚动条永久隐藏但轨道仍可键盘滚动，
覆盖层滑块可拖动，读写布局经 requestAnimationFrame 合并。插件 renderFn 即使不调用 fallback，也
必须由 host-owned append 显示一次交付区；不能把未知第三方 renderer 当作天然支持此区域。

## 5. AT 合同：附件与错误分类

已有 `/api/console/upload` 使用 multipart `file`。当前成功结果为 `url/file_name/size`，实测 url 是
绝对 Windows 路径；前端旧注释“filename only”不等于实际协议。修复路径处理时保持旧绝对路径、
存储名和预览 URL 的历史兼容，不能在本版突然全部改成 artifact ID；交付物 ID 是独立新接口。

原始媒体用 bytes 上传/落盘、rb 读给 formatter 或 provider；只对 JSON、URL 和 SSE 文本做 UTF-8。
提供商不支持图片/视频、上传超限、坏媒体、认证失败、非 JSON 错误页与文本编码错误必须区分。
不 `errors=ignore` 丢字节、不用多编码猜测掩盖协议错误。具体证据和 AT-01–06 定位见
[附件核查记录](../../incidents/2026-09-03-chat-attachments-utf8-investigation.zh.md)。

## 6. BILL 兼容合同

充值仍走原本机 `/api/console/recharge/*`，客户端整数元输入；服务端整数分、原换算和账本幂等键不变。
1–100000 元、10/50/100/200 快填和“￥1 对应 500万算力”沿用已确认行为；不因更新改变已有订单的
换算快照。客户界面无退款发起入口，客服后台人工决定金额；删除的灰色限额/退款/开票说明不恢复。

升级/回滚/盘符变更保留 `data/.go-claw-billing.json`、实例与账户绑定，不能重复开户。Billing 不可达时
记录 degraded，聊天/员工/媒体不被连带关闭；支付到账不能仅凭微信 PAID，要查 quota credit 成功。
本机更新不回滚服务端账本，退款仍由原客服流程执行。对账只读优先；需要新真实扣款前通知用户。

原有余额包含此前赠送、充值及消费/退款后的剩余额度，不因本版才开始记充值账本而消失。权威余额
取自**同一个 NewAPI 用户**，不是新 billing ledger 的汇总初始值；绑定时已有 user/account 冲突必须
拒绝这次绑定，不覆盖原关系。网络失败只表示不可读取，不能写回 0、重新赠额或切换账户。

在既有 staging 对账中记录脱敏的账户关联与整数 quota：无消费/入账/退款时前后值相等；有并发业务
时按同一时间窗已落地的额度变更核对 `after = before + 净增加 - 净扣减`，不比较 UI 百分比，也不
把尚未到账的支付算作已增加。NewAPI 用户 ID 及原始 quota 只用于受控测试/后端，不返回客户前端。
这不增加运行期逐次“余额必须相等”的门禁；新充值绑定仍异步、超时仍沿用现有预算。

## 7. 时序与验收的追踪关系

| 设计时序 | 合同 | 计划任务 | 退出证据 |
| --- | --- | --- | --- |
| UP-01 下载 | UP-C1/2/3 | 1.1–1.3、2.1、2.4 | 目标冻结、只下变化包、旧实例仍可用、STAGED 不自动安装 |
| UP-02 安装 | UP-C2/3/4 | 2.2/2.3/2.5、3.1 | 实际安装清点、壳/槽位提交、原数据根保留、就绪后才解锁 |
| UP-03 回滚 | UP-C3/4 | 2.1/2.3/2.5 | 断电/启动失败后完整恢复；回滚不全锁保留；实际旧版本仍能读原数据 |
| DL-01 产物 | DL-C1/2 | 5.1/5.2 | 并发轮次隔离、完成仅一次、历史可重放 |
| DL-02 预览 | DL-C2/3、UI-DL | 5.2/5.3 | ID 授权、Range、危险文件拒绝、轨道零位移 |
| AT-01–06 核查链 | AT | 0.3、6A | 真图片/视频与错误路径矩阵，首错证据或未复现结论 |
| 充值原时序 | BILL 与充值合同包 | 0.1、6 | 微信/Billing/NewAPI/客户端四方一致，跨更新无重复账 |

新增机器 schema 和 fixture 后以同一命令验证服务端 JSON 与前端 decoder；本 README 不代替机器
验签、CI 或实机升级验收。任何未执行项保留未勾选状态。

2026-09-04 已新增 `update-status.schema.json`、`deliverables.schema.json` 与合成 fixture，
`test_v212_contracts.py` 验证结构、旧状态映射和未知主版本拒绝；尚未接入新 API 或前端 decoder。
构建合同、工具输入和剩余接线边界见 [组件发布机器合同](../update-v2/README.zh-CN.md)。

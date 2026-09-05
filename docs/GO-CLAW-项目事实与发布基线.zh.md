# GO CLAW 项目事实与发布基线

> 状态：当前有效。最后现场复核：2026-09-05（Asia/Shanghai）。
>
> 本文只记录“现在是什么”和“发布前必须成立什么”。历史变更见
> `GO-CLAW-变更台账.zh.md`，操作步骤见各专题文档，尚未实施的内容不得写成现状。

2026-09-05 开发态补充：`codex/v2.1.2` 已把产品唯一版本升到 2.1.2，并完成组件 A/B 引擎、
Bridge、双橙点更新 UI、技能 Banner、交付产物、附件 AT-03 修复和 draft Release 工作流的代码接线。
同日已完成一次本地**未签名** Main Full Build、完整 portable 结构检查和实际 full staging 的两次确定性
组件分包；RC 已在 F 盘新建隔离目录真实启动，未覆盖根产品或数据。真实签名资产、客户盘 A/B、
跨版本余额回读及全部五种媒体能力的本轮复验尚未完成。因此当前事实仍是“未发布、生产更新入口未切换”，
不能把源码版本、本地 RC 或自动测试解释为线上 v2.1.2 已可更新。

本地构建证据（不具备发布资格）：

- NSIS：`D:\GO-CLAW-v212-build-work\target-main-b\release\bundle\nsis\GO CLAW_2.1.2_x64-setup.exe`，
  622564466 字节，SHA-256 `261eda38833fa41e9bfb018a7f71beff1ea71de06b24b4994422d8b7f44cabcb`；
- Portable ZIP：`D:\GO-CLAW-v212-build-work\dist-main-0905b\GO-CLAW-Portable-2.1.2-Windows-x64.zip`，
  634905818 字节，SHA-256 `08b945378715f07f64abc482606554c22ad4df988793189c5894e5310a19f610`；
- ZIP 共 13264 个条目、解压后 1432526282 字节；壳、后端、独立更新引擎、Node/Python runtime、
  qwen-image/wan27 种子均存在，无路径穿越、`credentials.json`、`provision.json` 或私钥文件；
- 上述 EXE 的 Windows Authenticode 状态为 `NotSigned`；这与 Tauri updater/minisign 是两套独立机制。
  Authenticode 不是 v2.1.2 技术发布硬门禁，但本地构建未注入 Tauri 私钥、没有组成正式 sidecar/目录
  签名链，因此该批本地产物仍不得上传、发布或切换生产源；正式资产必须由已有 CI Tauri key 构建；
- `F:\GO-CLAW-v2.1.2-RC-0905` 为隔离副本，13264 个文件、1432526282 字节，8 个关键文件哈希
  与 D 盘 staging 一致；F 根目录现有 `data`、`secrets`、产品 EXE 和聊天记录未修改；
- 2026-09-05 实际启动后，壳/后端进程路径均归属该隔离目录，`/api/version` 为 2.1.2、
  `/api/healthz` 为 ok 且加载 5 个预置员工；`qwen-image-tool`、`wan27-tool` 均为
  `enabled=true/loaded=true`，日志确认 5 个 workspace 注入媒体工具，无异常栈；
- 浏览器真实页面确认版本、5 员工、算力充值入口及技能 Banner 的标题、副标题和右侧按钮。公共包按
  凭据边界不携带 `credentials.json`/`provision.json`，所以该隔离实例的额度为 404、模型档位为 503、
  充值显示初始化中；这证明未绑定态降级，不证明真实账号额度/provider 或支付调用通过；
- 经用户授权，临时复制 F 根产品的 credentials/provision 及最小 instance/billing 绑定文件并重启后，
  额度、模型档位、充值配置和余额四个接口均为 200；真实 UI 显示 41% 额度条、经济/均衡/高性能三档、
  `￥1对应500万算力`、10/50/100/200 快捷按钮、整数金额输入与历史账本。此绑定步骤未创建充值订单，
  未复制聊天记录或数据库；后续媒体验收另用专用构建探针令牌执行；
- 同时只读确认 v2 索引/目录及其签名四个生产 URL 均为 404，设置页因此显示 discover 阶段
  `DOWNLOAD_REJECTED`。本轮未修改生产更新源。

2026-09-05 GitHub 配置只读复核：`TAURI_SIGNING_PRIVATE_KEY`、
`TAURI_SIGNING_PRIVATE_KEY_PASSWORD` 已存在，`TAURI_UPDATER_PUBKEY` 与
`tauri.conf.json` 内置值完全一致；未读取私钥内容。GO CLAW OSS 的 endpoint/access-key secrets 与
bucket/public-base variables 尚未出现在仓库配置。Windows Authenticode 企业证书未接入 workflow，
沿用既有交付策略时不阻塞 v2.1.2；代价是 Windows 可能继续显示未知发布者/SmartScreen 提示，列为后续优化。

同日媒体真实调用：在已绑定隔离 RC 内调用 `generate_image` 一次，上游返回 token plan 周配额耗尽
（提示 2026-09-07 07:27 UTC 重置）；调用 `generate_video_from_text` 三次，均到达上游但返回当前分组
负载饱和 429。工具调用与 480P/1:1/3 秒参数传递成立，未产生 PNG/MP4；这是 provider 容量/额度阻塞，
不能写成端到端生成成功，也不是此前“工具未检测到”回归。调用后额度 UI/API 正常更新，无本地异常栈。

随后经用户授权建立 New API 媒体备用管线。变更前使用 SQLite backup API 创建
`/opt/new-api/data/backups/one-api-before-media-fallback-20260905T020257Z.db`，SHA-256 为
`768a3676332e8518b0059a099322310960ee1b2f539cb0adc2a3aefff60c7988`，文件/目录权限分别为
`600`/`700`，变更前后 `PRAGMA integrity_check` 均为 `ok`。当前四个产品媒体模型的拓扑固定为：
渠道 3 Token Plan（priority 10）作为主路，渠道 2 阿里 API 直连（priority 0）作为备用；渠道 1
只承担文字兼容协议，不再错误声明产品媒体模型；全局 `RetryTimes` 从 1 调整为 2。

同一专用构建探针令牌经 New API 公共接口完成真实故障转移：图片请求先由渠道 3 返回周配额 429，
日志记录 `use_channel=["3","2"]`，渠道 2 最终返回 HTTP 200 和有效图片；3 秒 480P/1:1 文生视频
同样记录 `重试：3->2`，提交后约 100 秒完成并返回有效 MP4。两项总计按 New API 账本计费
USD 0.611（图片 USD 0.080、视频 USD 0.531），只扣专用构建探针令牌，不改客户账本。未把 400、
504、524 强行映射为可重试，避免参数错误或长任务超时触发重复付费请求。配置前还通过渠道 2
直连生成过一张探测图片；该笔可能由阿里侧另行计费，不计入上述 New API USD 0.611 账本。

## 1. 权威性和冲突处理

2026-09-04 Windows 现场补充（仅本机，不更新下文生产服务器历史复核日期）：带更新器的
v2.0.1 候选基准在 D 盘 NTFS 完成历史 staging 477092325 字节包的下载、验签、安装及自动
重启；API/UI/版本标记均为 2.1.1，无安装锁/失败摘要，空聊天索引与身份文件摘要未变。但继承的
1.0.0 媒体插件因 `<2.1.0` 限制被禁用，模型档位 UI 仍显示加载中，**产品 readiness 不通过**。
原始无更新器的另一份 2.0.1 不能直接套用这项在线事务证明。
2026-09-05 00:01 补充：F exFAT 独立同基准也完成安装事务和自动重启，版本/程序哈希同 NTFS，
无安装锁/失败摘要、额度前后同值、身份/凭据摘要未变；同样媒体禁用、模型档位加载中。
两样本聊天索引原本均为空，尚不能证明非空历史消息/归档/附件可读。未修改 F 根目录现有产品。
详见 [本次现场](incidents/2026-09-04-v201-clean-sample-preflight.zh.md)。未关闭事故、未变更生产源。

2026-09-04 23:31 公共更新 HTTP 只读复核：`https://goclaw.host:8443/updates/latest.json`
现返回 **2.1.1**、pub_date `2026-09-01T09:43:12+08:00`，Windows URL 为
`https://goclaw.host:8443/updates/GO-CLAW-Update-2.1.1-setup.exe`，含签名。
下文生产 2.1.0/服务器软链描述是历史记录，不能再当成此 URL 的当前响应。此次没有 SSH 核对
软链或下载生产包，不能由 manifest 版本推断生产包内容/验收状态。正在实测的历史 staging
pub_date 为 `2026-08-31T16:09:38+08:00`、不同 URL；其故障不能直接归给现生产包。

当前状态的资料优先级固定为：

1. 本文中带验证日期的“已验证现状”；
2. 实际代码、GitHub 配置和服务器的同日只读复核结果；
3. 已上线系统的专题运维文档；
4. 已确认设计；
5. 实施计划；
6. 历史快照和聊天记录。

计划描述的是目标，不是事实。任何执行者发现代码、服务器或 GitHub 与本文不一致时，
必须先停止发布，重新核对并在同一变更中更新本文和台账；不得自行选择看起来更合理的
旧 URL、旧密钥路径或旧模型名继续实施。

## 2. 代码与发布仓库

| 项目 | 已验证现状 | 验证方式 |
| --- | --- | --- |
| 当前 P0 修复工作树 | `H:\2026\0811 GO Claw 2.0-hotfix-media-agents` | `git rev-parse --show-toplevel` |
| GitHub 仓库 | `GresonKwan/GO-Claw-2.0` | `gh repo view` |
| 唯一可写远端 | `origin` → `GresonKwan/GO-Claw-2.0` | `git remote -v` 与维护合同 |
| 产品基线 | QwenPaw v2.0.1，导入提交 `24813b3` | 变更台账和 Git 历史 |
| 本轮设计提交 | `ce18d02f` | `git show --stat ce18d02f` |
| 本轮四份原始计划提交 | `3fc3be19` | `git show --stat 3fc3be19` |
| 在线更新实现提交 | `58b5fbe8` | `git show --stat 58b5fbe8` |
| v2.1.1 调试分支 | `codex/portable-updater-v2-1-1` | 本地与 `origin` 均为 `77f7916e`（文档提交前） |
| v2.1.1 事务修复提交 | `5921dc41`、`50a1460b` | `git show --stat`、Windows run `33369481282` |
| staging 单实例启动器 | `77f7916e` | 13 项脚本合同测试；不代表安装成功 |
| v2.1.1 媒体/员工修复分支 | `codex/hotfix-v2-1-1-media-agents` | PR #4；媒体插件与员工恢复提交 `5bec4dc`，后续热修复稳健性至 `512ba07` |
| 新盘 provisioning 正式构建修复 | `565cd13`（正式构建代码头 `512ba07`） | 54 项针对性测试及完整 Tests run `33497130435` 通过；Windows Full run `33497201586` 成功 |

GO CLAW 是基于 QwenPaw 的独立二开。保留 `qwenpaw` 代码命名空间只为兼容，不表示仍向
QwenPaw 源项目贡献；不得在 `agentscope-ai/QwenPaw` 创建或更新 PR、Issue、分支、Tag、
Release，也不得向其推送本项目提交。

当前启动、产品就绪、更新和回滚顺序以 `GO-CLAW-运行时序与维护规则.zh.md` 及其可执行
合同为准。后续计划只能作为文件级任务明细，不得越过事实基线、运行合同和发布门禁。

## 3. 生产服务器和域名

| 项目 | 已验证现状 |
| --- | --- |
| 生产服务器 | `1.14.203.54` |
| SSH 用户 | `root` |
| 本机 SSH 私钥位置 | `C:\Users\Gemini the Z\Downloads\GoClaw0810.pem` |
| SSH 公钥指纹 | `SHA256:1ue8rpU83cufqgL97ohlvTyImZhndBSFBSlcsAMJuzI` |
| 产品域名 | `goclaw.host`，当前解析到 `1.14.203.54` |
| 客户 New API 基础地址 | `https://goclaw.host:8443/v1` |
| provisioning 公网地址 | `https://goclaw.host:8443/go-claw/provision` |
| provisioning 服务 | systemd `go-claw-provision.service`，监听 `127.0.0.1:9100` |
| provisioning 代码 | `/opt/go-claw-provisioning/provision_server.py` |

`https://api.tokenbyte.ai/v1` 不是 GO CLAW 当前生产网关：该域名解析到
`103.240.196.135`，现场测试令牌仅暴露两个模型，且不包含本轮要求的七个模型。它不得再
写入新交付凭据、CI 或新计划。历史凭据如仍指向该地址，只能作为待迁移状态处理。

Nginx 的已验证配置文件是：

- `/etc/nginx/conf.d/goclaw.conf`：80/443 的 `goclaw.host` 控制面；
- `/etc/nginx/conf.d/newapi-8443.conf`：8443 的 New API、provisioning 和额度代理。

## 4. New API 运行基线

| 项目 | 已验证现状 |
| --- | --- |
| 容器 | `new-api` |
| 上游版本 | `v1.0.0-rc.24` |
| 源码修订 | `5c3abffe8572aa8a49f15c3916707d2019d66af4` |
| 镜像 RepoDigest | `calciumion/new-api@sha256:be4b1f3fb48687cab0e0ff921a1e4c69ae3738c0907ce05646ddc6da02cb35a5` |
| 监听 | 宿主机 `127.0.0.1:3000` |
| 数据卷 | `/opt/new-api/data:/data` |
| SQLite | `/opt/new-api/data/one-api.db` |

### 4.1 渠道现状

- 渠道 1 `阿里百炼_TokenPlan_1` 是 OpenAI 类型，基础地址为
  `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode`。当前只承担文字/音频兼容协议，
  不再声明四个产品媒体模型；文字别名 `deepseek-v4-flash` 映射到
  `deepseek-v4-flash-0731`。
- 渠道 2 `阿里百炼_直连API_1` 是阿里类型的百炼直连备用渠道，地址为独立的 `aliyuncs.com`
  endpoint；当前挂载四个产品媒体模型，优先级为 0，并保留历史 Wan/Qwen Image 模型。
- 渠道 3 `阿里百炼_TokenPlan_媒体` 是经用户明确授权新增的阿里类型媒体渠道，基础地址为
  `https://token-plan.cn-beijing.maas.aliyuncs.com`，仅挂载本轮四个媒体模型，优先级为 10。
- 全局 `RetryTimes=2`。该固定版本遇到可重试的主路错误时会进入下一优先级；400、504、524
  保持默认不重试，不做宽泛状态码覆写。
- 现有 provisioning 签发的样本令牌可以从 `/v1/models` 看到本轮七个必需模型。

客户媒体插件仍只调用 New API 公开入口：图片使用 `/v1/images/generations`，视频使用
`/v1/video/generations` 提交和轮询。2026-08-26 的现场验证结论为：

- 旧图片/视频模型实际由渠道 2（`type=17` 的阿里类型直连渠道）承载，所以旧插件可用；
- 最初将新四个媒体模型只挂在渠道 1（`type=1`）时，图片和视频均不可用；
- 通过渠道 1 调用图片和视频均返回 HTTP 400 `url error`；绕过 New API 直接请求
  `compatible-mode/v1/images/generations` 仍返回相同错误；
- 阿里云 Token Plan 官方媒体合同是原生
  `/api/v1/services/aigc/multimodal-generation/generation`、
  `/api/v1/services/aigc/video-generation/video-synthesis` 和 `/api/v1/tasks/{task_id}`，
  不是文字 `compatible-mode` 路径。

用户后续明确授权尝试新增渠道。运维先用 SQLite backup API 生成
`/opt/new-api/data/backups/one-api-before-token-plan-media-20260826T145110Z.db`，再通过 New API 管理 API
新增渠道 3；渠道 1、2 均未修改。当前固定 New API `v1.0.0-rc.24` 不需要私有补丁：
其 Ali task adaptor 会将 `metadata.input.media` 和 `metadata.parameters` 还原为百炼原生请求。

2026-08-26 的五项真实验收全部通过：图片生成、图片编辑、文生视频、图生视频、参考图生视频当时均由
渠道 3 承载并返回有效媒体 URL。2026-09-05 在渠道 3 周额度耗尽现场新增上述渠道 2 备用管线，
并重新实测图片生成和文生视频的 `3->2` 故障转移成功；图片编辑、图生视频、参考图生视频共享相同
模型渠道拓扑，但本轮尚未重复产生对应付费样本。

### 4.2 唯一产品模型映射（内部）

| 客户标签/能力 | 内部传输模型 ID |
| --- | --- |
| 经济（默认） | `deepseek-v4-flash-0731` |
| 均衡 | `qwen3.7-plus` |
| 高性能 | `qwen3.8-max` |
| 图片生成、图片编辑 | `qwen-image-3.0-pro` |
| 文生视频 | `happyhorse-1.1-t2v` |
| 图生视频 | `happyhorse-1.1-i2v` |
| 参考图生视频 | `happyhorse-1.1-r2v` |

这些 ID 只允许出现在后端私有映射、媒体插件内部、New API 配置、测试和内部文档中。
客户前端、工具描述、员工提示词和公开产品 API 只使用中文产品标签。

## 5. 交付凭据和 provisioning 现状

客户端和服务端仍使用 schema 1：Full ZIP 内的 `provision.json` 携带 provisioning URL 和
共享 HMAC，客户端首次启动生成 `data/instance.id`，按实例换取低额度 New API 子令牌，再将
schema-1 `credentials.json` 原子写入产品盘并导入文字、媒体 provider。

正式 Main Build 合同为：

- CI 从既有 `GO_CLAW_PROVISION_URL` 和 `GO_CLAW_PROVISION_HMAC_SECRET` 生成唯一的
  `Portable/GO-CLAW-Config/provision.json`；
- Full ZIP 严禁包含任何 `credentials.json`，也严禁 provisioning 与静态凭据混装；
- `GO_CLAW_DASHSCOPE_API_KEY` 只用于构建期七模型预检，不进入客户包；
- Full ZIP manifest 使用 schema 3，记录 `containsCredentials=false`、
  `containsProvisioningConfig=true` 和 provisioning 配置 SHA-256；
- 便携运行验证必须确认 `/api/console/quota` 返回有效三字段额度合同，并确认两个媒体插件均已
  加载、启用；
- 在线更新 payload 不包含 `GO-CLAW-Config`，因此不覆盖客户已有 provisioning 配置或实例凭据。

### 5.1 算力充值状态

`codex/compute-recharge` 已按冻结合同落地本地凭据隔离、存量实例 challenge/proof enrollment、
同源充值代理、整数金额域模型、幂等订单、PostgreSQL 双分录账本、微信 Native 支付和前端入口。
代码默认仍为 fail-closed；生产实例由独立配置显式开启，不能把服务端已启用推断为尚未发布的
v2.1.2 客户端已经上线，也不授权修改生产更新源或公开 Release。

2026-09-05 只读复核：公网与 `127.0.0.1:9200` readiness 均为 HTTP 200；
`go-claw-billing.service` 为 active、主进程退出码 0、重启次数 0，Nginx 配置检查通过。用户此前
支付的最新一笔 ￥1 订单在服务端为 `PAID/APPLIED`，只有 1 个 CREDIT adjustment、1 个 APPLIED
adjustment、1 个 PAYMENT journal、1 个 QUOTA_CREDIT journal 和 1 个已处理回调；订单快照为
5,000,000 展示算力与 75,000 NewAPI quota unit，按资产汇总的 journal 差额为 0，无退款、无未解决
对账项。F 盘仅只读确认已有 schema 1 billing profile、账户/实例身份文件和 bearer token 字段，未
输出任何 ID 或 token，未为本次复核再次支付。

存量迁移只允许新增 `data/.go-claw-billing.json`，并复用已有 `instance_id → newapi_user_id`；
失败只影响充值入口，聊天记录、员工、模型、原 token/quota、额度条和在线更新不得变化。

共享 HMAC 会随 Full ZIP 分发，可以被提取，不能作为强身份凭证。这是 v2.1.1 明确接受的
限制；通过每实例低额度、模型白名单和服务端幂等控制影响面。本轮不实施 schema 2、激活码、
ticket DB 或客户 ZIP sealing。

## 6. 更新签名事实

更新密钥的保管路径、钥匙串条目、备份、Key ID 和轮换顺序只由
`GO-CLAW-在线更新签名密钥运维.zh.md` 维护，本文不复制密钥材料。

2026-08-26 已重新验证：

- 本地主私钥和跨磁盘备份都存在；
- 两份公钥都与 `console/src-tauri/tauri.conf.json` 完全一致；
- GitHub Variable `TAURI_UPDATER_PUBKEY` 与仓库公钥完全一致；
- 使用现有私钥签名临时文件，再经
  `src/qwenpaw/app/go_claw_updates.py::verify_minisign` 验证通过。

结论：本轮不生成新密钥、不改变公钥、不执行轮换。任何计划中出现的
`~/.config/go-claw/keys/updater-2026-08.key` 都是已否决路径。

CI 现已将 `TAURI_UPDATER_PUBKEY` 作为与仓库公钥的 fail-closed 相等性断言，
不再覆盖跟踪值。正式 Windows 构建缺少私钥、口令或公钥任一项时直接失败；
安装器和更新包在上传前均由项目 `verify_minisign` 对真实字节复验。

## 7. GitHub 与 CI 现状

### 7.1 已存在的设置

GitHub Secrets 已存在：

- `GO_CLAW_DASHSCOPE_API_KEY`；
- `GO_CLAW_PROVISION_HMAC_SECRET`；
- `GO_CLAW_PROVISION_URL`；
- `TAURI_SIGNING_PRIVATE_KEY`；
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`。

GitHub Variable `TAURI_UPDATER_PUBKEY` 已存在并与仓库公钥一致。

`GO_CLAW_LLM_API_KEY` 当前不存在，v2.1.1 不新增它。Main Build 使用已有
`GO_CLAW_DASHSCOPE_API_KEY` 请求 `https://goclaw.host:8443/v1/models` 做七模型预检，但不把该
key 写入 Full ZIP。客户盘首次启动后由 provisioning 服务签发独立低额度 token。本轮不新建
`GO_CLAW_CI_TEST_API_KEY` 或其他测试额度机制。

2026-08-26 已在 New API 创建专用交付令牌 ID 29（名称
`go-claw-main-v2.1-full`）：非无限额度，只允许本轮七个产品模型。创建前数据库备份为
`/opt/new-api/data/backups/one-api-before-main-delivery-token-20260826T153608Z.db`，完整性为 `ok`。
令牌值已直接写入现有 GitHub Secret `GO_CLAW_DASHSCOPE_API_KEY`，未输出到日志；
实测 `/v1/models` 七模型全部可见。该 Secret 现在仅作为构建期可用性探针，客户实例 token
由 provisioning 服务另行签发。

### 7.2 产物与发布现状

> **事故状态（2026-08-31，仍未解决）**：公开 `v2.1.0` 更新包不能完成 v2.0.1 的
> 原地更新；第一轮已确认因更新器继承 `binaries/qwenpaw-backend` 当前目录而自行锁住
> `binaries`，最终在 `stage=backup:binaries` 回滚。`v2.1.1` 已修复该已知原因并通过
> Windows 小型 probe 事务测试，但用户使用完整 staging 更新包再次实测仍然失败。本次失败
> 尚未取得安装阶段日志，原因未知；不得宣称 `v2.1.1` 已修复或让客户继续重试。完整接手资料见
> `GO-CLAW-v2.1.1-Windows在线更新调试交接.zh.md`。

> **新盘 Full ZIP P0（2026-09-01）**：当天新拷贝的 G、F 两块空产品盘均复现额度条缺失、
> 生图生视频工具不可用。现场证据显示旧 Full ZIP 携带共享 `credentials.json` 而没有
> `provision.json`/`data/instance.id`，同时两个媒体插件 manifest 的 host 上限停在 `2.1.0`。
> 两块盘均在备份后完成本地最小修复，并验证额度接口、两个媒体插件和五个员工恢复。
> 正式代码合同已改为 provisioning-only，并增加额度运行门禁；最终 Windows Full run
> [`33497201586`](https://github.com/GresonKwan/GO-Claw-2.0/actions/runs/33497201586)
> 已在代码头 `512ba07debd7ec027461f9a84fc06937dc40f9fe` 成功完成。
> 此 P0 与上方“v2.0.1 → v2.1.1 原地更新事务”是两个独立问题，不能互相作为关闭证据。

- Windows-only Main Build run `33059759882` 已对提交
  `f6732aa67e012a5f5b03048276ba05df1051ded9` 成功完成；客户 artifact
  `GO-CLAW-Windows-x64-Full-2.1.0` 内只有一个
  `GO-CLAW-Windows-x64-Full.zip`。CI 已通过便携 Tauri 内容就绪、离线 WebView2、
  Full ZIP 结构、SHA-256 和签名合同验证。
- GitHub Release [`v2.1.0`](https://github.com/GresonKwan/GO-Claw-2.0/releases/tag/v2.1.0)
  已于 2026-08-28 发布并设为 latest，固定到上述提交。公开 Release 只包含在线更新所需的
  `GO-CLAW-Update-2.1.0-setup.exe`、`.sig`、`latest.json` 和 `SHA256SUMS.txt`；
  不包含历史 Tauri Setup，也不包含带客户本地凭据的 Full ZIP。
- GitHub 记录的四个 Release asset SHA-256 digest 已与服务器原文件逐项比对一致；服务器另以
  包内公钥完成更新 exe 的 Ed25519 真实验签。
- 当前公开更新 exe 的 SHA-256 为
  `0ac1dc32c3a0321665394ef2905861cc1accd1e26eb811d8b671037ec1219ed0`；测试 U 盘
  缓存与该值一致，排除了旧缓存或下载损坏。
- `desktop-publish.yml` 历史上允许 `--clobber`，导致 `v2.1.0` tag 的 target SHA 与后来
  覆盖的资产构建 SHA 不再一一对应。v2.1.1 起，发布只允许向 draft 上传不存在的资产，
  已发布资产不可变。
- v2.1.1 Windows-only build run
  [`33369481282`](https://github.com/GresonKwan/GO-Claw-2.0/actions/runs/33369481282)
  在提交 `50a1460bb53106f7016c8f73950b13d7ecb1eb18` 上成功；它验证了完整构建和生产 NSIS
  的小型 probe，不是完整 v2.0.1 → v2.1.1 实机验收。
- v2.1.1 新盘 P0 最终代码头 `512ba07debd7ec027461f9a84fc06937dc40f9fe` 的完整 Tests run
  [`33497130435`](https://github.com/GresonKwan/GO-Claw-2.0/actions/runs/33497130435)
  成功，Windows、macOS、Ubuntu 的 unit/contract/integrated 矩阵全部通过。
- 同一代码头的 Windows Full run
  [`33497201586`](https://github.com/GresonKwan/GO-Claw-2.0/actions/runs/33497201586)
  成功；客户 artifact `GO-CLAW-Windows-x64-Full-2.1.1` 的 artifact ID 为
  `9797474948`，GitHub artifact digest 为
  `sha256:c88d734a7e1c3e2499c5819cb88918789100fb61a5c79df21816e5c1acbefe66`。
  运行日志确认五个员工和无 key 媒体工具、三档模型、两个媒体插件及实例额度合同均 PASS；
  最终 verifier 输出 `containsCredentials=false`、`containsProvisioningConfig=true`、
  `fullZipFiles=13910`、`signatureChecks=2`。
- staging 启动器提交 `77f7916e` 会先结束旧单实例，再注入测试 endpoint；它只消除旧
  v2.0.1 托盘进程继续使用生产 endpoint 的干扰，不修复安装事务。

GitHub Actions 下载 artifact 时会额外使用平台包装层；客户文件合同是该 artifact 内只包含
一个 `GO-CLAW-Windows-x64-Full.zip`。

## 8. 在线更新镜像现状

2026-08-26 已在 `/etc/nginx/conf.d/newapi-8443.conf` 的 8443 server 中、通配
`location /` 之前增加 `location ^~ /updates/`，静态根为 `/srv/go-claw-updates`。
原配置备份为 `/etc/nginx/conf.d/newapi-8443.conf.before-updates-20260826`；
`nginx -t` 和 reload 均成功。

2026-08-28 已将经 Actions artifact digest、内部 SHA-256 和 Ed25519 验签的更新资产落到
`/srv/go-claw-updates/releases/2.1.0`，并以同文件系统 rename 原子建立
`updates -> releases/2.1.0`。公网
`https://goclaw.host:8443/updates/latest.json` 当前返回 HTTP 200、
`application/json`、版本 `2.1.0`；更新 exe 支持 Range，请求 `0-1` 返回 `MZ`，总长度
线上文件当前长度为 `477008062`，但该包已确认存在上述 `backup:binaries` 缺陷。

生产镜像的 `latest.json` 下载 URL 固定为同域
`https://goclaw.host:8443/updates/GO-CLAW-Update-2.1.0-setup.exe`，避免国内客户端再跳转
GitHub 下载。v2.0.1 的 manifest 拉取没有开启 HTTP redirect，GitHub
`/releases/latest/download/latest.json` 回退会因 302 失败；在后续客户端修正前，
`goclaw.host` 主 endpoint 是已安装 v2.0.1 的必要更新入口，不得下线。

生产 `latest.json` 当前仍指向已知不可安装的 v2.1.0，切换到 v2.1.1 前不得再让用户重试。
v2.1.1 必须先在 Windows CI 真实执行生产 NSIS 的成功、回滚和自动重启事务，再用完整
v2.0.1 对 staging manifest 做一次升级验收；客户不得成为第一位端到端测试者。

2026-08-31 已建立隔离的 staging 路径：

- manifest：`https://goclaw.host:8443/updates-staging/2.1.1/latest.json`；
- update exe：`477092325` bytes，SHA-256
  `1e21ec0e485258513252f19128f09d114e1511e5029b21472f2ff5b6e63ef34d`；
- 测试启动器 ZIP：SHA-256
  `4afad8861d113c840257f5768e6e4aa24b16c9f354e99b0170ca433bcb7f0500`；
- 生产软链仍为 `/srv/go-claw-updates/releases/2.1.0-a9ab44b`，未切换。

上述 staging 的完整包再次实机失败，当前只能用于受控调试，不得推广。新 Windows 调试机
必须先按 `GO-CLAW-v2.1.1-Windows在线更新调试交接.zh.md` 保存失败现场，再决定下一处代码修改。

## 9. 发布不可变条件

正式 `v2.1.1` 修复版只有同时满足下列条件才可交付：

1. Tauri Auto 模式以 React 内容首帧为成功条件；WebView 失败只打开一次浏览器，后端失败
   显示明确故障页而不是打开一个同样不可用的浏览器。
2. 客户前端和其调用的产品 API 响应不出现 provider/model/base URL/API key。
3. 每个员工独立保存经济/均衡/高性能档位，新员工默认经济。
4. 五个媒体工具必须只调用 New API 产品入口；生产路由以 Token Plan 原生媒体渠道为主、阿里直连为
   备用。2026-09-05 图片生成和文生视频已实测 `3->2` 故障转移，另三项沿用同一渠道拓扑但发布前
   是否复验按当次媒体变更范围决定，不增加固定付费门槛。
5. Main Full ZIP 只包含唯一、规范的 `provision.json`，不包含任何静态 `credentials.json`、
   enrollment ticket 或签名私钥；共享 HMAC 的可提取局限已记录。首次启动必须生成
   `data/instance.id` 和实例凭据，`/api/console/quota` 返回 200 且额度字段有效。
6. 三处 updater 公钥一致，安装器和更新包均由现有私钥签名并经项目 verifier 复验。
7. `/updates/latest.json` 返回 `application/json`，文件、SHA-256、签名和 URL 相互一致。
8. Main Build 的客户 artifact 内恰好有一个完整 ZIP；在两类 Windows 终端完成 Tauri、
   浏览器回退和 WebView2 恢复验收。
9. 生产 NSIS 可执行事务测试证明：更新器即使从 `binaries/qwenpaw-backend` cwd 启动，也能
   完成备份、替换和自动重启；外部锁失败时完整回滚且没有混合版本。
10. `installing.lock` 只在成功或完整回滚后删除；回滚不完整时保留，并由 Tauri 在后端启动前
    拒绝运行。诊断只写 `version/stage/retries/restore`，不得写任何凭据。
11. GitHub tag、Release target、update exe、签名、manifest 和 SHA256SUMS 来自同一 build，
    已发布资产不得覆盖；生产镜像只在完整 v2.0.1 → v2.1.1 staging 验收后原子切换。
12. 完整 477MB 更新 payload 必须从干净 v2.0.1 样本分别在短路径 NTFS 和目标 U 盘完成
    下载、替换、自动重启和版本一致性验收；小型 CI probe 不能替代此项。
13. 两个捆绑媒体插件在 v2.1.1 host 上必须同时 `loaded=true`、`enabled=true`，内容生产员工
    必须暴露五个媒体工具；全新盘验证不能复用已有 `credentials.json` 或 `instance.id`。

## 10. 每次发布前的复核命令

以下命令只输出非秘密元数据；任何密钥内容均不得进入日志：

```bash
git status --short
git rev-parse HEAD
gh variable get TAURI_UPDATER_PUBKEY | shasum -a 256
gh secret list
curl --fail --silent --show-error https://goclaw.host:8443/updates/latest.json
ssh -i /Users/gresonkwan/Downloads/GoClaw0810.pem root@1.14.203.54 \
  "docker inspect new-api --format '{{.Config.Image}} {{index .Config.Labels \"org.opencontainers.image.revision\"}}'"
```

公钥输出允许用于一致性比较，但发布日志只应保留其 SHA-256 指纹。服务器配置、镜像 digest、
渠道模型和更新 URL 只要发生变化，就必须在同一变更中更新本文的验证日期和对应事实。

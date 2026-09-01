# GO CLAW 项目事实与发布基线

> 状态：当前有效。最后现场复核：2026-09-01（Asia/Shanghai）。
>
> 本文只记录“现在是什么”和“发布前必须成立什么”。历史变更见
> `GO-CLAW-变更台账.zh.md`，操作步骤见各专题文档，尚未实施的内容不得写成现状。

## 1. 权威性和冲突处理

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
| 产品基线 | QwenPaw v2.0.1，导入提交 `24813b3` | 变更台账和 Git 历史 |
| 本轮设计提交 | `ce18d02f` | `git show --stat ce18d02f` |
| 本轮四份原始计划提交 | `3fc3be19` | `git show --stat 3fc3be19` |
| 在线更新实现提交 | `58b5fbe8` | `git show --stat 58b5fbe8` |
| v2.1.1 调试分支 | `codex/portable-updater-v2-1-1` | 本地与 `origin` 均为 `77f7916e`（文档提交前） |
| v2.1.1 事务修复提交 | `5921dc41`、`50a1460b` | `git show --stat`、Windows run `33369481282` |
| staging 单实例启动器 | `77f7916e` | 13 项脚本合同测试；不代表安装成功 |
| v2.1.1 媒体/员工修复分支 | `codex/hotfix-v2-1-1-media-agents` | PR #4；媒体插件与员工恢复提交 `5bec4dc`，后续热修复稳健性至 `512ba07` |
| 新盘 provisioning 正式构建修复 | `565cd13`（正式构建代码头 `512ba07`） | 54 项针对性测试及完整 Tests run `33497130435` 通过；Windows Full run `33497201586` 成功 |

后续实施以本轮 review 后的总执行计划为唯一跨模块顺序；四份原始分计划只能作为文件级
任务明细使用，不得越过总计划中的前置门禁。

## 3. 生产服务器和域名

| 项目 | 已验证现状 |
| --- | --- |
| 生产服务器 | `1.14.203.54` |
| SSH 用户 | `root` |
| 本机 SSH 私钥位置 | `/Users/gresonkwan/Downloads/GoClaw0810.pem` |
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
  `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode`。当前已列出本轮
  三个文字模型和四个媒体模型；文字别名 `deepseek-v4-flash` 映射到
  `deepseek-v4-flash-0731`。
- 渠道 2 是阿里类型的历史百炼直连渠道，地址为独立的 `aliyuncs.com` endpoint，保留旧
  Wan/Qwen Image 模型。
- 渠道 3 `阿里百炼_TokenPlan_媒体` 是经用户明确授权新增的阿里类型媒体渠道，基础地址为
  `https://token-plan.cn-beijing.maas.aliyuncs.com`，仅挂载本轮四个媒体模型，优先级为 10。
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

五项真实验收全部通过：图片生成、图片编辑、文生视频、图生视频、参考图生视频均由
渠道 3 承载并返回有效媒体 URL，无旧模型自动回退。因此媒体发布门禁已解除。

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
4. 五个媒体工具均通过 New API 的 Token Plan 原生媒体渠道实测，不存在旧百炼直连自动回退；
   当前该门禁已通过。
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

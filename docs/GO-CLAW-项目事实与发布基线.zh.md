# GO CLAW 项目事实与发布基线

> 状态：当前有效。最后现场复核：2026-08-28（Asia/Shanghai）。
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
| 本地仓库 | `/Volumes/固态2/2026/0811 GO Claw 2.0/upstream/QwenPaw-v2.0.1` | `git rev-parse --show-toplevel` |
| GitHub 仓库 | `GresonKwan/GO-Claw-2.0` | `gh repo view` |
| 产品基线 | QwenPaw v2.0.1，导入提交 `24813b3` | 变更台账和 Git 历史 |
| 本轮设计提交 | `ce18d02f` | `git show --stat ce18d02f` |
| 本轮四份原始计划提交 | `3fc3be19` | `git show --stat 3fc3be19` |
| 在线更新实现提交 | `58b5fbe8` | `git show --stat 58b5fbe8` |

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

当前代码仍是 schema 1：通用 `provision.json` 内嵌一个所有客户端共享的 HMAC secret，
客户端用它签名后换取每实例 New API 子令牌。当前实现还有两个必须正视的事实：

1. 分发进客户端的 HMAC secret 可以被提取，不能作为强身份凭证；
2. `go_claw_provision.py` 发现已有 `credentials.json` 时会跳过 provisioning，因此同时打包
   静态共享凭据和 provisioning 配置会直接绕过每实例开户。

用户已确认接受低额度 API key 存放在客户本地的交付取舍。v2.1 保留现有
`credentials.json` schema 1 和一次性本地导入逻辑：

- Main CI 使用已有 `GO_CLAW_DASHSCOPE_API_KEY` 生成一份指向
  `https://goclaw.host:8443/v1` 的本地 `credentials.json`；
- 同一个低额度 New API key 供文字和媒体 provider 使用，不新增 secret；
- Main Full ZIP 包含该凭据，首次启动自动导入，不出现激活或开户交互；
- Main Full ZIP 不包含 `provision.json`、共享 HMAC 或 enrollment ticket；
- 在线更新 payload 不包含 `GO-CLAW-Config`，因此不覆盖客户本地 key。

现有 schema-1 HMAC provisioning 服务可保留用于历史客户，但不是 v2.1 Main Build 前置条件；
本轮不实施 schema 2、激活码、ticket DB 或客户 ZIP sealing。

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

`GO_CLAW_LLM_API_KEY` 当前不存在，v2.1 不新增它。Main Build 直接复用已有
`GO_CLAW_DASHSCOPE_API_KEY` 作为低额度 New API key，同时写入客户本地的文字和媒体凭据字段。
保留的是 Secret 名称；其值必须通过 `https://goclaw.host:8443/v1/models` 七模型预检。若现值不是
可用的低额度 New API key，只替换该 Secret 的值。本轮不新建 `GO_CLAW_CI_TEST_API_KEY` 或其他测试额度机制。

2026-08-26 已在 New API 创建专用交付令牌 ID 29（名称
`go-claw-main-v2.1-full`）：非无限额度，只允许本轮七个产品模型。创建前数据库备份为
`/opt/new-api/data/backups/one-api-before-main-delivery-token-20260826T153608Z.db`，完整性为 `ok`。
令牌值已直接写入现有 GitHub Secret `GO_CLAW_DASHSCOPE_API_KEY`，未输出到日志；
实测 `/v1/models` 七模型全部可见。

### 7.2 产物与发布现状

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
`476989105`。

生产镜像的 `latest.json` 下载 URL 固定为同域
`https://goclaw.host:8443/updates/GO-CLAW-Update-2.1.0-setup.exe`，避免国内客户端再跳转
GitHub 下载。v2.0.1 的 manifest 拉取没有开启 HTTP redirect，GitHub
`/releases/latest/download/latest.json` 回退会因 302 失败；在后续客户端修正前，
`goclaw.host` 主 endpoint 是已安装 v2.0.1 的必要更新入口，不得下线。

尚未完成的是用户在真实 v2.0.1 Windows 客户端执行“检查、下载、验签、更新、重启、
数据保留”的最终端到端验收；线上资产和检查链已经开放。

## 9. 发布不可变条件

正式 `v2.1.0` Main Build 只有同时满足下列条件才可交付：

1. Tauri Auto 模式以 React 内容首帧为成功条件；WebView 失败只打开一次浏览器，后端失败
   显示明确故障页而不是打开一个同样不可用的浏览器。
2. 客户前端和其调用的产品 API 响应不出现 provider/model/base URL/API key。
3. 每个员工独立保存经济/均衡/高性能档位，新员工默认经济。
4. 五个媒体工具均通过 New API 的 Token Plan 原生媒体渠道实测，不存在旧百炼直连自动回退；
   当前该门禁已通过。
5. Main Full ZIP 包含已接受的低额度本地 `credentials.json`，但不包含 `provision.json`、共享 HMAC、ticket 或签名私钥；在线更新资产不包含客户凭据。
6. 三处 updater 公钥一致，安装器和更新包均由现有私钥签名并经项目 verifier 复验。
7. `/updates/latest.json` 返回 `application/json`，文件、SHA-256、签名和 URL 相互一致。
8. Main Build 的客户 artifact 内恰好有一个完整 ZIP；在两类 Windows 终端完成 Tauri、
   浏览器回退和 WebView2 恢复验收。

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

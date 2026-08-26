# GO CLAW v2.1 Review 后唯一执行计划

> 状态：已完成架构 review，待实施。
>
> **执行要求：** 实施时逐任务使用 `executing-plans`；每个行为变更先写失败测试，完成声明前使用
> `verification-before-completion`。本文件是四份 2026-08-26 分计划之间的唯一顺序和跨模块合同。
> 分计划中的文件级说明只有在不与本文及
> `docs/GO-CLAW-项目事实与发布基线.zh.md` 冲突时才有效。

**目标：** 先修复开户、媒体协议、客户 API、签名/交付和更新镜像之间的断层，再完成桌面可靠性、
客户界面、模型档位、两个媒体插件和唯一 Main CI ZIP；此后只通过已验签的在线更新发布版本。

**review 基线：** 代码设计 `ce18d02f`，四份原始计划 `3fc3be19`，现场复核日期
2026-08-26。行号只用于审计，发生位移后以表中 symbol/JSON key/route 为唯一定位。

---

## 1. review 结论与唯一决策

| 编号 | 已发现的重大冲突 | 唯一决策 |
| --- | --- | --- |
| R1 | 静态 `credentials.json` 会让 `go_claw_provision.py` 直接跳过每实例开户；通用 HMAC secret 又可从客户端提取 | Main CI 包完全无凭据；用一次性 enrollment ticket 私下封装首次交付，删除共享 HMAC |
| R2 | 原媒体计划使用错误的图片编辑路径、旧视频路径和 `data.result_url` 响应 | 图片生成用 `/v1/images/generations`，图片编辑用 multipart `/v1/images/edits`；视频固定用 `/v1/videos` 和顶层 `status`/`metadata.url` |
| R3 | 现网 New API 的 OpenAI 类型 Token Plan 渠道不能替选中的 HappyHorse 原生媒体体；Ali 适配器也只特殊处理 Wan 2.7 | 保留文字渠道 1；新增单独 Ali 类型 Token Plan 媒体渠道，并部署固定上游 commit 的最小服务端补丁 |
| R4 | 聊天选择器虽隐藏模型 ID，`/api/agents`、员工表格和编辑弹窗仍传输/显示 `active_model` | 客户前端改用只含 tier 的产品 DTO；员工页不再调用 provider catalog 或原始 agent config 接口 |
| R5 | 原签名计划准备生成第二套本地密钥 | 不轮换；只使用现有已签名实测通过的密钥，路径和保管规则引用既有签名运维文档 |
| R6 | release 计划一处禁止上传凭据，另一处又要求 Full ZIP 包含凭据 | 通用 Full ZIP 永远 credential-free；客户 ticket 只由本地 sealing 步骤加入交付副本，绝不回传 GitHub |
| R7 | 当前 Main build 只有分散 artifacts，且更新镜像 URL 返回 HTML/404 | CI 上传一个内含单一 Full ZIP 的 artifact；Nginx 增加原子 `/updates/` 静态发布后才执行正式 Main build |
| R8 | 后端启动失败若一律浏览器回退，浏览器同样没有可用页面 | WebView 失败且后端已就绪才回退浏览器；后端失败进入明确 fatal UI/原生对话框，不制造第二个空白入口 |

不得引入这些替代方案：客户端媒体直连百炼、模型失败自动换模型、通用 ZIP 内置共享 API key、
通用 ZIP 内置共享 HMAC、第二套 updater 密钥、用 `api.tokenbyte.ai` 作为新交付网关。

## 2. 依赖顺序

```text
P0 项目事实冻结
  ├─ P1 enrollment/凭据 v2
  ├─ P2 New API 媒体适配与现网五项付费探针
  └─ P3 Tauri 内容就绪状态机

P1 + P2
  → P4 三档模型和客户 API/界面
  → P5 两个中性媒体插件及迁移

P3 + P4 + P5
  → P6 签名、唯一 Full ZIP、更新镜像
  → P7 签名 Main build 与 Windows 验收
  → P8 发布 v2.1.0，后续只走在线更新
```

P2 的五项真实媒体探针未通过时，P5 可以在 mock 下开发，但不得合并为 release candidate。
P7 之前不得创建并行的第二个 Main 候选 run。

## 3. P0：项目事实冻结

**文件：**

- 维护：`docs/GO-CLAW-项目事实与发布基线.zh.md`
- 修改：`docs/GO-CLAW-文档规范.zh.md`
- 修改：`docs/GO-CLAW-变更台账.zh.md`
- 修改：四份 `docs/superpowers/plans/2026-08-26-go-claw-*-plan.md`

**完成条件：**

- [ ] 四份分计划标题下都标明“受本计划约束”，并移除/标废 R1–R8 的冲突文字。
- [ ] 文档规范把“当前事实”和“历史台账”分开，不再同时声称两个文件都是同一类唯一事实源。
- [ ] 所有外部 URL、容器 revision/digest、SSH/Nginx 文件、GitHub setting 名称都有验证日期。
- [ ] `rg -n 'api\.tokenbyte\.ai|updater-2026-08\.key|containsBatchCredentials.*true' docs/superpowers/plans/2026-08-26-go-claw-*` 的每个剩余命中都明确标注为“已否决历史”，不得作为命令或目标配置出现。

## 4. P1：一次性开户与凭据 v2

### 4.1 为什么必须先改

一个可无限复制的通用 ZIP 不可能安全保存能够证明“正版客户端”的共享秘密。将 HMAC 放进客户端
只是把全局开户权限交给任何拿到安装包的人。因此采用“通用无凭据构建 + 每次交付一个一次性 ticket”；
它保持客户零输入，同时把泄露范围限制为一次开户。

### 4.2 外部文件和 HTTP 合同

客户专属 `Portable/GO-CLAW-Config/provision.json` 只允许 schema 2：

```json
{
  "schemaVersion": 2,
  "provisionUrl": "https://goclaw.host:8443/go-claw/provision",
  "ticket": "gce_43-or-more-base64url-characters"
}
```

公开请求固定为：

```http
POST /go-claw/provision
Content-Type: application/json

{
  "schemaVersion": 2,
  "instanceId": "e64b8db8-2665-45ef-b708-9c22c1d84d6a",
  "ticket": "gce_43-or-more-base64url-characters"
}
```

成功响应只供本地 Python 后端读取，不进入浏览器：

```json
{
  "schemaVersion": 2,
  "enrollmentId": "enr_6fe7274e7d14429ea2fd317f492f7c04",
  "newApi": {
    "providerId": "deepseek",
    "baseUrl": "https://goclaw.host:8443/v1",
    "apiKey": "per-instance New API token",
    "modelIds": [
      "deepseek-v4-flash-0731",
      "qwen3.7-plus",
      "qwen3.8-max",
      "qwen-image-3.0-pro",
      "happyhorse-1.1-t2v",
      "happyhorse-1.1-i2v",
      "happyhorse-1.1-r2v"
    ]
  }
}
```

错误响应固定为：

```json
{"schemaVersion":2,"code":"ENROLLMENT_EXPIRED","message":"交付凭证已失效，请联系服务人员"}
```

允许的 `code` 只有 `INVALID_REQUEST`、`ENROLLMENT_INVALID`、`ENROLLMENT_EXPIRED`、
`ENROLLMENT_ALREADY_USED`、`RATE_LIMITED`、`UPSTREAM_UNAVAILABLE`。响应和日志都不得回显 ticket、
New API token 或完整请求体。

### 4.3 ticket 数据合同

在 `scripts/provisioning/provision_server.py` 的 SQLite schema 中新增：

```sql
CREATE TABLE IF NOT EXISTS enrollment_tickets (
    ticket_hash       TEXT PRIMARY KEY,
    enrollment_id    TEXT NOT NULL UNIQUE,
    batch_id          TEXT NOT NULL,
    expires_at        INTEGER NOT NULL,
    max_instances     INTEGER NOT NULL DEFAULT 1,
    bound_instance_id TEXT,
    created_at        INTEGER NOT NULL,
    consumed_at       INTEGER
);
```

`enrollmentId` 是 `enr_` 加 16 个随机字节的 32 位小写 hex；ticket 是 `gce_` 加 32 个随机
字节的无 padding base64url；数据库只保存完整 ticket 的 SHA-256 十六进制。
服务端用 `BEGIN IMMEDIATE` 原子完成校验和绑定：未绑定 ticket 绑定当前 `instanceId`；已绑定且
instance 相同的重试返回同一份开户结果；不同 instance 永远返回
`ENROLLMENT_ALREADY_USED`。默认过期时间 7 天，`max_instances` 固定 1。

### 4.4 代码修改点

| 当前文件/范围 | symbol | 唯一修改 |
| --- | --- | --- |
| `scripts/provisioning/provision_server.py:79-159` | `_SCHEMA`、`init_db`、persistence helpers | 增加 ticket 表、hash、原子绑定和 schema 迁移 |
| `scripts/provisioning/provision_server.py:343-479` | `build_credentials_payload`、`ProvisionRequest`、`provision` | 接受 schema 2；删除 HMAC/timestamp；返回上面的 schema 2 |
| `scripts/provisioning/.env.example` | `PROVISION_HMAC_SECRET` | 删除；增加 `ENROLLMENT_DEFAULT_TTL_SECONDS=604800` |
| `scripts/provisioning/issue_enrollment_ticket.py`（新建） | CLI | 只允许在服务器本机运行，写 DB；用必填 `--output` 以 `0600`/exclusive-create 写 schema-2 `provision.json`，stdout 只打印 enrollment ID |
| `src/qwenpaw/app/go_claw_provision.py:1-160` | `_load_provision_config`、`_provision` | schema 2 请求；成功后直接调用共享 credentials apply service，验证后删除 ticket 文件 |
| `src/qwenpaw/app/go_claw_credentials.py:31-339` | `BatchCredentials`、`_import...` | 增加 v1/v2 discriminated union；抽出 `apply_go_claw_credentials`；v1 只用于旧交付迁移 |
| `.github/workflows/desktop-build.yml:89-164` | credentials/provision materialization | 删除两种秘密文件 materialization；通用 CI stage 中二者都不存在 |
| `scripts/pack-tauri/seal_customer_bundle.py`（新建） | local sealing CLI | 将一个 ticket 注入 Full ZIP 副本并重算 manifest/checksums；拒绝覆盖输入 ZIP |

`go_claw_provision.py` 的顺序固定为：读取/创建 instance ID → POST → 严格验证 schema 2 →
持久化 provider → 验证 URL/key/七模型 → 写 routing marker → 写 enrollment marker → 删除
`provision.json`。任一步失败不写完成 marker、不删除 ticket，下一次启动重试。

已有安装的迁移边界必须明确：已经持有 `goclaw.host:8443` 每实例 token 的客户保留原 token，不
重新开户；仍持有静态共享凭据或 `api.tokenbyte.ai` 凭据的客户不能靠通用在线更新安全获得一个
私有 ticket，因为更新资产对所有人相同。此类客户必须由运营逐一签发 schema-2 `provision.json`
并通过受控渠道放入其 `GO-CLAW-Config`，或者重新交付 sealing 后的 Portable ZIP。不得在通用
`latest.json`/更新包中夹带迁移 ticket，也不得静默复用旧共享 key。

### 4.5 测试和门禁

- [ ] 先在 `scripts/provisioning/test_provision_server.py` 写 ticket hash、过期、原子单用、同实例幂等、
  不同实例拒绝、日志脱敏测试。
- [ ] 在 `tests/unit/app/test_go_claw_provision.py` 写 schema 2、失败保留 ticket、成功删除、已有旧
  `credentials.json` 不得覆盖新 ticket 的测试。
- [ ] 在 `tests/unit/app/test_go_claw_credentials.py` 写 v1 迁移、v2 应用、七模型去重、marker-last、
  不更新 DashScope provider 的测试。
- [ ] 在 `tests/unit/scripts/test_seal_customer_bundle.py` 写路径逃逸、重复 ticket、输入不变、manifest
  重算和输出单 ZIP 测试。
- [ ] `rg -n 'GO_CLAW_LLM_API_KEY|GO_CLAW_PROVISION_HMAC_SECRET|hmacSecret' .github/workflows/desktop-build.yml scripts/pack-tauri` 必须零命中。

## 5. P2：New API 媒体服务端适配

### 5.1 渠道划分

现有渠道 1 继续只承担三档文字模型，不更改类型和已工作的文字映射。新增渠道名称固定为
`阿里百炼_TokenPlan_Media`：

```text
type: Ali（New API channel type 17）
base_url: https://token-plan.cn-beijing.maas.aliyuncs.com
models:
  qwen-image-3.0-pro
  happyhorse-1.1-t2v
  happyhorse-1.1-i2v
  happyhorse-1.1-r2v
model_mapping: identity
```

创建后把实际 channel ID 写回项目事实文档。渠道 2 可保留给旧调用，但上面四个模型不得出现在
渠道 2，确保它们不会自动落到百炼直连。

### 5.2 New API 补丁边界

产品仓库新增：

- `deploy/new-api/Dockerfile`：只从
  `5c3abffe8572aa8a49f15c3916707d2019d66af4` 构建；
- `deploy/new-api/patches/0001-go-claw-token-plan-media.patch`；
- `deploy/new-api/build-and-verify.sh`；
- `tests/contracts/test_new_api_patch_contract.py`。

补丁只改上游三个文件：

| 上游文件 | 唯一修改 |
| --- | --- |
| `relay/channel/task/ali/constants.go` | 将三种 `happyhorse-1.1-*` 加入 `ModelList` |
| `relay/channel/task/ali/adaptor.go` | i2v 转为 `media[type=first_frame]`；r2v 的 1–3 张图转为 `media[type=reference_image]`；清除 legacy img 字段 |
| `relay/channel/task/ali/adaptor_test.go` | 覆盖 t2v/i2v/r2v 精确上游 JSON、空图/超三图拒绝、模型映射不改 family |

镜像标签固定为 `go-claw/new-api:v1.0.0-rc.24-goclaw.1`。实际构建 digest 在部署后写回事实
文档；禁止用 `latest`。部署前备份 `/opt/new-api/data/one-api.db`，复用现有
`/opt/new-api/data:/data` bind 和 `127.0.0.1:3000` 监听，健康检查通过后才停止旧容器；失败立即
回到已经记录 digest 的旧镜像。

### 5.3 GO CLAW → New API 唯一媒体合同

所有请求使用 `Authorization: Bearer <per-instance token>`；客户端日志不记录 header、data URL、
带签名的结果 URL。

图片生成：

```http
POST /v1/images/generations
Content-Type: application/json

{
  "model": "qwen-image-3.0-pro",
  "prompt": "用户提示词",
  "n": 1,
  "size": "2048x2048",
  "response_format": "url",
  "parameters": {
    "size": "2048*2048",
    "n": 1,
    "negative_prompt": "",
    "prompt_extend": true
  }
}
```

当前 pinned New API 一旦看到扩展 `parameters` 就以该对象构造 Ali 参数，不会自动把标准顶层
`size/n` 合并进去，所以两处值必须同时存在且一致：顶层使用 OpenAI 的 `2048x2048`，扩展对象
使用 Ali 的 `2048*2048`。插件在一个构造函数中生成两处值，测试必须拒绝不一致，避免尺寸和数量
被悄悄丢弃。

图片编辑必须是 multipart，不能把 `image` JSON 发到 generations：

```text
POST /v1/images/edits
Content-Type: multipart/form-data
fields: model=qwen-image-3.0-pro, prompt=<text>, n=1, response_format=url
files:  image=<binary>（同名字段 1–3 次，保持输入顺序）
```

本轮编辑工具不公开 `negative_prompt`、`prompt_extend` 和输出 size，因为当前上游 multipart
转换没有可靠接收这三项；不得在提示词中承诺它们。

视频提交/查询统一使用当前 New API 的 OpenAI Video 路径：

```text
POST /v1/videos
GET  /v1/videos/<id>
```

三个提交体分别固定为：

```json
{"model":"happyhorse-1.1-t2v","prompt":"用户提示词","duration":5,"size":"1280*720","metadata":{"input":{"negative_prompt":""},"parameters":{"prompt_extend":true}}}
```

```json
{"model":"happyhorse-1.1-i2v","prompt":"用户提示词","duration":5,"size":"720P","image":"data-or-https-url","metadata":{"parameters":{"prompt_extend":true}}}
```

```json
{"model":"happyhorse-1.1-r2v","prompt":"用户提示词","duration":5,"size":"720P","images":["data-or-https-url-1","data-or-https-url-2"],"metadata":{"parameters":{"prompt_extend":true}}}
```

创建响应和轮询响应都只解析顶层字段：

```json
{
  "id": "public-task-id",
  "status": "queued|in_progress|completed|failed",
  "progress": 0,
  "metadata": {"url": "present only when completed"},
  "error": {"code": "present on failure", "message": "neutralized by client"}
}
```

成功条件是 `status == "completed"` 且 `metadata.url` 是 `https`；不得解析
`data.status`、`data.result_url` 或旧 `/v1/video/generations`。创建请求收到不确定网络错误时不自动
重放，防止重复计费；已取得 task ID 后只轮询同一 ID。模型不可用时直接返回中性错误，不换模型。

### 5.4 五项真实门禁

`scripts/verify/new_api_media_contract.py` 使用独立低额度的 `GO_CLAW_CI_TEST_API_KEY`，依次只做：

1. 一张最小图片生成；
2. 一张图的最小图片编辑；
3. 最短文生视频；
4. 最短图生视频；
5. 一张参考图的最短参考视频。

五项均需证明 New API task/channel 记录命中 `阿里百炼_TokenPlan_Media`，并保存只含时间、模型
内部 ID、channel ID、request/task ID、状态和自定义镜像 digest 的脱敏 JSON。任何一项失败都阻断
客户端 release；`GET /v1/models` 通过不能代替此门禁。

## 6. P3：Tauri 内容就绪与失败语义

沿用 `2026-08-26-go-claw-desktop-readiness-plan.md` 的事件驱动状态机，但作以下强制修正：

```rust
enum ClientPhase {
    ProcessStarting,
    BootstrapCreating,
    BootstrapReady,
    BackendReady,
    ConsoleNavigating,
    ConsoleReady,
    DesktopActive,
    BrowserFallback,
    FatalStartup,
}
```

- `BrowserFallback` 只允许 `ExplicitBrowserMode`、`WebviewBuildFailed`、
  `BootstrapReadyTimeout`、`ConsoleNavigationFailed`、`ConsoleReadyTimeout`；除明确 browser mode 外，
  fallback 可以先被预留，但真正打开浏览器前必须已有 `backend_port` 且 `/api/version` 返回 2xx。
- `BackendStartupFailed` 进入 `FatalStartup`：若 Bootstrap 可显示，就显示“服务启动失败”、重试、打开
  日志目录、退出；Bootstrap 也不可用时显示原生错误对话框。即使 WebView 先失败、状态已经预留
  `BrowserFallback`，后端随后失败也必须升级为 `FatalStartup`。不得打开一个同样无法连接的浏览器。
- `WebviewWindowBuilder::build()` 不是成功；只有正式 console 完成两帧并调用
  `client_console_ready` 才进入 `DesktopActive`。
- 10 秒 Bootstrap 和 30 秒 Console watchdog 只在异常时触发，不加入正常路径串行等待；正常启动时长
  只取决于现有后端和页面实际就绪时间。
- 测试必须覆盖“窗口存在但 DOM marker 永远不出现”，最终只打开一次浏览器且隐藏空窗口。

修改文件、IPC/event 名和测试矩阵保持桌面分计划第 1–8 Task；在
`.github/actions/verify-tauri-windows*/action.yml` 中，CDP/进程存在不能替代
`data-go-claw-console-ready="1"` 和截图证据。

## 7. P4：三档模型、客户 API 和界面

### 7.1 档位合同

档位顺序固定为经济、均衡、高性能，新员工默认经济；每个员工独立持久化。后端
`src/qwenpaw/app/go_claw_product.py` 是 tier → model 的唯一运行时映射。产品 API 只返回：

```json
{
  "schemaVersion": 1,
  "agentId": "content-production",
  "selectedTier": "economy",
  "tiers": [
    {"id":"economy","label":"经济","description":"适合日常任务，额度更耐用","warning":null,"icon":"leaf"},
    {"id":"balanced","label":"均衡","description":"质量与额度消耗更均衡","warning":null,"icon":"balance"},
    {"id":"performance","label":"高性能","description":"适合复杂和高要求任务","warning":"高性能模型可以提高任务完成质量，但额度消耗更快。","icon":"rocket"}
  ]
}
```

### 7.2 修复员工页原始模型泄漏

除原 UI 分计划列出的改动外，必须修改：

| 当前文件/范围 | 当前泄漏 | 唯一修改 |
| --- | --- | --- |
| `src/qwenpaw/app/routers/agents.py:46-55,246-264` | `AgentSummary.active_model` | 产品 summary 改为 `model_tier`，不序列化 slot |
| `src/qwenpaw/app/routers/agents.py:70-86,439-460` | create 接受/回退 raw slot | customer create DTO 不接受 slot；后端私下解析并持久化 economy |
| `src/qwenpaw/app/routers/agents.py:359-365,636-648` | get/update 返回完整 `AgentProfileConfig` | 新增 customer editable DTO，排除 `active_model`；模型更新只能走 tier PUT |
| `console/src/api/types/agents.ts:12-42` | TypeScript 暴露 `ModelSlotConfig` | 客户 DTO 只含 `model_tier`，删除 raw slot import |
| `console/src/pages/Settings/Agents/index.tsx:52-65,146-155` | 读取/提交 raw slot | 改调产品 tier API，不构造 `active_model` |
| `console/src/pages/Settings/Agents/components/AgentTable.tsx:141-160` | 表格显示真实模型名和 provider icon | 显示叶片/天平/火箭和中文档位 |
| `console/src/pages/Settings/Agents/components/AgentModal.tsx:57-97,185-280` | 调 `listProviders()` 并渲染模型 | 删除 provider state/API；复用三档 tier choices |

浏览器网络响应、DOM、aria-label、tooltip、前端日志、localStorage 和前端 fixture 不得出现七个内部
模型 ID、provider ID、base URL 或 API key。新增递归 JSON 单测和一次 Playwright 网络捕获检查。

### 7.3 其余客户 UI

按 UI 分计划实施：隐藏右上“代码”、侧边栏“模型/数字员工统计/文件”、设置中的语言；侧边栏底部
固定额度、设置、收起；静态文字 caret 透明，真实输入恢复；字号/图标提升一档；三个 SVG 分别是
叶片、天平和火箭。对应 route component 源码可保留，但三个条目不进入导出的产品
`BUILTIN_ROUTES`，直接 URL 由现有 unmatched-route fallback 重定向到首页。

## 8. P5：两个中性媒体插件

插件目录、ID 和公开工具固定为：

```text
plugins/tool/image-generation      image-generation-tool
  generate_image
  edit_image

plugins/tool/video-generation      video-generation-tool
  generate_video_from_text
  generate_video_from_image
  generate_video_from_reference
```

公开 schema 不含 `model`、`provider`、`endpoint`、`api_key` 或厂商名。图片生成默认内部模型是
`qwen-image-3.0-pro`；没有自动回退。旧 Qwen/Wan 工具名只作为隐藏、禁用、不可列举的迁移别名。

工具描述和内容生产员工提示词必须与 P2 的真实参数交集一致：图片编辑不承诺负向提示/尺寸；视频
不承诺旧版末帧、音频、模板、续写；选择哪个工具由输入是零张、首帧一张或参考图 1–3 张决定。
实现/测试文件沿用媒体分计划 Task 1–6，但所有 HTTP 断言以本文 P2.3 为准。

## 9. P6：签名、唯一 Full ZIP 和更新镜像

### 9.1 密钥

不执行 key generate。只按 `docs/GO-CLAW-在线更新签名密钥运维.zh.md` 读取现有本地密钥和
钥匙串口令。CI 必须证明：

```text
tauri.conf.json pubkey
  == GitHub Variable TAURI_UPDATER_PUBKEY
  == Portable/GO-CLAW-Config/update-pubkey.txt
```

并对真实 update installer 做一次项目 `verify_minisign` 复验。GitHub Secret 无法读取，所以私钥
是否匹配的最终 CI 证据是“签名产物能被仓库公钥验证”，不是 Secret 名称存在。

### 9.2 通用 CI 完整 ZIP

artifact 内只允许一个文件：

```text
GO-CLAW-Windows-x64-Full.zip
```

ZIP 内只有一个版本根：

```text
GO-CLAW-Windows-x64-Full-<version>/
  START-HERE.zh-CN.txt
  Portable/
  WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe
  MANIFEST.json
  SHA256SUMS.txt
```

这里的 “Full” 指客户冷启动所需的完整便携应用、Python/Node/runtime、插件和离线 WebView2，
不是把发布流水线的每个中间产物再复制一份进 ZIP。安装版 NSIS 和在线更新 exe/sig/manifest 继续
作为经过验证的独立 publish transport artifacts，供 GitHub Release 和 `/updates/` 使用，不进入客户
首次交付 ZIP。这样 sealing 后的 ticket 只存在于实际会读取它的 Portable 配置中，不会出现“ZIP
里有 ticket、安装器安装后却找不到”的第二套首次启动语义。

通用 manifest 固定包含：

```json
{
  "schemaVersion": 2,
  "product": "GO CLAW",
  "platform": "windows-x86_64",
  "containsCredentials": false,
  "containsEnrollmentTicket": false,
  "confidential": false
}
```

assembler 发现 `credentials.json`、`provision.json`、`hmacSecret`、疑似 `sk-` token 或私钥 header
时立即失败。Actions artifact 名为 `GO-CLAW-Windows-x64-Full-<version>`，其上传 path 只匹配这一个
ZIP。GitHub 平台自己的下载包装不计为产品内嵌压缩包。

客户 sealing 输出 `GO-CLAW-Windows-x64-Delivery-<enrollmentId>.zip`，manifest 中
`containsEnrollmentTicket=true`、`confidential=true`；它只能保存在批准的本地交付目录，不能上传
Actions、Release、缓存或更新镜像。

### 9.3 `/updates/` 原子静态发布

客户端和 `tauri.conf.json` 的主 endpoint 都使用 8443，因此在服务器
`/etc/nginx/conf.d/newapi-8443.conf` 的 `server_name goclaw.host` 8443 server、现有
通配 `location /` 之前加入：

```nginx
location ^~ /updates/ {
    root /srv/go-claw-updates;
    try_files $uri =404;
    add_header Cache-Control "no-cache" always;
    add_header X-Content-Type-Options "nosniff" always;
}
```

文件布局固定为：

```text
/srv/go-claw-updates/
  releases/<version>/latest.json
  releases/<version>/GO-CLAW-Update-<version>-setup.exe
  releases/<version>/GO-CLAW-Update-<version>-setup.exe.sig
  updates -> releases/<version>
```

先上传并在新 release 目录本地验 SHA-256/签名，再用临时 symlink + 同文件系统 rename 原子替换
`updates`。`nginx -t` 通过后 reload。验收必须同时检查 200、`application/json`、manifest schema、
签名、SHA-256 和 URL basename；返回 HTML 视为失败。GitHub Release 继续作为 manifest 的第二
endpoint，但只有统一 `release.yml` 可以发布。

## 10. P7：唯一签名 Main build 验收

### 10.1 前置条件

- [ ] P1 ticket provisioning 已部署并用一次性测试 ticket 通过；
- [ ] P2 自定义 New API 镜像和媒体渠道已部署，五项真实探针通过；
- [ ] P3/P4/P5 全部单测、前端全量、Cargo 和构建通过；
- [ ] `GO_CLAW_CI_TEST_API_KEY` 已作为独立低额度 GitHub Secret 配置，通用包扫描证明未包含；
- [ ] 三处公钥一致，本地签名探针通过；
- [ ] Nginx `/updates/` staging 路径可用但尚未切换生产 `latest.json`；
- [ ] `main` 工作树、远端分支和目标 commit 一致。

### 10.2 唯一 run

```bash
gh workflow run desktop-build.yml --ref main -f ref=main -f windows_only=true -f unsigned_test=false
```

记录 run ID。失败只 rerun failed jobs 或修复后启动新的明确候选；同一 commit 不并行启动两个
候选。下载后要求 artifact 内恰好一个 `GO-CLAW-Windows-x64-Full.zip`，运行
`scripts/verify/windows_release_contract.py` 做离线复验。

### 10.3 Windows 两机验收

1. 正常 WebView2 终端：Auto 直接进入 Tauri，出现 console-ready marker；五名员工各自档位独立。
2. 无/损坏 WebView2 终端：不出现永久空白；后端就绪后只打开一次系统浏览器；安装 Full ZIP 内
   Evergreen 后重试，Auto 回到 Tauri。
3. 人为令后端启动失败：显示 fatal UI/原生错误，不打开无法访问的浏览器。
4. 使用一次性测试 ticket 封装一个测试交付副本；首次开户成功、第二个 instance 使用同 ticket
   被拒绝。
5. 五个媒体工具各调用一次；UI/工具文本无厂商和模型名；New API 记录全部命中媒体渠道。
6. 下载一次已 staging 的更新，验证、安装、自动重启和回滚各一次。

全部通过后才原子切换 `/srv/go-claw-updates/updates` 并发布 GitHub Release。

## 11. 总验证命令

```bash
uv run pytest -q scripts/provisioning/test_provision_server.py
uv run pytest -q tests/unit/app/test_go_claw_provision.py tests/unit/app/test_go_claw_credentials.py
uv run pytest -q tests/unit/plugins tests/unit/app/test_go_claw_bundled_plugins.py
uv run pytest -q tests/unit/scripts/test_new_api_media_contract.py tests/unit/scripts/test_windows_release_contract.py
npm --prefix console run format:check
npm --prefix console run test:run
npm --prefix console run build:prod
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo test --manifest-path console/src-tauri/Cargo.toml
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 .github/workflows/*.yml
git diff --check
```

最后执行秘密扫描时只能扫描 tracked/staged 变更，不能把 ignored 的真实凭据内容打印到终端。完成
定义不是“测试绿”，而是 P2 五项真实探针、P7 签名 Main run、两类 Windows、更新镜像和一次性
开户全部有脱敏证据。

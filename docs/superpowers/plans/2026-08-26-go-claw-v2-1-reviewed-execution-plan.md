# GO CLAW v2.1 唯一执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以最小必要改动完成 Tauri 启动可靠性、客户界面收敛、三档文字模型、Token Plan 媒体模型替换、更新签名和单一 Full ZIP，执行一次正式 Main Build。

**Architecture:** 保留本地低额度 API key 交付和 New API 公开媒体 endpoint。首次真实调用证明文字渠道不能承载 Token Plan 原生媒体后，用户另行明确授权新增了一个最小 Ali 媒体渠道。不引入激活码、enrollment ticket、自定义 New API 镜像、新客户端 endpoint 或新的额度层。

**Tech Stack:** Python, FastAPI, React/TypeScript, Tauri/Rust, Pytest, Vitest, GitHub Actions, NSIS, New API.

---

## 1. 执行原则与已删除的过度设计

当计划、分计划、历史设计或聊天记录冲突时，以本文为唯一执行顺序，以
`docs/GO-CLAW-项目事实与发布基线.zh.md` 记录的已验证现状为事实。

本轮明确删除以下工作，不得在实施时重新加回：

- enrollment ticket、激活码、schema 2 provisioning、ticket DB 和客户 ZIP sealing；
- 为本轮额外设计独立额度、请求预算或 `GO_CLAW_CI_TEST_API_KEY`；
- 未经现场证据和用户授权新建渠道（本轮已有一次受控例外：渠道 3）；
- New API 私有 Dockerfile、HappyHorse adapter patch 和上游 fork；
- 把现有图片编辑换成 `/v1/images/edits` 或把视频换成 `/v1/videos`；
- 客户端媒体直连百炼，以及任何模型自动回退；
- 第二套 Tauri updater 密钥。

如果真实测试失败，执行者只收集脱敏证据并报告最小修正建议。一次失败不自动授权引入上述架构。

## 2. 唯一依赖顺序

```text
P0 文档合同收敛
  ├─ P1 Tauri 内容就绪与失败语义
  ├─ P2 三档模型与客户界面
  └─ P3 媒体默认模型与中性名称

P1 + P2 + P3
  → P4 凭据、签名与单一 Full ZIP
  → P5 /updates/ 静态镜像
  → P6 唯一签名 Main Build 和 Windows 验收
  → P7 发布 v2.1.0，后续只走在线更新
```

P1、P2、P3 可在不同文件上开发，但必须在 P4 前合并并运行共同合同测试。不得在 P6 前启动一个“先看看”的正式 Main Build。

## 3. P0：文档合同收敛

**Files:**

- Modify: `docs/GO-CLAW-项目事实与发布基线.zh.md`
- Modify: `docs/go-claw-auto-provisioning.zh.md`
- Modify: `docs/superpowers/specs/2026-08-26-go-claw-v2-1-product-iteration-design.md`
- Modify: `docs/superpowers/plans/2026-08-26-go-claw-token-plan-media-plan.md`
- Modify: `docs/superpowers/plans/2026-08-26-go-claw-release-signing-plan.md`
- Modify: `docs/GO-CLAW-变更台账.zh.md`

- [x] 删除所有将 ticket/provisioning v2 写成 v2.1 发布前置条件的段落。
- [x] 取消 New API patch、`/v1/images/edits` 和 `/v1/videos` 新合同；后续按用户单独授权仅新增最小 `type=17` 媒体渠道。
- [x] 记录用户已接受“低额度 API key 存放在客户本地完整 ZIP”的交付取舍。
- [x] 记录“媒体保持 New API 公开 endpoint，视频供应商参数使用已验证的 metadata 嵌套合同”。
- [ ] 运行冲突扫描：

```bash
rg -n 'enrollment|ticket|TokenPlan_Media|channel type 17|deploy/new-api|/v1/images/edits|/v1/videos|GO_CLAW_CI_TEST_API_KEY' \
  docs/GO-CLAW-项目事实与发布基线.zh.md \
  docs/go-claw-auto-provisioning.zh.md \
  docs/superpowers/specs/2026-08-26-go-claw-v2-1-product-iteration-design.md \
  docs/superpowers/plans/2026-08-26-go-claw-*-plan.md
```

Expected: 只允许“已删除/禁止/历史实现”语境中的命中。

## 4. P1：Tauri 内容就绪与失败语义

文件级步骤唯一来源：
`docs/superpowers/plans/2026-08-26-go-claw-desktop-readiness-plan.md`。

完成合同不变：

- [ ] Auto 模式以 React 内容首帧/console-ready 为 Tauri 成功，不以“窗口已创建”为成功。
- [ ] WebView 失败时，只在 Python 后端 `/api/version` 已 2xx 后打开一次系统浏览器。
- [ ] 后端启动失败进入 fatal UI/原生错误，不打开无法访问的浏览器。
- [ ] 启动等待时间不增加人为延时；就绪事件一旦到达立即显示。

## 5. P2：三档模型和客户界面

文件级步骤唯一来源：
`docs/superpowers/plans/2026-08-26-go-claw-customer-ui-model-tiers-plan.md`。

唯一档位映射：

| 客户标签 | 内部模型 | 产品行为 |
| --- | --- | --- |
| 经济 | `deepseek-v4-flash-0731` | 新员工默认 |
| 均衡 | `qwen3.7-plus` | 每员工独立保存 |
| 高性能 | `qwen3.8-max` | 选中时显示额度消耗较快提醒 |

必须同时完成：

- [ ] 隐藏右上角“代码”、侧边栏“模型”、“数字员工统计”和“文件”。
- [ ] 从客户路由注册中删除这些入口，不只是 CSS 隐藏。
- [ ] 设置弹层不显示语言选择。
- [ ] 三档选择器使用三个已确认的中性图标，客户端不显示模型 ID。
- [ ] 员工表格、员工编辑弹窗和对应 API 不再向前端传输原始 provider/model/base URL/API key。
- [ ] 浏览器页面全局禁止非输入区域 caret；字号、图标和左下固定操作区整体放大一档。

## 6. P3：Token Plan 媒体模型替换

文件级步骤唯一来源：
`docs/superpowers/plans/2026-08-26-go-claw-token-plan-media-plan.md`。

这一阶段的代码范围只有：

- [x] 图片默认模型替换为 `qwen-image-3.0-pro`。
- [x] 三个视频默认模型替换为三个 `happyhorse-1.1-*` 目标模型。
- [x] 删除媒体模型不可用时的候选模型回退。
- [x] 插件客户可见名称改为“图片生成”和“视频生成”；工具名和提示词中性化。
- [x] 保持 `resolve_media_api` 和公开 URL；视频 body 按固定 New API Ali adaptor 合同嵌套 `metadata.input.media` / `metadata.parameters`。
- [x] 渠道 1、2 不做配置变更；经后续明确授权新增渠道 3。
- [x] 使用现有低额度 key 运行五个真实调用；结果全部通过。

## 7. P4：本地凭据、签名和单一 Full ZIP

### 7.1 凭据合同

保留现有 `GO-CLAW-Config/credentials.json` schema 1 和一次性本地导入逻辑，不修改
`BatchCredentials`、marker 或 provider 导入架构。Main Build 使用已存在的 GitHub Secret
`GO_CLAW_DASHSCOPE_API_KEY` 作为低额度 New API key，同时写入 `llm.apiKey` 和
`dashscope.apiKey`；不新增 secret。这里保留的是 Secret 名称，不是假定其现有值必然正确：Main Build
前必须用该值请求 `https://goclaw.host:8443/v1/models`，确认七个必需模型全部可见。若失败，唯一允许的
凭据修正是把这个 Secret 的值替换为可用的低额度 New API key，不得因此改写客户端协议或再扩大已批准的渠道 3 范围。

`.github/workflows/desktop-build.yml` 生成的内容固定为：

```json
{
  "schemaVersion": 1,
  "batchId": "go-claw-main-<github-run-id>",
  "llm": {
    "providerId": "deepseek",
    "modelId": "deepseek-v4-flash-0731",
    "baseUrl": "https://goclaw.host:8443/v1",
    "apiKey": "<GO_CLAW_DASHSCOPE_API_KEY>"
  },
  "dashscope": {
    "compatibleBaseUrl": "https://goclaw.host:8443/v1",
    "apiKey": "<GO_CLAW_DASHSCOPE_API_KEY>"
  }
}
```

实施修改点：

| 文件 | 当前行为 | 唯一修改 |
| --- | --- | --- |
| `.github/workflows/desktop-build.yml:89-138` | 同时等待不存在的 `GO_CLAW_LLM_API_KEY`，且 URL/模型是旧值 | 只要求已有 `GO_CLAW_DASHSCOPE_API_KEY`，用上述唯一 JSON，`/models` 检查七个必需 ID |
| `.github/workflows/desktop-build.yml:140-164` | 可生成 HMAC `provision.json` | 删除该 materialization step；不删服务端历史代码 |
| `scripts/pack-tauri/stage_windows_portable.py:115-181` | 已支持校验并携带 `credentials.json` | 保留；正式 Main Build 必须提供 credentials，不提供 provision |
| `tests/unit/scripts/test_stage_windows_portable.py:170-238` | 已覆盖凭据入包 | 更新 workflow URL/模型/secret 期望，新增“没有 provision.json”断言 |

在线更新包仍然不包含 `GO-CLAW-Config`，因此不覆盖客户已导入的 key。这是已确认的产品取舍：客户拿到 Full ZIP 后可以读取其中的低额度 key；不再用激活或开户系统隐藏该事实。

### 7.2 更新签名

文件级步骤来源：
`docs/superpowers/plans/2026-08-26-go-claw-release-signing-plan.md`。

- [x] 不生成新密钥，使用已经签名往返验证通过的现有私钥。
- [x] `tauri.conf.json` 公钥、GitHub Variable `TAURI_UPDATER_PUBKEY` 和入包 `update-pubkey.txt` 三处相等。
- [x] `sync_tauri_version.mjs` 将 GitHub Variable 当作相等性断言，不再用它覆盖仓库公钥。
- [ ] 安装器和更新包必须有 `.sig`，并由项目 `verify_minisign` 路径验证。

### 7.3 Full ZIP 合同

Actions 客户 artifact 内只允许一个文件：

```text
GO-CLAW-Windows-x64-Full.zip
```

ZIP 内只允许一个版本根：

```text
GO-CLAW-Windows-x64-Full-<version>/
  START-HERE.zh-CN.txt
  Portable/
    GO-CLAW-Portable.exe
    binaries/
    GO-CLAW-Config/
      credentials.json
      credentials.example.json
      update-pubkey.txt
    LICENSE
    README-PORTABLE.zh-CN.txt
    portable.json
  WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe
  MANIFEST.json
  SHA256SUMS.txt
```

`MANIFEST.json` 必须声明：

```json
{
  "schemaVersion": 2,
  "product": "GO CLAW",
  "platform": "windows-x86_64",
  "containsCredentials": true,
  "containsEnrollmentTicket": false,
  "confidential": true
}
```

assembler 必须要求恰好一个 `Portable/GO-CLAW-Config/credentials.json`，仅验证 schema 1、两个 base URL、
`llm.modelId=deepseek-v4-flash-0731`、两个 key 字段值相等且形式合法，不输出 key。七模型可用性由 workflow 的
`GET https://goclaw.host:8443/v1/models` 预检负责。assembler 必须拒绝 `provision.json`、`hmacSecret`、enrollment ticket 和签名私钥。安装版和更新 exe/sig/manifest 作为 publish transport artifact，不内嵌到 Full ZIP。

## 8. P5：`/updates/` 原子静态发布

在服务器 `/etc/nginx/conf.d/newapi-8443.conf` 的 8443 `server` 中、通配 `location /` 之前增加：

```nginx
location ^~ /updates/ {
    root /srv/go-claw-updates;
    try_files $uri =404;
    add_header Cache-Control "no-cache" always;
    add_header X-Content-Type-Options "nosniff" always;
}
```

目录合同：

```text
/srv/go-claw-updates/
  releases/<version>/latest.json
  releases/<version>/GO-CLAW-Update-<version>-setup.exe
  releases/<version>/GO-CLAW-Update-<version>-setup.exe.sig
  updates -> releases/<version>
```

- [x] 先将新版上传到 `releases/<version>` 并在服务器验 SHA-256/签名。
- [x] `nginx -t` 通过后 reload；静态 location 已生效，未发布时返回 404。
- [x] 用临时 symlink 和同文件系统 rename 原子替换 `updates`。
- [x] `https://goclaw.host:8443/updates/latest.json` 必须返回 200 和 JSON，不得再返回 New API HTML。

2026-08-28 现场结果：`updates -> releases/2.1.0`，公网 manifest 为 `2.1.0`；
更新 exe Range `0-1` 返回 `MZ` 且总长度为 `476989105`。生产 manifest 使用同域更新 URL。
GitHub Release `v2.1.0` 已发布；真实 v2.0.1 Windows 客户端端到端安装验收由用户执行。

## 9. P6：唯一签名 Main Build 和验收

### 9.1 前置条件

- [ ] P1 Tauri 内容就绪测试通过。
- [ ] P2 客户 UI、三档模型和每员工独立配置测试通过。
- [ ] P3 媒体相关单测和五次真实调用通过。
- [ ] `GO_CLAW_DASHSCOPE_API_KEY` 的当前值是低额度 New API key，且用它请求
  `https://goclaw.host:8443/v1/models` 可见七个必需模型；若不满足，只更新该 Secret 的值。
- [ ] 三处 updater 公钥一致，现有私钥签名探针通过。
- [ ] `/updates/` staging 已可用，但未切换生产 `latest.json`。
- [ ] 本地 `main`、`origin/main` 和要构建的 commit 一致。

### 9.2 唯一 run

```bash
gh workflow run desktop-build.yml --ref main -f ref=main -f windows_only=true
```

记录 run ID 并等待完成。失败后可以 rerun failed jobs，或修复后启动一个新候选；不并行启动两个正式候选。

下载 artifact 后验证：

- [ ] artifact 内恰好一个 `GO-CLAW-Windows-x64-Full.zip`。
- [ ] ZIP 有一个版本根，完整 Portable、WebView2、manifest 和 checksums 齐全。
- [ ] `credentials.json` 存在、可被应用导入、指向 `https://goclaw.host:8443/v1`，验收时不打印 key。
- [ ] ZIP 不包含 `provision.json`、HMAC、ticket 或签名私钥。
- [ ] installer/update `.sig`、`latest.json`、SHA-256 和入包公钥相互匹配。

### 9.3 Windows 验收

1. 正常 WebView2 终端：Auto 直接进入 Tauri，看到内容首帧；五名员工的档位互不影响。
2. 无/损坏 WebView2 终端：不出现永久空白；后端就绪后只打开一次系统浏览器；安装 ZIP 内 Evergreen 后重试进入 Tauri。
3. 人为令后端失败：显示 fatal UI/原生错误，不打开不可访问的浏览器。
4. 首次启动自动导入 Full ZIP 中的本地凭据；不出现激活、ticket 或 provisioning 交互。
5. 客户界面无“代码/模型/数字员工统计/文件/语言选择”入口，无非输入框闪烁 caret，字号图标和左下固定区符合设计。
6. 五个媒体工具各调用一次；界面/提示词不显示厂商和模型名，New API 记录命中 Token Plan 媒体渠道 3。
7. 从 staging 下载一次更新，完成验签、安装、自动重启和回滚；客户本地凭据未被更新包覆盖。

全部通过后才切换 `/srv/go-claw-updates/updates` 并发布 GitHub Release。Full ZIP 是首次交付和恢复产物；后续普通版本只发在线更新资产。

## 10. 总验证命令

```bash
uv run pytest -q tests/unit/plugins/test_media_openai_mode.py tests/unit/plugins/test_go_claw_media_plugins.py
uv run pytest -q tests/unit/app/test_go_claw_bundled_plugins.py tests/unit/app/test_go_claw_credentials.py tests/unit/app/test_go_claw_presets.py
uv run pytest -q tests/unit/agents/test_go_claw_presets.py tests/unit/branding/test_go_claw_customer_contract.py
uv run pytest -q tests/unit/scripts/test_stage_windows_portable.py tests/unit/scripts/test_windows_release_contract.py
npm --prefix console run format:check
npm --prefix console run test:run
npm --prefix console run build:prod
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo test --manifest-path console/src-tauri/Cargo.toml
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 .github/workflows/*.yml
git diff --check
```

完成标准是“要求的功能正常并有对应测试”，不是增加更多中间系统。

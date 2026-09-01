# GO CLAW 自动开通与 New API 凭据交付

> 当前代码实现：schema 1（2026-09-01 复核）。
>
> **v2.1.1 正式交付边界：** Main Full ZIP 只携带 `provision.json`，不得携带静态
> `credentials.json`。每块新盘首次启动时按 `instance.id` 换取独立的低额度 New API
> 凭据。在线更新包不包含 `GO-CLAW-Config`，不会覆盖已有实例的凭据。

## 1. 正式自动开通链路

Portable schema-1 链路是：

```text
客户首次启动
  → 生成并持久化 data/instance.id
  → 使用 provision.json 中的共享 HMAC 调用 POST /go-claw/provision
  → 服务端按 instance.id 创建或查询 New API 子用户和 token
  → 客户原子写入 GO-CLAW-Config/credentials.json
  → 批次凭据导入逻辑配置文字和媒体 provider
  → GET /api/console/quota 返回该实例的额度
```

关键文件和服务：

- 客户端：`src/qwenpaw/app/go_claw_provision.py`；
- 凭据导入：`src/qwenpaw/app/go_claw_credentials.py`；
- 额度代理：`src/qwenpaw/app/routers/quota.py`；
- 服务端代码：`/opt/go-claw-provisioning/provision_server.py`；
- systemd：`go-claw-provision.service`，监听 `127.0.0.1:9100`；
- 公网入口：`https://goclaw.host:8443/go-claw/provision`。

共享 HMAC 会随客户包分发，可以被提取，不能作为强身份凭证。v2.1.1 接受这个已知局限，
通过每实例低额度、服务端幂等和模型白名单限制影响面；本版本不扩建激活码、ticket DB 或
客户 ZIP sealing。后续若引入强授权，必须升级 schema，不能把共享 HMAC 描述为设备身份。

## 2. v2.1.1 Main Build 合同

GitHub Actions 只在构建时读取三个既有 Secret：

- `GO_CLAW_PROVISION_URL`：必须精确等于
  `https://goclaw.host:8443/go-claw/provision`；
- `GO_CLAW_PROVISION_HMAC_SECRET`：生成 Full ZIP 内的 `provision.json`；
- `GO_CLAW_DASHSCOPE_API_KEY`：只用于构建期七模型预检，不进入 Full ZIP。

Full ZIP 内的配置形状固定为：

```json
{
  "provisionUrl": "https://goclaw.host:8443/go-claw/provision",
  "hmacSecret": "<GO_CLAW_PROVISION_HMAC_SECRET>"
}
```

构建和发布 verifier 必须同时执行以下 fail-closed 规则：

- `Portable/GO-CLAW-Config/provision.json` 有且只有一份，字段只能是
  `provisionUrl` 和 `hmacSecret`；
- Full ZIP 中任何位置都不得出现 `credentials.json`；
- `MANIFEST.json` 使用 schema 3，明确记录 `containsCredentials=false`、
  `containsProvisioningConfig=true` 和 provisioning 配置 SHA-256；
- 便携包首次启动验证必须通过 `/api/console/quota`，并确认捆绑媒体插件已加载启用；
- 构建完成后清除工作区中的临时 `provision.json`，日志不得输出 Secret 或完整 JSON；
- 在线更新 payload 继续使用程序文件白名单，不包含 `GO-CLAW-Config`、`data`、`secrets`、
  `logs`、`cache`、`backups` 或 `updates`。

不得同时打包 `credentials.json` 和 `provision.json`。客户端发现现成
`credentials.json` 会跳过 provisioning，这种混装会让所有新盘继续共用静态 token，且
没有 `instance.id`，额度接口会返回未开通。

## 3. 文字模型

三档内部映射：

| 产品档位 | New API 模型 |
| --- | --- |
| 经济（默认） | `deepseek-v4-flash-0731` |
| 均衡 | `qwen3.7-plus` |
| 高性能 | `qwen3.8-max` |

客户前端不显示上表内部 ID。

## 4. 媒体链路

`src/qwenpaw/plugins/dashscope_credentials.py::resolve_media_api` 根据 endpoint host 选择协议：

| 凭据 endpoint host | 协议 | 图片 | 视频 |
| --- | --- | --- | --- |
| `*.aliyuncs.com` | DashScope 原生 SDK | 保留历史行为 | 保留历史行为 |
| 其他（GO CLAW New API） | OpenAI 兼容 | `POST /v1/images/generations` | `POST /v1/video/generations` + `GET .../{task_id}` |

v2.1.1 的插件兼容范围必须包含 host `2.1.1`，五个媒体工具的内部模型为：

| 能力 | 默认模型 |
| --- | --- |
| 图片生成/编辑 | `qwen-image-3.0-pro` |
| 文生视频 | `happyhorse-1.1-t2v` |
| 图生视频 | `happyhorse-1.1-i2v` |
| 参考图视频 | `happyhorse-1.1-r2v` |

生产 New API 渠道 1 `阿里百炼_TokenPlan_1` 承载文字兼容协议；渠道 3
`阿里百炼_TokenPlan_媒体` 仅承载四个媒体模型。客户端不修改公开 endpoint，不自动回退旧模型。

## 5. 2026-09-01 P0 回归与预防

旧 Main Full ZIP 只携带一份静态 `credentials.json`，没有 `provision.json`。在当天新拷贝的
G、F 产品盘上均复现出以下同根现象：

- 左下角额度条缺失，因为没有 `data/instance.id`，额度接口不能识别实例；
- 两个媒体插件 manifest 的 host 上限仍为 `2.1.0`，在 v2.1.1 上被判为不兼容；
- 对话因此看不到生图、生视频工具。

两块盘的现场修复均保留备份后补入 provisioning 配置、提升媒体插件兼容范围并重新启动；
额度接口、两个媒体插件、五个员工随后恢复。正式构建通过以下门禁避免复发：

1. 打包阶段拒绝静态凭据与 provisioning 混装；
2. Full ZIP verifier 校验 schema 3 和 provisioning 文件哈希；
3. 桌面运行验证硬性请求额度接口；
4. 插件运行验证硬性确认图片和视频插件均 `loaded=true`、`enabled=true`；
5. 媒体插件升级使用原子写入，避免旧盘残留旧 manifest。

本 P0 是“新盘完整包交付”问题，不等同于 v2.0.1 → v2.1.1 在线更新事务事故；后者仍按
`GO-CLAW-v2.1.1-Windows在线更新调试交接.zh.md` 的门禁独立处理。

## 6. 安全与运维检查

- [x] 本地 `credentials.json`、`provision.json`、`.env`、`provision.db` 被 `.gitignore` 覆盖。
- [x] 客户凭据不是 New API 管理员令牌。
- [x] Full ZIP 不携带静态 New API key 或签名私钥。
- [x] Full ZIP 携带的共享 HMAC 被明确记录为可提取、非强身份凭证。
- [x] `GO_CLAW_DASHSCOPE_API_KEY` 只用于构建期模型预检，不写入客户包。
- [x] 在线更新包使用白名单 payload，不包含或覆盖客户本地凭据和 provisioning 配置。
- [ ] 正式 Windows CI 运行需记录 run ID、commit SHA 和 Full ZIP artifact；未通过前不得把本次
  构建合同写成已发布版本。

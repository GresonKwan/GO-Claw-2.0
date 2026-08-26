# GO CLAW 自动开通与 New API 凭据交付

> 当前代码实现：schema 1（2026-08-26 复核）。
>
> **v2.1 发布边界：** 本页记录已存在的 HMAC 自动开通机制，供历史客户和运维查阅。
> v2.1 Main Build 不改造它、不依赖它：正式 Full ZIP 直接携带用户已接受的低额度
> `credentials.json`，不携带 `provision.json`、共享 HMAC、激活码或 enrollment ticket。

## 1. 历史自动开通现状

已存在的 Portable schema-1 链路是：

```text
客户首次启动
  → 生成 data/instance.id
  → 使用 provision.json 中的共享 HMAC 调用 POST /go-claw/provision
  → 服务端创建/查询 New API 子用户和 token
  → 客户写入 GO-CLAW-Config/credentials.json
  → 批次凭据导入逻辑配置文字和媒体 provider
```

关键文件和服务：

- 客户端：`src/qwenpaw/app/go_claw_provision.py`；
- 凭据导入：`src/qwenpaw/app/go_claw_credentials.py`；
- 服务端代码：`/opt/go-claw-provisioning/provision_server.py`；
- systemd：`go-claw-provision.service`，监听 `127.0.0.1:9100`；
- 公网入口：`https://goclaw.host:8443/go-claw/provision`。

共享 HMAC 可以从客户包中提取，不是强身份凭据。这是历史机制的已知局限，不在 v2.1 中通过新激活系统扩建。

## 2. v2.1 Main Build 凭据合同

v2.1 沿用已实现的 `credentials.json` schema 1 和一次性导入 marker。Main Build 只使用
已存在的 GitHub Secret `GO_CLAW_DASHSCOPE_API_KEY`，将同一个低额度 New API key
写入文字和媒体凭据字段：

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

规则：

- 不新增 `GO_CLAW_LLM_API_KEY`；
- 不新增 `GO_CLAW_CI_TEST_API_KEY`；
- desktop-build 不生成 `provision.json`；
- Full ZIP 中必须有且只有一份 `Portable/GO-CLAW-Config/credentials.json`；
- 在线更新 payload 不包含 `GO-CLAW-Config`，不覆盖客户已导入的 key；
- 验证脚本可检查 JSON schema、URL 和 key 形式，但不得输出 key 或完整 JSON。

## 3. 文字模型

三档内部映射：

| 产品档位 | New API 模型 |
| --- | --- |
| 经济（默认） | `deepseek-v4-flash-0731` |
| 均衡 | `qwen3.7-plus` |
| 高性能 | `qwen3.8-max` |

客户前端不显示上表内部 ID。

## 4. 媒体链路

`src/qwenpaw/plugins/dashscope_credentials.py::resolve_media_api` 已根据 endpoint host 选择协议：

| 凭据 endpoint host | 协议 | 图片 | 视频 |
| --- | --- | --- | --- |
| `*.aliyuncs.com` | DashScope 原生 SDK | 保留历史行为 | 保留历史行为 |
| 其他（GO CLAW New API） | OpenAI 兼容 | `POST /v1/images/generations` | `POST /v1/video/generations` + `GET .../{task_id}` |

v2.1 保留上表已工作路径、请求体和响应解析，只替换插件内部默认模型：

| 能力 | 默认模型 |
| --- | --- |
| 图片生成/编辑 | `qwen-image-3.0-pro` |
| 文生视频 | `happyhorse-1.1-t2v` |
| 图生视频 | `happyhorse-1.1-i2v` |
| 参考图视频 | `happyhorse-1.1-r2v` |

生产 New API 渠道 1 `阿里百炼_TokenPlan_1` 已是 OpenAI 类型并列出上述媒体模型。
v2.1 不新建媒体渠道，不修改 New API 镜像或 adapter，不修改媒体 endpoint，不自动回退旧模型或百炼直连。

## 5. 安全与运维边界

- [x] 本地 `credentials.json` / `provision.json` / `.env` / `provision.db` 被 `.gitignore` 覆盖。
- [x] 客户凭据不是 New API 管理员令牌。
- [x] 用户已接受低额度 API key 保存在客户本地 Full ZIP 中。
- [ ] v2.1 Main ZIP 不包含 `provision.json`/共享 HMAC/ticket/签名私钥。
- [ ] 在线更新包继续使用白名单 payload，不包含或覆盖客户本地凭据。

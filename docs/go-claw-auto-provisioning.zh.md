# GO CLAW 自动开通与 NewAPI 计费体系

> 版本：2026-08-19 · 适用于 GO CLAW Portable 2.0.1+（Windows）

本文档描述 GO CLAW 便携版的**首次启动自动开通**机制：客户双击软件即自动获得
专属的 NewAPI 子用户与带赠送额度的 API Key，无需任何手动配置。

## 架构总览

```
客户便携包（首次启动，联网）                运营服务器（与 NewAPI 同机）
  data/instance.id (UUID)                  scripts/provisioning 服务
       │ HMAC 签名请求                        │ 验签 / 时间窗 / IP限流
       ├──────────────────▶ POST /go-claw/provision（nginx 重写为 /api/provision）
       │                                     │ 幂等查询（SQLite）
       │                                     ├─▶ NewAPI 建子用户 gc-xxxxxxxx-yyyy
       │                                     ├─▶ 签发不限额令牌 go-claw-auto
       │                                     └─▶ DB 直读完整 Key + 写用户额度
       │ ◀────────────────── 返回 credentials.json 内容
       ▼
  写入 GO-CLAW-Config/credentials.json
  → 现有批次导入机制同次启动完成配置（LLM + 媒体工具 + 默认模型）
```

- **实例绑定**：instance.id 在客户端首次启动时生成（非打包时），同一 U盘
  拷贝永远拿回同一份凭证；激活后整体复制 U盘则副本共享同一子用户与额度。
- **防刷**：HMAC 签名（密钥随包分发，可被提取，仅第一道闸）+ 每 IP 每日
  限流 + 赠送额度较小 + 后台可随时禁用异常子用户。
- **失败自愈**：开通失败不阻塞启动；因未写导入标记，下次启动自动重试。

## 链路细节

### LLM 聊天

- 借用内置 `deepseek` provider（OpenAI 兼容、base_url 可改）的壳接 NewAPI；
  导入时若 modelId 不在内置模型表，自动注册进 `extra_models`。
- 当前默认模型：`qwen3.7-plus`（服务端 `CHAT_MODEL_ID` 可改）。

### 媒体工具（图像/视频）

NewAPI **不透传** DashScope 原生路径（`/api/v1/services/aigc/*`），因此媒体
插件已改写为双协议（`src/qwenpaw/plugins/dashscope_credentials.py` 的
`resolve_media_api`）：

| 凭证端点 host | 协议 | 图像 | 视频 |
|---|---|---|---|
| `*.aliyuncs.com`（百炼官方） | DashScope 原生 SDK | 不变 | 不变 |
| 其他（NewAPI 中转） | OpenAI 兼容 | `POST {root}/v1/images/generations` | `POST {root}/v1/video/generations` + `GET .../{task_id}` 轮询 |

默认模型：生图 `qwen-image-2.0`；生视频按工具分别为 `wan2.7-t2v` /
`wan2.7-i2v` / `wan2.7-r2v`（图生视频传 `image` 字段，参考生视频多张图
放 `metadata.images`）。

### NewAPI 侧必备配置

1. 渠道 base_url 填**域名根**（不带 `/compatible-mode`），类型用阿里百炼；
   图像/视频模型须在建模列表与 abilities 中（后台改模型列表会自动维护）。
2. `设置 → 模型价格`（ModelPrice）为按次计费模型配价，否则调用报
   "模型价格尚未配置"。当前配置：图像 $0.03–0.08/次，视频 $0.10–0.12/次。
3. 子用户额度与令牌额度**双重检查**：消耗同时扣用户 quota 和令牌
   remain_quota，provisioning 服务两边都会写入赠送额度。

## 服务端部署

见 `scripts/provisioning/README.md`。关键件：

- 服务：`/opt/go-claw-provisioning/`（systemd: `go-claw-provision.service`）
- 公网入口：nginx `location = /go-claw/provision` → `proxy_pass http://127.0.0.1:9100/api/provision`（公网路径与服务端路由的映射靠这条重写，二者不可互换）
- 服务器机密（权限 600，勿外泄）：`/root/.newapi_admin_token`、
  `/root/.go-claw-hmac-secret`

## 打包与 CI

- 构建机/CI 通过 GitHub Secrets 注入 `GO_CLAW_PROVISION_URL` 与
  `GO_CLAW_PROVISION_HMAC_SECRET`，工作流（desktop-build /
  desktop-portable-reverify）自动生成 `GO-CLAW-Config/provision.json`
  打入 ZIP；该文件被 `.gitignore` 忽略，永不入仓库。
- 若同时存在旧版共享 `credentials.json`（secrets `GO_CLAW_LLM_API_KEY` 等），
  批次凭证优先，自动开通会跳过。新交付建议只配 provision 两个 secret。

## 安全清单

- [x] `credentials.json` / `provision.json` / `.env` / `provision.db` 均已
      被 .gitignore 覆盖，且从未进入 git 历史
- [x] 交付物只含 HMAC 密钥；NewAPI 管理员令牌不出服务器
- [x] 赠送额度仅受用户账号额度约束（令牌自 8561e1d 起默认不限额；令牌层可在 NewAPI 后台单独限额）
- [ ] 建议定期轮换 HMAC 密钥与管理员令牌（轮换后需重新出包）

# GO CLAW 变更台账（单一事实源）

> 本文件是 GO CLAW 二次开发所有变更的**唯一权威记录**。规则见 `GO-CLAW-文档规范.zh.md`。
> 每条条目：改动内容 / 原因 / commit / 验证方式 / 关联文档。
> 基线：QwenPaw v2.0.1（`24813b3` 导入）。文档目录见文末索引。

---

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
| 建立变更台账与文档规范，旧 plan 补状态标记 | 规范化（用户要求） | f4d93e9 |

## 运营侧变更（非代码，无 commit）

| 日期 | 变更 | 原因 |
|------|------|------|
| 08-20 | New API 渠道 #1 上游 TokenPlan 周配额耗尽（08-24 04:07 UTC 重置）；`deepseek-v4-flash` 模型名与渠道 `deepseek-v4-flash-0731` 不匹配 | 供应商侧，待续费/补模型名 |
| 08-21 | 4 个存量 `go-claw-auto` 令牌 DB 直改 `unlimited_quota=1`；管理员 access token 过期导致 provisioning 502，已同步 `.env` 并重启服务；仓库转 public 用免费 Actions 额度 | 现场修复 |

---

## 文档索引（唯一索引，新增文档必须登记）

| 文档 | 角色 |
|------|------|
| 本文件 | 变更唯一事实源 |
| `GO-CLAW-文档规范.zh.md` | 文档编写与维护规则 |
| `go-claw-auto-provisioning.zh.md` | 开通/计费专题（持续更新） |
| `superpowers/specs/*`、`plans/*` | 设计规格与实施计划（带状态标记） |
| 工作区 `GO-CLAW-debug计划.md`、`GO-CLAW-修改计划.md` | 现场排查原始记录（快照，不再更新） |

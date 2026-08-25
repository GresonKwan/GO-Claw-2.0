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
| test_offload_while_running 在 Windows 隔离（skipif win32） | 同一机制的其他用例在 Windows 全过，仅此用例 entry 永不出现；无 Windows 环境可调试，功能在 mac/Linux 有覆盖 | 3526338 | 标注待有 Windows 环境后复查 |
| 建立变更台账与文档规范，旧 plan 补状态标记 | 规范化（用户要求） | f4d93e9 |

## 2026-08-24 · 产品迭代：侧边栏精简

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 侧边栏隐藏 11 个专业/低频入口（工具/MCP/ACP/心跳/环境变量/安全/Token消耗/备份/语音转写/调试/插件管理），路由保留 | 非技术客户精简界面 | 5103c4bd | console/src/layouts/registry/builtinMenu.test.ts |
| 侧边栏左下角逐增额度进度条（仅百分比，低额度变红）+ provisioning /api/quota + 后端代理 /api/console/quota；数值=剩余÷签发额（clamp 0-100） | 客户对剩余额度无感知 | 8458ddfe | test_provision_server.py +3 / test_quota_router.py +3 / QuotaBar.test.tsx +3 |

关联计划：`docs/superpowers/plans/2026-08-24-go-claw-sidebar-quota.md`

## 2026-08-25 · 产品迭代：界面精简第 2 轮 + 模型可用性

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 隐藏侧边栏"运行配置"入口（同第一轮机制） | 非技术客户精简界面 | 82ada36c | builtinMenu.test.ts |
| 隐藏对话下方 Loop 模式选择器，固定默认模式 | 客户无需理解模式 | 82ada36c | 前端全套件 |
| 额度条去掉悬停金额 tooltip，只留进度条+百分比 | 用户要求 | 82ada36c | QuotaBar.test.tsx |
| 模型选择器：跨 provider 按 id 去重 + GO CLAW 可用模型白名单（deepseek-v4-pro/v4-flash/qwen3.7-max/qwen3.7-plus/glm-5.2/qwen3.6-flash/qwen3.8-max）+ 移除 FREE 页签 | 重复选项、不可用选项必 503 | 82ada36c | ModelSelector.test.tsx 12 例 |
| 空响应根治：取消路径改发 turn_interrupted 错误信封（"本轮对话已停止"） | cancel 产出 Completed+空 output 与空成功无法区分 | 82ada36c | envelope 既有测试 + retry_chat_model 测试 |
| extra_models 追加去重结论：has_model 已覆盖目录+extra，现有逻辑天然去重，无需改动 | 评估后关闭 | — | — |

## 2026-08-25 · 审查修复批次（全项目 review 后）

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 交付模型默认改 `deepseek-v4-flash`（服务器 .env + provision_server 默认值 + .env.example + 文档） | 交付模型须在白名单内，解决选择器空列表风险 | 9b8c6750 | 服务器已重启生效 |
| 模型白名单零命中兜底（回退去重后全量）+ 去重时已配置 provider 优先 | H1 解耦兜底 / H2 顺序隐患 | 9b8c6750 | ModelSelector.test.tsx |
| 额度语义：`granted = 剩余 + 累计净消耗`（NewAPI 数据恒等式，严格覆盖充值；弃用初版 max(签发,剩余) 近似） | 进度条严格反映 New API 实际额度 | 61647c04 | test_provision_server.py（含 quota_data）+ 服务器实测 granted=$8.00/percent=76（已部署） |
| 微信扫码仅首次配置时强制 enabled | 不覆盖既有用户的启用选择；表单其它字段随提交保存 | 9b8c6750 | ChannelDrawer 逻辑审查 |
| runtime 注释与实现对齐、额度条瞬态失败防闪烁、simple 白名单清理、删除 LoopInput 死代码 | 卫生 | 9b8c6750 | tsc + 前端 1203 全量 |
| 在线更新计划并入 11 条审查修正（白名单打包防凭证泄露、portable.json 兼容、自装路径改道、三处密钥一致、缓存迁移、回滚独立通道、/D= 安全拼接、发布架构、安装锁、国内镜像、CI 共存） | review 抓出的硬伤/泄露风险 | — | docs/superpowers/plans/2026-08-25-go-claw-online-update.md 第六节 |

## 2026-08-26 · 在线更新系统实施

| 改动 | 原因 | commit | 验证 |
|------|------|--------|------|
| 在线更新全链路：后端 Python 编排（go_claw_updates.py + /api/updates/* 路由 + 6h 定时检测）、minisign/Ed25519 验签、NSIS 更新包（白名单+备份+锁+自动重启）、CI 构建/签名/manifest/发布、前端版本区块（检查/下载/一键安装/历史回滚）、公钥随包分发 | 客户一键更新到新版本 | （待推送） | test_go_claw_updates.py（验签往返+篡改拒绝）、tsc、前端全量、pre-commit 全钩子 |
| Rust 侧：portable.json updates 字段（serde default 兼容）、便携放行、安装 /D= raw_arg 安全拼接、缓存迁便携根、install_update_from_url 回滚命令 | 便携模式兼容 | （待推送） | cargo check |
| 修正：更新编排从 Rust 改为 Python（便携浏览器模式无 Tauri IPC） | 架构事实 | — | — |

## 运营侧变更（非代码，无 commit）

| 日期 | 变更 | 原因 |
|------|------|------|
| 08-20 | New API 渠道 #1 上游 TokenPlan 周配额耗尽（08-24 04:07 UTC 重置）；`deepseek-v4-flash` 模型名与渠道 `deepseek-v4-flash-0731` 不匹配 | 供应商侧，待续费/补模型名 |
| 08-21 | 4 个存量 `go-claw-auto` 令牌 DB 直改 `unlimited_quota=1`；管理员 access token 过期导致 provisioning 502，已同步 `.env` 并重启服务；仓库转 public 用免费 Actions 额度 | 现场修复 |
| 08-25 | deepseek-v4-flash 不可用三层修复：渠道 #1 models 名单补名 + `abilities` 表补路由行 + `options.ModelRatio` 补定价 0.25 + `model_mapping` 映射到 deepseek-v4-flash-0731（上游只认带日期型号）；实测 chat completion 200 | 模型选择器调用必 503 |
| 08-25 | provisioning 服务器 `CHAT_MODEL_ID` 由 qwen3.7-plus 改为 `deepseek-v4-flash` 并重启；服务端 quota 语义更新已部署 | 交付模型与白名单对齐 / 充值语义 |

---

## 文档索引（唯一索引，新增文档必须登记）

| 文档 | 角色 |
|------|------|
| 本文件 | 变更唯一事实源 |
| `GO-CLAW-文档规范.zh.md` | 文档编写与维护规则 |
| `go-claw-auto-provisioning.zh.md` | 开通/计费专题（持续更新） |
| `superpowers/specs/*`、`plans/*` | 设计规格与实施计划（带状态标记） |
| 工作区 `GO-CLAW-debug计划.md`、`GO-CLAW-修改计划.md` | 现场排查原始记录（快照，不再更新） |

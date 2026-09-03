# GO CLAW “算力充值”实施计划

日期：2026-09-03
状态：Phase 1 已落地，生产开关保持关闭；等待合规、安全、耐久仓储与真实微信 staging 评审
设计：`../specs/2026-09-03-go-claw-compute-recharge-design.md`

当前代码落地范围（2026-09-03）：合同与初始 migration 镜像、整数金额/账本域模型、fake
provider、NewAPI 结果分类、存量 challenge/proof enrollment、本地凭据隐藏代理、侧边栏页面、
本地二维码、额度刷新事件、systemd/Nginx 模板及针对性测试。非 development 模式在耐久
PostgreSQL repository 启用前主动拒绝启动，`GO_CLAW_BILLING_ENABLED` 默认关闭。

尚未完成且不得据此上线：Task 0 审批、完整 PostgreSQL repository/outbox/inbox/audit 实现、
微信 Native 下单与回调持久事务、退款/补偿/对账 worker、故障注入、CI 全量门禁、真实商户
staging、7 天对账和灰度发布。本次落地没有修改生产更新源、公开 Release 或服务器配置。

## 1. 实施原则

1. 从 GO CLAW 当前最新工作分支创建 `codex/compute-recharge`，不向 QwenPaw 源项目提交 PR。
2. feature flag `GO_CLAW_RECHARGE_ENABLED=false` 默认关闭；关闭建单不影响回调、查单、到账和退款 worker。
3. 先完成 fake provider、账本和故障注入，再接真实微信商户配置。
4. 任何生产密钥只通过部署环境注入，不写入仓库、ZIP、日志、测试快照或 GitHub Actions artifact。
5. 三种单位严格分离并只使用整数：`display_compute_units = amount_fen * 50_000`，`newapi_quota_units = amount_fen * 750`；客户 API 不暴露 NewAPI 原始单位。
6. 支付、账本、NewAPI 三层状态分离；前端不自行推断“已付款”或“已到账”。
7. NewAPI 结果不确定时 fail closed，不盲目重试。

## 2. Task 0：审批与测试资源

交付物：填写完成的上线前置表，不改生产配置。

- [x] 产品参数：单笔 ￥1–￥100,000、最多两位小数；快捷金额 ￥10/￥50/￥100/￥200；用户展示“￥1对应500万算力”；
- [x] 项目负责人确认微信支付商户已经开通；
- [ ] 联系项目负责人核验实际经营主体、微信商户号、绑定 appid、Native 支付权限和证书方案；
- [ ] 创建独立测试 merchant/config 或受控小额测试流程；
- [ ] 财务确认每日累计风控上限、发票和退款策略；
- [ ] 法务审阅 `docs/contracts/compute-recharge/GO-CLAW算力充值服务条款模板.zh-CN.md`；
- [ ] 安全确认 KMS/Vault/systemd credential 方案；
- [ ] 运维确认 PostgreSQL、PITR、异地 WORM 存储和告警通道；
- [ ] 产品确认首期是否接受 NewAPI ambiguous result 人工复核。

退出条件：上述负责人、日期和结论都有记录；未完成不得开启生产 feature flag。

## 3. Task 1：锁定并验证合同

文件：

- `docs/contracts/compute-recharge/openapi.yaml`
- `docs/contracts/compute-recharge/provisioning-enrollment.openapi.yaml`
- `docs/contracts/compute-recharge/events.schema.json`
- `docs/contracts/compute-recharge/ledger.postgresql.sql`
- `docs/contracts/compute-recharge/GO-CLAW算力充值服务条款模板.zh-CN.md`

步骤：

1. 在 CI 增加 OpenAPI 3.1 lint；
2. 使用 Draft 2020-12 validator 校验事件 schema；
3. 在临时 PostgreSQL 16 执行 schema；
4. 写 migration smoke：全新安装、升级、重复执行、失败回滚；
5. 增加 breaking-change 检查；
6. 固定 v1 兼容规则：只加 optional 字段，删除/重命名/收窄枚举必须升主版本。

测试：

```powershell
python -m json.tool docs/contracts/compute-recharge/events.schema.json
python -m pytest scripts/billing/tests/test_contracts.py -q
npm --prefix console run lint
```

退出条件：两份 OpenAPI、事件 Schema 和账本 SQL 均可机器校验，服务条款通过业务/法务评审，CI 不依赖生产配置。

## 4. Task 2：Billing Service 骨架

新增目录：

```text
scripts/billing/
  pyproject.toml
  go_claw_billing/
    __init__.py
    app.py
    config.py
    domain/
      money.py
      orders.py
      ledger.py
      adjustments.py
      refunds.py
    application/
      order_service.py
      payment_service.py
      quota_service.py
      refund_service.py
      reconciliation_service.py
    adapters/
      postgres.py
      wechatpay.py
      newapi.py
      archive.py
    api/
      customer.py
      webhooks.py
      admin.py
    workers/
      outbox.py
      payment_recovery.py
      quota.py
      refunds.py
      reconciliation.py
  migrations/
  tests/
```

实现：

- Pydantic Settings 在进程启动时 fail closed 检查必填配置；
- `/health/live` 不访问下游，`/health/ready` 检查 DB 与必要配置；
- JSON 日志统一 `trace_id/order_id/account_id/error_code`，内置 token、签名、二维码和 PII 脱敏；
- request body 限制、超时、连接池、graceful shutdown；
- domain 层不得 import FastAPI、httpx 或数据库实现。

首批测试：配置缺失拒绝启动、日志脱敏、健康检查、整数溢出。

## 5. Task 3：PostgreSQL 账本与仓储

基于 `ledger.postgresql.sql` 创建版本化迁移，禁止应用启动时自动猜测迁移。

实现方法：

- `OrderRepository.create_idempotent()`；
- `InboxRepository.insert_once()`；
- `OutboxRepository.claim_batch()` 使用 `FOR UPDATE SKIP LOCKED`；
- `LedgerRepository.post_balanced_journal()` 一次事务写 entry + lines；
- `QuotaAdjustmentRepository.claim_for_user()` 保证每用户串行；
- `AuditRepository.append()` 维护 HMAC hash chain；
- `PricingRepository.get_active(at)` 返回唯一有效版本。

强制测试：

- journal 少于两行、借贷不平、跨资产抵消均失败；
- UPDATE/DELETE journal 与 audit 失败；
- reversal 只能创建一次；
- 相同 `(account_id, operation, idempotency_key)` 同 body 返回原结果；
- 同 key 异 body 返回 409；
- 100 并发创建只有一个 `out_trade_no`；
- `amount_fen * display_compute_units_per_fen` 与 `amount_fen * newapi_quota_units_per_fen` 分别做 checked int64，任一溢出都拒绝；
- pricing policy 强制 `min=100`、`max=10_000_000`、`step=1`、`presets=[1000,5000,10000,20000]` 分，金额越界或人民币输入超过两位小数均拒绝；
- 客户 DTO/日志/页面快照中不存在 NewAPI 原始 quota unit 或美元展示字段。

## 6. Task 4：计费账户与 provisioning schema 2

修改：

- `scripts/provisioning/provision_server.py`
- `scripts/provisioning/test_provision_server.py`
- `src/qwenpaw/app/go_claw_provision.py`
- `tests/unit/app/test_go_claw_provision.py`

新增：

- `src/qwenpaw/app/go_claw_billing.py`
- `tests/unit/app/test_go_claw_billing.py`

服务端：

1. 新实例完成 NewAPI user/token 后调用 Billing internal enrollment；
2. Billing 生成 token format `gcb_live_<token_id>_<secret>`；
3. 独立 `billing_access_token` 表保存 `token_id + account_id + Argon2id(secret) + version/status`，明文只返回给本地后端；
4. provisioning 返回 schema 2 envelope；
5. 存量实例提供一次性 challenge/proof-of-possession；
6. challenge 5 分钟过期、单次使用、绑定 instance；合法 completion 为现有 account 签发一个 `ISSUED` token，首次鉴权转 `ACTIVE`，未使用 24 小时失效；响应丢失时客户端用新 challenge 自动重试，不撤销仍可用的旧 token。

老用户 enrollment 使用 `provisioning-enrollment.openapi.yaml` 的两个独立端点。challenge 端点不依赖 `provision.json` 中的 shared HMAC，避免早期静态凭据产品盘无法升级；proof 必须由既有 NewAPI 子 token 计算。客户端从随代码发布的非秘密 billing bootstrap 配置读取 URL，该配置不得包含任何 shared secret。

客户端：

1. 保持 `BatchCredentials` schema 1 不变；
2. 新建严格 `BillingProfile`；
3. envelope 完整验证后分别原子写 credentials 与 billing profile；
4. 任一写入失败回滚本轮临时文件，下次启动可恢复；
5. 在线更新不覆盖 `data/.go-claw-billing.json`；
6. 日志只记录 account id 的短前缀，不记录 token。

老用户无感迁移约束：

- `ensure_billing_enrollment()` 在既有启动链路完成后异步运行，不能阻塞聊天、员工、模型、额度条或升级成功页；
- enrollment 必须复用 `instance_id → newapi_user_id`，禁止创建新 NewAPI 用户、覆盖原 token/quota 或迁移聊天记录；
- 失败状态仅禁用充值建单，后台对可重试错误退避，身份冲突进入人工处理；
- 新 token 首次成功鉴权前不吊销旧 token；更新与回滚均保留 billing profile；
- 服务端唯一约束和幂等 enrollment 保证并发启动只生成一个 Billing account。

兼容测试：旧 schema 1 仍能启动；schema 2 双写成功；v2.0.1/v2.1.1 干净与真实数据副本升级；截断文件、掉电模拟、服务端不可用、错误 token、challenge 重放和并发启动均不影响原有功能。

## 7. Task 5：微信支付适配器

文件：

- `scripts/billing/go_claw_billing/adapters/wechatpay.py`
- `scripts/billing/go_claw_billing/api/webhooks.py`
- `scripts/billing/tests/test_wechatpay_adapter.py`
- `scripts/billing/tests/test_wechatpay_webhooks.py`

接口：

- Native 下单 `POST /v3/pay/transactions/native`；
- 商户订单号查单；
- 关单；
- 申请退款；
- 查询退款；
- 下载交易/退款账单。

验签顺序：读取 raw bytes → 校验 headers/时间窗 → 按 serial 选公钥 → RSA-SHA256 验签 → AES-256-GCM 解密 → 严格 DTO → 核对商户/订单/金额 → 事务入 inbox。

测试 fixture 必须覆盖：

- 正确签名；
- body 任意字节改变后验签失败；
- 错 serial、错 nonce、过期 timestamp；
- `WECHATPAY/SIGNTEST/` 签名探测；
- event 重放；
- 商户号、appid、订单号、金额、币种不一致；
- 回调事务失败返回 500，成功或重复返回 204；
- 日志不含 ciphertext 解密后的 payer 标识。

## 8. Task 6：订单服务与客户 API

实现 `openapi.yaml` 中：

- `GET /v1/config`；
- `GET /v1/balance`；
- `POST /v1/orders`；
- `GET /v1/orders/{id}`；
- `POST /v1/orders/{id}/close`；
- `GET /v1/orders`；
- `GET /v1/ledger`。

建单事务：

1. 鉴权 billing token；
2. 执行频率限制；每日累计风控值非空时再执行每日限额；
3. 锁定有效 pricing policy；
4. 拒绝 `<100` 或 `>10_000_000` 分，人民币字符串解析超过两位小数时前端拒绝；客户端提交的展示/内部额度字段一律拒绝；
5. 同时计算 `checked_int64(amount_fen * 50_000)` 和 `checked_int64(amount_fen * 750)`；
6. 保存订单、双单位快照、terms version 和 idempotency request hash；
7. 事务外调用微信 Native 下单；
8. 保存 code_url 加密值与过期时间；
9. 客户 DTO 只返回 `computeUnits`，不返回美元和 `newapiQuotaUnits`。

如果服务在“微信下单成功、保存 code_url 前”崩溃，使用同一 `out_trade_no` 向微信查单并恢复，不创建第二个订单号。

## 9. Task 7：付款入账与配额 outbox

支付确认事务必须一次完成：

1. 锁定 `payment_order`；
2. 检查当前状态；
3. 唯一写 `wechat_transaction_id`；
4. 设置 `PAID`；
5. 创建 CNY_FEN 双分录 journal；
6. 创建 CREDIT `quota_adjustment`；
7. 写 `quota.adjustment.requested` outbox；
8. 提交后才返回微信 204。

重复回调测试 100 次，断言 payment state、journal、adjustment、outbox 各只有一份。

## 10. Task 8：NewAPI Adapter

文件：

- `scripts/billing/go_claw_billing/adapters/newapi.py`
- `scripts/billing/go_claw_billing/workers/quota.py`
- `scripts/billing/tests/test_newapi_adapter.py`
- `scripts/billing/tests/test_quota_worker_faults.py`

调用固定生产基线：

```json
{"id": 123, "action": "add_quota", "mode": "add", "value": 75000}
```

退款撤回使用 `mode=subtract`。target `id` 只从 `billing_account.newapi_user_id` 读取。

错误分类：

- `SAFE_RETRY`：DNS、TCP connect 被拒、请求未发送；
- `DEFINITE_FAILURE`：已收到可验证 4xx/业务失败响应；
- `DEFINITE_SUCCESS`：已收到严格校验的成功响应；
- `AMBIGUOUS`：write 后 timeout/EOF、响应无法解析、worker crash recovery 发现 APPLYING。

`AMBIGUOUS` 必须进入 `REVIEW_REQUIRED` 并 P0 告警。运维 resolution API 仅允许双人复核后执行：

- `confirm_applied`：只补 Billing journal，不再调用 NewAPI；
- `allow_retry`：生成新 attempt，保留旧证据；
- `reverse_and_refund`：走正式退款状态机。

## 11. Task 9：查单、关单与日终对账 worker

新增 worker：

- payment recovery：补丢回调；
- expiry closer：先查单后关单；
- quota recovery：处理 QUEUED 与明确可重试失败；
- refund worker：先撤额度再申请退款；
- daily reconciliation：微信账单、Billing ledger、NewAPI 审计三方核对；
- archive worker：签名日根并写 WORM。

故障注入点：每次外部调用前后、每个 DB commit 前后、响应解析前后强制 crash。重启后验证无丢单、无重复 journal、无重复加额。

## 12. Task 10：本地 FastAPI 代理

新增：

- `src/qwenpaw/app/routers/recharge.py`
- `tests/unit/app/routers/test_recharge_router.py`

修改：

- `src/qwenpaw/app/routers/__init__.py`

规则：

- 非 portable、无 billing profile 或 profile 损坏返回 404/明确未开通状态；
- billing token 只在后端 Authorization header 中使用；
- 浏览器输入不能覆盖 base URL、account id 或 NewAPI user id；
- 上游超时映射为稳定错误码，不透传 body；
- 订单查询只能访问当前 billing account；
- 设置 10 秒普通请求、20 秒建单超时；
- 使用 bounded response body，拒绝非 JSON 和超大 body。

## 13. Task 11：前端页面

修改：

- `console/src/layouts/registry/builtinMenu.ts`
- `console/src/layouts/registry/builtinRoutes.tsx`
- `console/src/layouts/QuotaBar.tsx`
- `console/src/locales/zh.json`
- `console/src/locales/en.json`
- `console/package.json`
- 对应 lockfile

新增：

- `console/src/api/modules/recharge.ts`
- `console/src/pages/Settings/ComputeRecharge/index.tsx`
- `console/src/pages/Settings/ComputeRecharge/index.module.less`
- `console/src/pages/Settings/ComputeRecharge/components/BalanceCard.tsx`
- `console/src/pages/Settings/ComputeRecharge/components/AmountCard.tsx`
- `console/src/pages/Settings/ComputeRecharge/components/NativePayModal.tsx`
- `console/src/pages/Settings/ComputeRecharge/components/LedgerTable.tsx`
- 对应 `*.test.tsx`

关键断言：

- menu 位于 settings order 5，精简/完整模式均显示；
- 标题区固定展示“￥1对应500万算力”，页面不展示美元或 NewAPI quota unit；
- 快捷按钮严格为 ￥10/￥50/￥100/￥200，只填充、不自动提交；
- 自定义金额接受 ￥1–￥100,000、最多两位小数；输入千分位只用于显示，请求使用分整数；
- UI 只提交 amountFen 与条款版本，不提交任何展示或内部额度；
- QR 完全本地生成且仅接受 `weixin://`；
- 同一次点击只生成一个 idempotency key；网络重试复用该 key；
- `CREDITING` 显示“已付款，额度同步中”；
- `SUCCEEDED` 停止轮询并触发 `go-claw:quota-updated`；
- `QuotaBar` 收到事件立即调用 `getQuota()`；
- 页面卸载清除 timer 和 listener；
- billing enrollment 未就绪时显示初始化/重试状态，但不得影响侧栏其他入口和主应用；
- keyboard、screen reader、色彩对比与窄屏布局通过。

## 14. Task 12：部署与硬化

新增：

- `deploy/systemd/go-claw-billing.service`
- `deploy/nginx/go-claw-billing.conf`
- `scripts/billing/README.md`
- `scripts/billing/.env.example`，只列键名和占位符

systemd：

- 独立非登录用户；
- `NoNewPrivileges=true`；
- `PrivateTmp=true`；
- `ProtectSystem=strict`；
- `ProtectHome=true`；
- `ReadWritePaths` 仅必要运行目录；
- secrets 使用 `LoadCredential=`；
- 限制 capability、syscall、文件描述符与内存；
- worker 与 API 可拆服务，均有 restart/backoff。

Nginx：

- 只暴露精确 billing 与 webhook location；
- webhook body 上限和独立 access log 脱敏；
- 客户 API rate limit；
- internal 路径公网直接 404；
- TLS/HSTS；
- 不记录 Authorization、code_url 或完整 query/body。

## 15. Task 13：CI、打包与在线更新

修改现有 GO CLAW CI：

- 合同 lint；
- billing 单测与 PostgreSQL integration；
- console 测试；
- portable smoke；
- secret scan；
- updater preserve-list 断言。

Full ZIP 和 update payload 门禁：

- 不含商户私钥、APIv3 key、微信平台密钥、NewAPI admin token；
- 不含服务端 `.env`、数据库 DSN 或生产 token；
- Full ZIP 仍只携带 provisioning bootstrap 配置；
- update payload 不覆盖 `data`、`GO-CLAW-Config`、聊天记录或 `.go-claw-billing.json`；
- 没有 billing profile 的旧盘自动走幂等迁移，必须复用原 NewAPI 用户；失败不影响原有聊天、员工、模型、额度条和在线更新；
- CI 从 v2.0.1/v2.1.1 真实目录结构执行更新，断言聊天数据库、员工配置、credentials、instance id 和原 quota 绑定均保持不变。

## 16. Task 14：Staging、灰度与发布

验证顺序：

1. fake provider 全链路；
2. staging 微信建单、付款、回调、到账；
3. 主动屏蔽回调，验证查单补偿；
4. 重放回调 100 次；
5. 注入 NewAPI connect failure 与 post-send timeout；
6. 管理员全额退款；
7. 微信、Billing、NewAPI 日终对账；
8. PostgreSQL PITR + WORM 恢复演练；
9. 内部实例；
10. 5% → 25% → 100% 灰度。

发布开关顺序：

- 先部署 DB、回调、worker，保持建单关闭；
- 确认 webhook 可达与证书正确；
- 开启内部账户建单；
- 验收后逐级放量；
- 回滚只关闭新建订单，不能停止处理已付款订单。

## 17. 完成定义

- [ ] 设计和五份合同通过产品、财务、法务、安全评审；
- [ ] 所有自动化测试和故障注入通过；
- [ ] 配置合同固定单笔 ￥1–￥100,000，快捷金额 ￥10/￥50/￥100/￥200；
- [ ] 真实 ￥1 订单展示增加 5,000,000 算力，并在 NewAPI 精确增加 75,000 units；
- [ ] ￥1.01 可精确下单；￥100,000 上边界无 int32/float/格式化溢出，越界和三位小数金额被拒绝；
- [ ] 重复回调不重复加额；
- [ ] 丢回调可自动查单到账；
- [ ] ambiguous NewAPI 调用不自动重试并有可操作复核证据；
- [ ] 每笔付款、加额、撤额、退款均有平衡 journal；
- [ ] 存量 v2.0.1/v2.1.1 在线迁移不丢聊天、员工、配置和额度，不创建第二个 NewAPI 用户；
- [ ] enrollment 故障时老用户原功能继续工作，恢复后自动完成充值开通；
- [ ] 7 天 staging 连续对账无未解释差异；
- [ ] 正式发布记录包含 artifact digest、schema version、pricing version、terms version 和回滚开关。

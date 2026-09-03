# GO CLAW 算力充值合同包

状态：Draft
设计入口：`../../superpowers/specs/2026-09-03-go-claw-compute-recharge-design.md`

## 文件

| 文件 | 用途 | 权威单位 |
| --- | --- | --- |
| `openapi.yaml` | Billing Service 客户、管理与微信回调 API | CNY 分、客户展示算力；原始 NewAPI 单位仅限内部管理合同 |
| `provisioning-enrollment.openapi.yaml` | v2.0.1/v2.1.1 老用户 proof-of-possession 无感开通 | 实例与既有 NewAPI 用户绑定，不处理金额 |
| `events.schema.json` | outbox/inbox 内部事件 | CNY 分、DISPLAY_COMPUTE_UNIT、NEWAPI_QUOTA_UNIT |
| `ledger.postgresql.sql` | PostgreSQL 账本与状态数据合同 | CNY_FEN、NEWAPI_QUOTA_UNIT；订单另存展示算力快照 |
| `GO-CLAW算力充值服务条款模板.zh-CN.md` | 客户 clickwrap/服务条款底稿 | 人民币、客户展示算力 |

## 路径映射

React 只调用本机同源接口：

```text
/api/console/recharge/config
/api/console/recharge/balance
/api/console/recharge/orders
/api/console/recharge/orders/{order_id}
/api/console/recharge/orders/{order_id}/close
/api/console/recharge/ledger
```

本地 FastAPI 读取计费凭证并映射到 `openapi.yaml` 的远端 `/v1/*`。浏览器不得读取计费 token，也不得调用 `/internal/admin/*` 或微信 webhook。

## 不变量

1. 用户展示 `display_compute_units = amount_fen × 50,000`，NewAPI 执行 `newapi_quota_units = amount_fen × 750`，均使用 checked int64；
2. 单笔金额必须是 ￥1–￥100,000、最多两位小数；快捷金额固定为 ￥10/￥50/￥100/￥200；
3. 客户 API 不返回美元或 NewAPI 原始 quota unit；订单创建后定价版本和双单位换算快照不可变；
4. 微信支付成功与 NewAPI 到账是两个状态；
5. 同一微信交易、配额 adjustment、退款和 journal 只能入账一次；
6. journal 必须按 asset 分别借贷平衡；
7. journal 和 audit 只追加，更正必须 reversal；
8. 客户不能指定 NewAPI user id；
9. 商户密钥和 NewAPI 管理 token 永不进入客户包；
10. 非幂等下游结果不确定时进入人工复核，禁止盲重试；
11. feature flag 关闭新建订单时，回调、查单、到账和退款 worker 仍运行；
12. 老用户 enrollment 失败不得影响聊天、员工、模型、原额度和在线更新。

## 版本策略

- 两份 OpenAPI 和 event `v1` 只允许增加 optional 字段；
- 删除字段、收窄含义、改变金额单位或重用枚举含义必须升级主版本；
- 数据库变更只通过 forward migration；生产回滚以兼容旧代码的 expand/contract 策略执行；
- 定价和客户条款均使用独立版本号，并在订单中快照。

## 上线前替换项

- `openapi.yaml` 的正式服务域名如有变化；
- 服务条款内所有 `[占位符]`；
- 每日累计风控上限（单笔最低/最高及快捷金额已经确认）；
- 数据、账单、审计和 WORM 保存期限；
- 微信商户与 appid 配置；
- 客服、发票、退款和争议处理主体。

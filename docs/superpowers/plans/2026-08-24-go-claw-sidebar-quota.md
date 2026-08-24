# GO CLAW 侧边栏精简与额度进度条实施计划

> 状态：第一部分已推送（5103c4bd）；第二部分已按定稿方案实施（2026-08-24）
> 关联台账：docs/GO-CLAW-变更台账.zh.md（实施后补登）

## 背景与目标

GO CLAW 面向非技术客户，侧边栏/设置中面向开发者的入口造成干扰。本计划做两件事：
1. 隐藏过度专业/低频入口（11 项）；
2. 侧边栏左下角新增"额度使用进度条"（只显示百分比，与 New API 额度同步）。

---

## 一、侧边栏入口隐藏

### 范围（菜单 id → 中文名）

| 菜单 id（`console/src/layouts/registry/builtinMenu.ts`） | 中文名 | 所在组 |
|---|---|---|
| `core.tools` | 工具 | 工作区组 |
| `core.mcp` | MCP | 工作区组 |
| `core.acp` | ACP | 工作区组 |
| `core.heartbeat` | 心跳 | 控制组 |
| `core.environments` | 环境变量 | 设置组 |
| `core.security` | 安全 | 设置组 |
| `core.token-usage` | Token 消耗 | 设置组 |
| `core.backups` | 备份 | 设置组 |
| `core.voice-transcription` | 语音转写 | 设置组 |
| `core.debug` | 调试 | 设置组 |
| `core.plugin-manager` | 插件管理 | 设置组 |

保留不动：聊天、收件箱、应用、频道、会话、定时任务、文件、技能、运行配置、数字员工统计（agentStats）、设置齿轮。

### 实施方案

利用已有的菜单项级 `visible?: () => boolean` 钩子（`plugins/registry/types.ts:105-106`，适配器 `layouts/registry/adapter.tsx:86,98-100,121` 已消费它，目前无内置项使用）：

- 在 `builtinMenu.ts` 顶部新增常量与注释：
  ```ts
  // GO CLAW 客户版：对非技术客户隐藏的过度专业/低频入口。
  // 仅隐藏菜单项，路由保留（深链接/未来恢复不受影响）。
  const CUSTOMER_HIDDEN_MENU_IDS = new Set([
    "core.tools", "core.mcp", "core.acp", "core.heartbeat",
    "core.environments", "core.security", "core.token-usage",
    "core.backups", "core.voice-transcription", "core.debug",
    "core.plugin-manager",
  ]);
  ```
- 给上述 11 个菜单项各加一行：`visible: () => !CUSTOMER_HIDDEN_MENU_IDS.has("<id>")`。
- **不改路由**（`builtinRoutes.tsx` 不动），直接访问 URL 仍可达——作为隐藏功能的兜底通道。
- 已有的 simple mode 白名单机制（`Sidebar.tsx:72-99`）不动；本改动作用于默认的 full 模式。

### 验证

- `console/src/layouts/` 下现有测试全绿；新增一个测试：渲染侧边栏后断言 11 个入口不存在、保留项存在。
- 手动核对截图：侧边栏只剩 聊天/收件箱/应用/频道/会话/定时任务/文件/技能/运行配置/数字员工统计 + 左下齿轮。

---

## 二、额度使用进度条（安全审查后定稿）

### 2.1 审查结论（冲突 / 假数据 / 安全暴露）

**假数据风险（已排除一条错路）**：New API 自带的 `/v1/dashboard/billing/subscription` 实测 `hard_limit_usd` 恒为系统级大数（$100,000,000），不反映子用户真实额度——**已否决直连 New API billing 端点的方案**。真实数据只有两处：one-api.db 的 `users.quota`（剩余）与 provision.db 的签发记录（授予额）。

**安全暴露面（逐项评估）**：
1. HMAC secret 随便携包分发（此前评审已接受）：持有者可伪造任意 instance_id 查额度——只泄露金额数字，敏感度低；`/api/quota` 对不存在的 instance 一律 404，防枚举。
2. **限流冲突（必须处理）**：现有 5 次/IP/天 是为"开通"设计的；额度条 60s 轮询 = 每实例 1440 次/天，绝不可复用该限制。`/api/quota` 采用独立的**按 instance_id 限流**（240 次/小时/实例），且该端点的失败请求不影响开通限流计数。
3. console 后端代理只转发数字：返回体仅 `granted/remaining/percent` 三个数；secret、instance.id 不出后端进程；仅在便携模式启用，否则 404。
4. 传输：provisioning URL 强制 https（`_load_provision_config` 已校验）。
5. 直读 one-api.db 为只读；New API 升级改 schema 的风险低，若读失败返回 503，前端隐藏组件（无假数据）。

**数值正确性**：
- percent = remaining / granted × 100，clamp 到 [0, 100]；
- 管理员在 New API 充值后 remaining 可能超过签发额 → 显示 100%（合理语义：额度充足）；
- granted 记录于签发时刻（provision.db 新列），不受后续 GIFT_QUOTA 配置变更影响。

### 2.2 唯一技术方案（数据链路）

```
客户机 console 前端 QuotaBar
  → GET /api/console/quota            （GO CLAW 后端代理，仅便携模式）
      → 读 GO-CLAW-Config/provision.json + data/instance.id
      → HMAC 签名 → GET {origin}/go-claw/quota?instance_id&ts&sign
          （nginx: location = /go-claw/quota → 127.0.0.1:9100/api/quota）
      → provisioning 服务验签 → 查 provision.db(instance→user_id, granted)
        → 只读查 one-api.db users.quota（remaining）
      → 返回 {granted, remaining, percent}
```

### 2.3 执行步骤（含具体代码位置）

**A. provisioning 服务端**（`scripts/provisioning/provision_server.py`）
1. `init_db()` 中加列迁移：`ALTER TABLE provisions ADD COLUMN granted_quota REAL`（catch duplicate-column 异常即跳过），`finalize_provision` 写入 `GIFT_QUOTA`；存量行回填。
2. 新增 `GET /api/quota`：校验 instance_id 格式 + 时间窗 + HMAC（复用现有逻辑）；按 instance_id 限流（内存 dict + 每小时 240 次）；实例不存在 → 404；查 one-api.db 失败 → 503。返回 `{"granted": float, "remaining": float, "percent": int}`。
3. 测试：`test_provision_server.py` 新增 3 例（正常、签名错 403、未知实例 404）。
4. 部署：`scp` 到服务器 `/opt/go-claw-provisioning/`，`systemctl restart go-claw-provision`；nginx `/etc/nginx/conf.d/newapi-8443.conf` 增加：
   ```nginx
   location = /go-claw/quota {
       proxy_pass http://127.0.0.1:9100/api/quota;
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
   }
   ```
   `nginx -t && systemctl reload nginx`；curl 验证 400/403/404 三类响应。

**B. GO CLAW 后端代理**（新文件 `src/qwenpaw/app/routers/quota.py`，挂进 `_app.py` 路由注册处）
1. `GET /api/console/quota`：非便携（`QWENPAW_PORTABLE != "1"`）或无 provision.json 或无 instance.id → 404。
2. 从 provision.json 读 `provisionUrl`，取其 origin 拼 `/go-claw/quota`；用 hmacSecret 对 `{instance_id}:{ts}` 签名；httpx GET，15s 超时；透传三字段。
3. 测试：mock httpx，覆盖 404（非便携）/正常透传/上游 503。

**C. 前端**（console）
1. `console/src/api/modules/quota.ts`：`getQuota()` → `GET /api/console/quota`，404 返回 null。
2. `console/src/layouts/QuotaBar.tsx`（新组件）：antd `Progress`，4px 高、品牌橙 `#FF4A18`、percent<20 变红 `#ff4d4f`；tooltip 显示"剩余 $X / 共 $Y"；加载中/失败/null 不渲染；60s 轮询 + window focus 刷新。
3. `console/src/layouts/Sidebar.tsx`：在 authActions 块（:584）之前插 `<QuotaBar />`，仅 `!collapsed` 时渲染。
4. `zh.json` 加 `nav.quota: "额度"`；`layouts/index.module.less` 加 `.quotaBar` 样式。
5. 测试：`QuotaBar.test.tsx`（渲染百分比/低额度变红/null 隐藏）。

### 2.4 明确排除

- 前端不直连 New API、不持有 secret；不显示金额于主界面（金额只在 tooltip）；不做预警推送；不改 New API 本体；不动现有 5 次/IP/天 开通限流。

---

## 三、工作量与顺序

1. 侧边栏隐藏（小，半天内）→ 2. provisioning `/api/quota` + 后端代理（中）→ 3. QuotaBar 组件（小）。
2. 全部完成后跑一次 Desktop Build 出新包。

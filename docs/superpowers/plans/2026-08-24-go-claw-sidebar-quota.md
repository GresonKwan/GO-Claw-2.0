# GO CLAW 侧边栏精简与额度进度条实施计划

> 状态：第一部分（侧边栏隐藏）已实施；第二部分（额度进度条）设计中（2026-08-24）
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

## 二、额度使用进度条（设计 + 实施）

### 数据链路（关键决策）

已实测：New API 的 `/v1/dashboard/billing/subscription` 返回的 `hard_limit` 不反映子用户真实额度（恒为系统级大数），**不能直接用**。

采用**服务端聚合**方案（我们同时控制两端，数据最准）：

1. **provisioning 服务新增** `GET /api/quota`（`scripts/provisioning/provision_server.py`）：
   - 入参同 `/api/provision`：instance_id + ts + HMAC 签名（复用现有验签）；
   - 按 instance_id 查 provision.db → 拿到 New API user_id → 从 one-api.db 读 `users.quota`（剩余）+ 签发时记录的 `granted_quota`（provision.db 新增列，存量行回填 GIFT_QUOTA）；
   - 返回 `{ "granted": <美元>, "remaining": <美元>, "percent": <0-100> }`。
   - percent = remaining / granted × 100（管理员充值后 remaining 增大，百分比同步上升，符合直觉）。
2. **客户端**：console 新增 `api/modules/quota.ts`，通过后端代理转发到 provisioning 服务（后端读 `GO-CLAW-Config/provision.json` 拿 URL + secret + instance.id 签名）——前端不直接接触 secret。
   - 后端代理路由：`GET /api/console/quota`（`src/qwenpaw/app/routers/console.py` 或新小模块），非便携包/无 provisioning 配置时返回 404，前端隐藏组件。
3. 刷新策略：进入页面请求一次 + 每 60s 轮询 + 窗口聚焦时刷新。

### UI 设计

位置：侧边栏左下角，齿轮/折叠按钮行（`Sidebar.tsx:617-647`）**上方**、账号区（:584-615）下方；折叠态只显示迷你圆环或隐藏（先隐藏，保持简单）。

```
┌─────────────────────┐
│ 额度                │
│ ▓▓▓▓▓▓▓░░░░░░  47%  │   ← 4px 高进度条 + 右侧百分比
├─────────────────────┤
│ ⚙  ⬅                │   ← 原有齿轮/折叠行
└─────────────────────┘
```

- 组件：`console/src/layouts/QuotaBar.tsx`（新文件），antd `Progress`（`size="small"`，`showInfo` 定制为右侧百分比）。
- 文案：标签"额度"（zh.json 新增 `nav.quota`）；tooltip 显示"剩余 $1.23 / 共 $2.00"。
- 配色：正常用品牌橙 `#FF4A18`；percent < 20% 转红色 `#ff4d4f` 并 tooltip 提示"额度即将用完，请联系客服"。
- 加载失败/非便携包：整体不渲染（不占空间、无报错）。
- 样式：`layouts/index.module.less` 新增 `.quotaBar`（padding、字号 12px、颜色 token 用 less 变量）。

### 验证

- provisioning 服务端：`test_provision_server.py` 新增 2 例（正常返回、签名错误 403）。
- 后端代理：单元测试 mock httpx。
- 前端：`QuotaBar` 组件测试（渲染百分比、低额度变红、404 时隐藏）。

### 不做（明确排除）

- 不显示具体金额于主界面（只要百分比，金额进 tooltip）；
- 不做额度预警推送；
- 不改 New API 本体。

---

## 三、工作量与顺序

1. 侧边栏隐藏（小，半天内）→ 2. provisioning `/api/quota` + 后端代理（中）→ 3. QuotaBar 组件（小）。
2. 全部完成后跑一次 Desktop Build 出新包。

# v2.1.2 交付产物预览与历史恢复诊断

> 状态：代码级首失败阶段已固定并完成最小修复；v2.1.3 本地完整 Main Build 和 Portable 启动/迁移已通过，真实正式 v2.1.2 U 盘与媒体生成现场仍待执行。
> 日期：2026-09-09（Asia/Shanghai）。

## 1. 证据边界

客户现场已报告两项独立现象：图片卡片存在但预览失败；切换数字员工或会话后再返回，交付产物区域消失。本轮没有把截图当作网络响应、文件字节或数据库证据，也没有预设二者同根。

为避免在不稳定 H 盘和客户数据上试错，本轮先以正式代码路径和可重复前端夹具逐段执行 Stage A–E。夹具只证明代码分支和失败阶段，不替代后续真实 U 盘、真实图片文件及 Network 日志。

## 2. 首个失败阶段

### 2.1 历史区域消失：Stage C（会话恢复）

`SessionApi.getSession()` 的 LRU 命中分支会直接返回已经转换的 messages；持久交付物索引查询只存在于首次后端历史转换路径。因此一个不含 deliverables envelope 的缓存会话在切回时不会调用 `/api/deliverables/query`，Panel 没有可渲染 envelope。Stage A/B/D 未参与该失败。

最小修复：给缓存会话增加仅表示“持久交付物查询成功”的 `deliverablesHydrated` 标记。首次加载和 LRU 命中共享 `hydrateDeliverables()`；成功或确认没有 response ID 后置 true。瞬态失败不置 true，下次切回只重试轻量索引，不重新读取整段聊天，也不扫描磁盘。

回归夹具 `console/src/pages/Chat/tests/deliverablesHistory.test.ts` 固定：缓存命中仍查询并合并；首次失败后下次命中重试；成功后不重复查询。

### 2.2 卡片存在但预览失败：Stage D（媒体读取）

媒体 URL 使用短期 ticket。缩略图 `<img>` 和预览弹层在 ticket 过期或读取失败后只有失败状态，没有重新取得一次 ticket 的路径。持久 envelope 和真实文件即使仍存在，旧 URL 也会使用户看到预览失败。

最小修复：`MediaDeliverablesRail` 与 `ArtifactPreviewDialog` 在首次媒体加载失败时各续签一次 ticket 并重载；第二次仍失败就停止，不循环请求，保留卡片/弹层并显示明确不可用文案。没有把媒体转成 base64、没有延长服务端 ticket、没有批量预取。

回归夹具 `ArtifactPreviewDialog.test.tsx` 与相关 rail 测试固定单次续签和最终失败边界。

## 3. 数据与兼容边界

- 不迁移、不重写 v2.1.2 chat/session/deliverables 记录；
- 不修改 `data/`、`secrets/`、员工 workspace、额度或充值账本；
- 老后端没有 deliverables 接口或接口瞬态失败时，聊天仍可打开；
- 缺失/损坏文件不隐藏整个交付区域；
- 查询上限仍为最近 50 个 response ID，媒体仍按需读取。

## 4. 已完成验证与未完成项

已完成：前端定向回归及随后全量 169 文件/1261 项通过，TypeScript 与 production Vite build 通过。最终代码对应的 v2.1.3 本地 Main Build 成功，Portable 在中文目录、两次盘符映射、二次双击和优雅退出场景通过；公开构建的五员工及图片/视频插件清单可用。

未完成：正式 v2.1.2 干净产品盘上用真实媒体复现并保存脱敏 response ID、文件 SHA-256、ticket/thumbnail/content HTTP 状态；已激活账号下 v2.1.3 的会话切换、刷新、重启与图片/视频真实生成验收。公开包按合同不携带 `provision.json`，其模型路由 503 只证明未绑定态降级，不能冒充真实媒体通过。完成前不得把本文件写成真实媒体设备验收通过。

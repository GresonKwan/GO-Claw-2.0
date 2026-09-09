# GO CLAW v2.1.3 兼容与运行合同

状态：本地实现合同；CI、正式签名构建、Release 与生产更新切换必须分别记账，不能由源码状态代替。

## WV2-01：Windows 客户端前置条件

- `clientMode=browser` 不检测、不安装 WebView2；`auto` 才执行前置检查。
- 只读取 HKLM/HKCU 固定 WebView2 Client GUID 的 `pv`；严格大于 `0.0.0.0` 才视为可用。
- 缺失时只接受产品根 `WebView2/MicrosoftEdgeWebview2Setup.exe`。路径必须是根内普通文件且无链接/reparse point。
- 产品根 `MANIFEST.json` 必须把该文件声明为 `evergreen-bootstrapper`、`requiresNetwork=true`、微软官方固定来源，并同时匹配文件记录和 SHA-256。
- Windows 运行时还必须通过 WinTrust Authenticode 校验及微软文件身份校验；随后以参数数组 `/silent /install` 启动，不经 shell。
- 单进程最多尝试一次，最长等待 300 秒；超时不强杀微软安装事务。失败后只进入一次浏览器回退，不启动第二个后端。
- Portable ZIP 自身携带 WebView2、根 Manifest 和 SHA256SUMS；Full ZIP 仅包装同一 Portable staging，不维护第二份安装器。

## DL-213：交付产物恢复与媒体票据

- 已持久化的 deliverables envelope 和 response ID 不迁移、不改写。
- 空闲会话从 LRU 恢复时，若交付物索引从未成功水合，必须只重试交付物查询；不得重新拉取整段聊天。
- 一次成功水合后复用缓存；瞬态失败保留“未水合”状态，以便切回会话时恢复。
- 图片缩略图、图片预览和视频预览均允许一次媒体票据续签；第二次失败显示明确不可用状态，不静默移除整个交付区域。
- 媒体仍受原 workspace/response 所有权校验，不因预览修复放宽路径或鉴权。

## QT-213：算力余额只增字段

- `/api/quota` 原有 `granted`、`remaining`、`percent` 含义不变。
- 新增可选非负安全整数 `displayRemaining`，按 `floor(newapi_remaining_units × 200 / 3)` 计算；全程整数运算。
- provision 服务、客户端代理和前端均对该字段独立验证；字段缺失或非法时只省略新字段，不破坏旧三字段。
- v2.1.3 UI 以余额数字为主：小于 1 万显示完整整数，1 万至 1 亿使用“万”，1 亿以上使用“亿”，最多一位小数；完整值保留在 aria/tooltip 文本。
- 低余额阈值固定为 500 万；充值成功事件只触发一次立即刷新，增量到账提示约 3 秒且不占布局；常规轮询仍为 60 秒。
- 旧服务端返回旧三字段时显示兼容百分比，网络瞬态失败保留上次成功值；首次不可用显示 `--`。

## SEC-213：New API 公网面

- 8443 只允许 `/v1` 模型协议、精确 provision/quota/enrollment 和只读 updates；`/api/*`、管理 UI、healthz、`/v1beta/*` 及未知路径不进入上游。
- 充值 API 与微信回调继续由 443 提供；New API 管理界面仅通过 SSH 隧道访问 loopback 3000。
- 本合同不新增 voucher、开户/pending 熔断或数据库迁移；已有 done 实例、聊天、额度和账本不受影响。

## A/B 数据不变量

`data/`、`secrets/`、`backups/`、`logs/`、`cache/`、`GO-CLAW-Config/` 和 `portable.json` 永不进入程序槽。`WebView2/`、`MANIFEST.json`、`SHA256SUMS.txt` 属 `bootstrap-root` 根组件，随签名组件事务备份、安装和回滚；聊天、员工身份、实例、额度及充值账本不参与程序回滚。

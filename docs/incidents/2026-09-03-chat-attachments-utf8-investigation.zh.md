# v2.1.2 附件 UTF-8 报告：有限核查记录

取证时间：2026-09-03 22:31–22:33（Asia/Shanghai）；整理：2026-09-04。
状态：**已定位并修复 AT-03 URL 二次解码缺陷；真实媒体字节与 SSE 编码合同已自动回归，完整 UI
文件选择器和真实多模态模型理解仍待实机验收。**

## 1. 报告与本次结论

用户报告在对话框添加图片或视频附件时提示 UTF-8 错误，并要求若核实不存在则继续推进版本。
最初没有对应错误堆栈/失败媒体原文件，因此没有先加推测性编码补丁。后续在 AT-03 得到可重复失败：
前端把本地路径直接拼到路由，服务端又对框架已解码的 path 做一次 `unquote`，文件名中的 `#`、
`%2F`、`+`、空格和 Unicode 会被截断或再次解释。修复只限定为“各路径段编码一次、框架解码一次”；
上传和 provider 链继续传递原始 bytes，禁止把图片或视频尝试转换成 UTF-8 文本。

## 2. 环境与证据

| 项目 | 观察 |
| --- | --- |
| 产品 | 当前已使用的 F 盘；`F:\GO-CLAW-Portable.exe` 与 F 盘 binaries 后端 |
| 版本/端口 | `/api/version` 为 v2.1.1；`F:\data\desktop_port` 为 14666；只代表取证当时 |
| 日志 | `F:\data\desktop.log`、`F:\data\qwenpaw.log`；检查范围内未发现对应 UTF-8/Unicode 异常 |
| 浏览器 | 当前聊天页面可用、5 个员工、41% 额度；这些不等于附件全部可用 |
| UI 限制 | 点击附件按钮打开了系统文件选择器，但未通过该选择器完成文件选择；不能报 UI E2E 通过 |
| 测试文件 | 已有 PNG，289400 字节；上传 multipart 文件名设为 `附件测试-猫咪图片.png` |
| 上传 | POST `/api/console/upload` HTTP 200；无员工 header，实际落在 default，不等于已测 content-production |
| 返回 | file_name 为上述中文名，size 289400；url 为 default workspace media 下带 UUID 的本机路径 |
| 预览 | Windows 反斜杠编码形式和斜杠规范化形式均 HTTP 200，响应长度均 289400 |
| 对话流 | 新建隔离 debug session，image_url 使用上传本机路径，文本“仅回复：附件已读取”；HTTP 200 SSE 正常完成，没有 Unicode 错误 |
| 模型边界 | 使用 deepseek/deepseek-v4-flash-0731；正文被 headline 处理后为空/仅标题，不能证明模型理解了图像 |
| 视频 | 没有真实 MP4 完成上传、预览、模型请求的证据，保持待验证 |

本轮测试 session：`utf8-attachment-debug-20260903`；chat id：`01c9ba96-3435-43c4-af27-bcd04f93aba3`。
上传保存文件：`F:\data\workspaces\default\media\fefd34410b6b4581969407a0a5558097_附件测试-猫咪图片.png`。
这些是历史定位线索，U 盘重插后不可假定 F 仍是同一设备。没有记录原文件 SHA-256，也没有独立导出
完整 HAR/日志副本；后续不能把本记录当作可重复的完整发布证据。不要删除客户会话以“清理现场”。

## 3. 代码阅读事实

源码基线：`cd365aa`，当前工作分支 `codex/compute-recharge`，相关路径均为已有代码。

| Stage | 入口 | 事实与尚未证实的边界 |
| --- | --- | --- |
| AT-01 | `console/src/api/modules/chat.ts::uploadFile` | FormData 二进制上传；未发现 readAsText 媒体解码 |
| AT-02 | `src/qwenpaw/app/routers/console.py::post_console_upload` | await file.read 返回 bytes，write_bytes 落盘；中文文件名经过安全化 |
| AT-03 | `console/src/api/modules/chat.ts`、`console/src/pages/Chat/utils.ts`、`src/qwenpaw/app/routers/files.py` | 已复现路径段未编码与二次 `unquote`；现已固定 URL 单次语义并覆盖特殊字符 |
| AT-04 | `src/qwenpaw/agents/model_factory.py`、`src/qwenpaw/providers/capping_formatter.py` | 本地媒体 rb 读取后 base64，不把原始 PNG/MP4 decode UTF-8 |
| AT-05 | formatter 到 provider | 本次调用完成不等于视觉/视频能力已被证实；需要支持相应模态的 mock 和实测断言 |
| AT-06 | `console/src/pages/Chat/index.tsx` 与 SDK 流读取 | UTF-8 文本流和媒体字节是两条路径；四字节字符跨 SSE chunk 已回归，媒体 bytes 不进入文本解码器 |

`ChatUploadResponse` 注释写“filename only”而实际返回绝对路径，是文档注释偏差，不是已证实的
UTF-8 根因。`_resolve_console_upload_refs` 存在但未接入，也不能仅凭未使用就认定是事故原因。

## 4. 发布前待补矩阵

| 样本/场景 | 上传/预览 | 对话/历史 | 状态 |
| --- | --- | --- | --- |
| 上述真实 PNG，中文文件名，default | HTTP 200，大小相同 | SSE 完成但无视觉理解证据；历史未验证 | 有限通过 |
| 同一 PNG 通过 UI 选择，content-production 与 default | 文件选取、缩略图、agent header | 发送/重启/重放 | 待验证 |
| JPEG/WebP，中文/空格/#/%/+/emoji 文件名 | 合法 bytes、不双重 URL 解码 | 自动合同保持引用 | 自动回归通过 |
| 真实 MP4，支持的 MIME/codec | 原始 MP4 字节上传和 magic 校验通过 | 真实视频模型理解仍待实测 | 部分通过 |
| 真实图片，正斜杠/反斜杠/历史绝对路径 | 正确且仅一次解析 | 更新前会话可重放 | 待验证 |
| 文件名看似图片但 bytes 损坏；空文件 | `INVALID_MEDIA_BYTES` / `EMPTY_ATTACHMENT` | 不报成泛 UTF-8 错误 | 自动回归通过 |
| 上传超限、非 JSON 错误页、认证过期、断网、取消 | 有界失败与可重试提示 | 不阻塞下一次发送 | 待验证 |
| 四字节字符跨 SSE chunk | 不误解码媒体 bytes | 文本正确重组 | 自动回归通过 |
| 干净 v2.1.1 / 候选 v2.1.2；NTFS / 目标 U 盘 | 同样本相同请求 | 多员工隔离、历史兼容 | 待验证 |

测试落点与代码条件修改见 [计划 Phase 6A](../superpowers/plans/2026-09-03-go-claw-v2-1-2-implementation-plan.md)。
特别注意 `console/vite.config.ts` 当前排除 `ChatPage.test.tsx`；命令列出该文件不等于它运行过。
此前对临时代码的测试不得作为撤回后基线的通过证据；最终以实际测试报告收集的文件和用例数为准。

2026-09-04 在未保留编码补丁的当前源码上重新执行：

```powershell
& 'F:\binaries\node-runtime\node.exe' .\node_modules\vitest\vitest.mjs run src/api/modules/chat.test.ts src/pages/Chat/utils.test.ts
```

执行目录为本工作树 `console`；该早期结果为 **2 个测试文件、50 项通过**。2026-09-05 又新增并执行
`chat.test.ts`、`attachments.test.ts`、`utils.test.ts` 与后端 `test_console_upload.py`：覆盖 PNG/JPEG/
WebP/MP4 原始字节、中文/空格/#/%/+/emoji、空/损坏媒体、非 JSON 413 和四字节字符跨 SSE chunk。
最终前端相关 8 文件 19 项、后端附件 9 项通过。它们仍不包含系统文件选择器操作或真实模型视觉/
视频理解，不能把自动合同升级为 UI E2E 或 provider 能力通过。

## 5. 失败时必须保留的最小证据

1. 原始媒体的大小、magic、SHA-256 和用户允许使用的复现样本；不要在日志写媒体内容或 token。
2. 产品真实根/版本/构建摘要、文件系统、agent 与模型 ID；先确认盘符对应设备。
3. 第一处失败 stage、HTTP 状态和脱敏 error code/堆栈；区分 upload、preview、normalize、formatter、
   provider 与 SSE，不能凭最终 UI toast 猜后端根因。
4. 相同样本修复前失败、单点修改后通过；再扩展其他模态。原始媒体 bytes 必须不被改写。
5. 若矩阵均不复现，记“未复现，未加编码补丁”，继续版本发布门禁，不编造根因或修复成果。

本记录不涉及生产更新源、服务器配置或客户热修复脚本更改。

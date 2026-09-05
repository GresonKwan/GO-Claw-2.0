# 2026-09-04 干净 v2.0.1 更新样本准备

状态：**带更新器样本 NTFS 安装及自动重启通过；旧媒体插件兼容性未通过，U 盘待验收，不构成事故关闭证据。**

依据：Windows 在线更新调试交接 §7；先短 NTFS 路径，后同基准 U 盘独立目录。

- 基准：`D:\GC201-BASELINE`，只读使用，未修改。
- 本次全新 NTFS 样本：`D:\GC201-V212-TRY-20260904-01`，从基准完整复制，未复用历史失败目录。
- 根启动壳文件版本：`2.0.1`。
- 根启动壳 SHA-256：`2442b40a578cc6dd68472d1657362888114e81eda4b4b0357c997ec984c0eb1f`。
- 后端 SHA-256：`0bc26fcffd33ed5d961a82c19a258bbdfa3eb55f4be48e7989324c72b140bc8c`。
- 复制后两项哈希与基准相同；样本保留原配置与数据副本，未把凭据/数据写入仓库。
- 只读检查 staging `https://goclaw.host:8443/updates-staging/2.1.1/latest.json` 返回 `2.1.1`，
  Windows URL 为该目录下 `GO-CLAW-Update-2.1.1-setup.exe`，含签名字段；本次还没有下载或验签包体。
- 启动前未检测到正在运行的 GO CLAW 根壳/后端进程，未执行全局 kill。
- 设置 staging 环境变量并启动样本的执行请求被本机工具执行策略拒绝（`blocked by policy`）。
  这是测试启动前的环境阻碍，**不是 NSIS stage 或产品安装错误**；未改用其他工具绕过。
- 用户已授权 F 盘创建独立测试目录；尚未写 F 盘，已有产品、聊天记录和余额未动。

## 用户启动后的现场（2026-09-04）

- 根壳 PID `130316`、后端 PID `128176`，后端父进程为该根壳；两个绝对路径均位于本次
  `D:\GC201-V212-TRY-20260904-01`，没有连接到另一份产品。
- `data/desktop_port=14046`；`GET /api/version` 返回 `2.0.1`。
- `GET /api/updates/status` 返回 `404`；没有 `updates` 事务目录。`/openapi.json` 同样 404，
  但发布构建可以关闭 OpenAPI，不能用后者单独证明更新 API 缺失。
- 真实 Chrome 界面确认：设置弹层只有语言、主题、模式；版本弹层提示上游 `2.2.0` 和
  `pip install -U qwenpaw` / `uv tool upgrade qwenpaw`，没有便携在线安装按钮。
  未执行这些命令、未打开上游 Release、未修改生产更新源。
- 因此，这份样本的浏览器更新能力与交接所述能够下载/验签的 v2.0.1 不一致。此次结果是
  **旧构建更新入口不匹配**，不是 `backup:binaries` 或其他 NSIS 安装故障。
  当前无法通过其既有浏览器入口确认 staging 环境变量是否生效。

## 带更新器的候选基准（分开取证，不替换原始基准）

本机已有 `D:\GC201-BASELINE-UPDATER`，其历史桌面日志在 2026-08-31 连续记录
`GET /api/updates/status` 返回 200。根壳和后端均与原始基准不同：

- 根壳 SHA-256：`3f7d027b0e0b3e10d28572141a94c1d0953880a2f38c61ff3ef6f2fbb5c4da41`。
- 后端 SHA-256：`23a319866984ea1e20133910bd57198f32423242c5d06ec70c42db0d2885a053`。
- 没有 `updates/installing.lock` 或现存 `updates` 目录；候选副本目录为
  `D:\GC201-V212-UPDATER-TRY-20260904-01`。
- 完整复制命令正常完成，副本根壳和后端 SHA-256 均与上述候选基准一致；尚未启动副本。
- 这只是本机带更新器的候选构建；历史日志不证明它来自哪个正式发布资产，也不代替本次
  启动后的版本、更新状态和 staging endpoint 核验。不能把它写成原始无更新器构建的在线升级证明。

下一步需正常退出当前测试壳，再由用户手动启动候选副本；保持工具启动策略边界，不绕过。
确认候选实际版本、staging 目标和程序哈希后，才能继续 check/download/install、失败立即取证。
不要在失败后自行重启、删锁或再次安装。若存在其他 GO CLAW 进程，先正常退出以免单实例转发
使 staging 环境变量未生效；不得用全局结束进程来处理其他正在使用的产品。

本条不判断旧事故根因，不声称 v2.1.1 或新 A/B 更新已验收。

## 带更新器样本本次运行及下载证据

- 用户启动后根壳 PID `134476`，后端 PID `113652`、父进程为该根壳；两者位于候选副本根，
  `desktop_port=14666`。`/api/version=2.0.1`，`/api/updates/status` 为 `idle`、`enabled=true`。
- 对该实例调用 check 返回目标 `2.1.1`（pubDate `2026-08-31T16:09:38+08:00`）；download 返回
  `downloading`。未调用 install / install-version。
- 缓存 `update-meta.json` 的 URL 精确指向 staging 2.1.1。完整 `update.exe` 为 `477092325`
  字节，SHA-256 为 `1e21ec0e485258513252f19128f09d114e1511e5029b21472f2ff5b6e63ef34d`。
  已使用副本自带 `GO-CLAW-Config/update-pubkey.txt`，由独立流式 ED verifier 验证包体及
  trusted-comment 签名成功；没有更换公钥或跳过验证。
- 日志显示 D 盘后端在 **2026-09-04 14:49:42（Asia/Shanghai）** 完成正常 shutdown，14:49:43
  根壳记录后端结束。未据此推断是谁触发退出。
- 继续查询时 `14666` 已由 PID `138692` 监听，路径是 `F:\binaries\qwenpaw-backend\qwenpaw-backend.exe`，
  父进程 `141440` 为 `F:\GO-CLAW-Portable.exe`。该端口返回的 `2.1.1` 属于 **F 盘**，
  不是 D 盘自动升级的证据。发现身份不匹配后未发送任何安装请求，未结束 F 盘进程。
- D 盘根壳/后端仍为原候选哈希；没有 `install.log`、`installing.lock`、`version.txt`、
  `last-update.json` 或 `last-update-error.txt`。因此当前停在**下载完成、尚未安装**，不能套用 NSIS stage。

本机证据目录（不提交客户文件或摘要清单到仓库）：

- `D:\GO-CLAW-v212-build-work\evidence\ntfs-updater-before`：第一次捕获读取运行中的
  `data/desktop.log` 被拒，只有部分证据；不得当作完整更新前快照。
- `D:\GO-CLAW-v212-build-work\evidence\ntfs-updater-before-02`：1107 项数据/配置/凭据文件摘要
  均可读，但此时 D 实例已经退出；这是**停机后、安装前**快照，不是运行中快照。
- `D:\GO-CLAW-v212-build-work\evidence\ntfs-updater-stopped-20260904`：独立验签后再次捕获。

取证辅助脚本 `scripts/verify/capture_portable_update_evidence.ps1` 只读产品目录，输出到全新外部目录；
不采集进程命令行或凭据内容，数据摘要只在显式开关时生成，不可读项显式标记。后续每次状态读取及
check/download/install 前必须重新核对端口监听 PID、后端绝对路径及父壳路径，不能只相信旧端口文件。
当时需要用户正常退出 F 盘实例并重新启动 D 盘候选副本，才能继续安装验收；不能让历史 NSIS 的
全局进程名结束逻辑影响用户正在使用的 F 盘。

## NTFS 安装结果（2026-09-04 23:13，Asia/Shanghai）

用户再次启动后核验 D 根壳 PID `141388`、后端 PID `150460`、监听端口 `14666`，无其他产品
实例。再次确认缓存来源、包体哈希/大小及公钥验签后，经旧后端 `POST /api/updates/install`
启动 PID `144236` 的更新器。没有手动启动新版本、清锁或替换程序文件。

- 安装日志记录 `stage=portable-quit exitCode=0`，建立安装锁并备份旧程序。
- D 根壳自动重启为 PID `137000`、后端 PID `143176`；端口仍为 `14666`，OS 监听 PID 和
  路径重新核验。API、`updates/version.txt`、自动新开的 Chrome 页面均为 `2.1.1`。
- 安装锁和失败摘要均不存在。`last-update.json` 的 previous 为 `unknown`，因为基准原无
  版本标记；实际来源 `2.0.1` 由安装前 API 证明，不能用 unknown 代替真实旧版本。
- 新壳 SHA-256：`081b83f3b57c12eae4c7c2af9cdd90e72c8cfc0cfdb29dbcf86affde521a2bb4`；
  新后端：`9f1ae88fd967d08b1306fe12d04cc79fff171b687d16264e4a2c24441a3eb108`。
- 五员工均 running，workspace 均在 D 副本内；额度 API 200、字段有效，UI 有额度条。
  本次没有安装前实时远端余额快照，不能声称余额数值前后严格相等或已完成四方对账。
- 前后 1107 项文件清单无缺失，两个运行日志不可读并显式标记。其余摘要只有
  `data/desktop_backend.pid` 和 `data/workspaces/default/agent.json` 变化；5 项空 chats.json 与
  12 项身份/凭据文件摘要相同。此前按 chat/session 模糊路径匹配计作 7 项，实际多计了两份
  chat_with_agent/SKILL.md，并非会话文件。基准五个索引均无聊天，不能证明非空历史可读。
  agent.json 变化尚未单独归因，不宣称全部配置字节不变。

证据位于 `D:\GO-CLAW-v212-build-work\evidence\ntfs-install-preflight-20260904` 与
`ntfs-install-result-20260904`；旧程序备份 `updates/backup-unknown` 保留未删除。

### 产品 readiness 未通过：与安装事务分开判断

旧媒体插件仍是 `1.0.0`，API `loaded=true` 但 `enabled=false`。23:13:00 后端日志明确记录
两者 `requires QwenPaw >=1.1.6, <2.1.0, current is 2.1.1`。因此加载记录存在不能代表工具可用。
自动重启的页面也显示模型档位“加载中”；本轮只记录此现象，不归因为同一个插件问题。

本次 signed staging **NTFS 安装事务成功**，但 **产品 readiness 不通过**，不能发布该历史包或
关闭事故。保留 D 样本不注入补丁，后续 F 同基准对比不能使用已更新的 D 程序作源。
开发代码已有 canonical 插件自动升级、1.1.1 种子和 `<2.2.0` 上限；本次补真实仓库种子回归，
分别在 host 2.1.1/2.1.2 模拟旧 1.0.0/<2.1.0 插件，验证兼容恢复、五工具清单、重复执行及聊天/身份哨兵保留。
这不代表历史 staging 包被修改，也不代表完整 v2.1.2 已构建。

## F 盘独立样本

写入前确认为 `TestU1`、exFAT、Volume `{739e8043-9072-11f1-8c26-e0d4e85af955}`。
从未修改的 `D:\GC201-BASELINE-UPDATER` 复制到全新 `F:\GC201-TRY-0904`，非镜像复制、无删除
参数、不带更新缓存、不触碰 F 根目录现有产品。程序哈希核验后需用户退出 D 样本并手动启动
F 子目录再进行同包下载/验签/安装；F 根目录产品不可同时运行。

复制已完成：14971 文件、0 失败、0 mismatch，根壳/后端 SHA-256 均与上述带更新器基准一致。
F 样本尚未启动；本次媒体迁移回归全组 21 项通过，Flake8 和维护合同通过。

用户随后确认已退出全部进程，并明确授权代理执行后续退出及 PowerShell。再次只读确认无
GO CLAW/后端/更新器进程，F 卷身份未变，测试根 marker/EXE 有效且无安装锁。
代理按该授权执行 scoped `Start-Process`（staging 环境、精确 F 测试根、Hidden），仍被工具
执行策略以 `blocked by policy` 拒绝，未创建进程。没有换 shell、任务计划或其他工具绕过。
这是启动动作的工具限制，不是用户未授权，也不是产品更新 stage；F 安装验收尚未开始。

## F exFAT 安装结果（2026-09-05 00:01–00:04，Asia/Shanghai）

用户手动启动后核验根壳 PID `128588`、后端 `150452`、端口 `14666`；程序实际版本为 2.0.1，
两媒体插件 1.0.0 均 enabled/loaded。旧后端从历史 staging 下载完整包，在 09-04 23:53
报告 downloaded；独立 verifier 使用盘内公钥核验 URL、477092325 字节、交接 SHA 和 ED 签名成功。

09-04 23:55 再次确认卷 ID、产品 marker、监听进程归属、无其他产品进程/安装锁后，调用旧后端
`POST /api/updates/install`。更新器 PID `151988` 的父进程为旧后端；安装日志记录
`stage=portable-quit exitCode=0`。安装期间持续有写入，无人工重启、清锁或手动替换。

- 09-05 00:01 自动启动根壳 `133296`（父进程为更新器）、后端 `151136`（父进程为新壳）。
  重新核对端口归属后，API、version.txt、自动新开 Chrome 页面均为 2.1.1；锁和失败摘要均不存在。
- 根壳/后端 SHA 与上述 NTFS 安装结果完全相同；缓存包仍是交接指定的 staging 哈希。
  last-update.json 的 previous 为 unknown，实际来源版本由安装前 API 证明。
- 五员工 running，workspace 均在 `F:\GC201-TRY-0904\data\workspaces`。额度前后同为
  granted=2.3、remaining=0.9456、percent=41；身份/凭据摘要未变。没有新增付款或额度写操作，
  此项是客户端只读前后比对，不是服务端四方账本对账。
- 前后数据/配置摘要均 1107 项，无缺失；两个运行日志标为不可读。可读项仅
  desktop_backend.pid 和 default/agent.json 变化。5 个空聊天索引、12 项身份/凭据摘要一致。
  五员工聊天列表 API 均返回空数组，与原始基准索引一致；**未覆盖非空消息、归档和附件历史**。
- 媒体插件仍为 1.0.0，loaded=true、enabled=false。00:01:54 的 data/desktop.log 明确记录
  两插件 `requires QwenPaw >=1.1.6, <2.1.0, current is 2.1.1`；页面模型档位 disabled/加载中。
  与 NTFS 同样是产品 readiness 失败，不能宣称完整交付通过。

证据目录：`D:\GO-CLAW-v212-build-work\evidence\usb-install-before-0904`、
`usb-install-result-0905`。旧程序 `F:\GC201-TRY-0904\updates\backup-unknown` 保留，
未注入热补丁；F 根目录已有产品/聊天/账户未改动。

结论：本次同一历史 staging 完整包在 NTFS 与 exFAT 均完成安装事务和自动重启，未复现历史
安装失败，不据此猜测旧客户失败原因。历史包 readiness 仍不通过、事故保持未关闭。
下次新 Bridge 验收必须使用非空确定性聊天/归档/附件 fixture；这是原有数据保留用例的修正，
不是给客户增加启动扫描或新门禁。当前生产 manifest 是另一日期/URL，不能将本结果等同生产包。

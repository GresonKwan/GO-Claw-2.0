# GO CLAW v2.1.1 Windows 在线更新调试交接

> 状态：**事故未解决，禁止发布**。
>
> 最后更新：2026-09-01（Asia/Shanghai）。
>
> 用途：让一台全新 Windows 电脑上的 Codex 不依赖历史聊天即可继续定位
> v2.0.1 → v2.1.1 便携版原地更新失败。

## 1. 接手时先遵守的边界

1. 当前用户实机再次报告更新失败。不得把 `v2.1.1` 写成“已修复”或“可发布”。
2. 生产更新源仍是已知不可安装的 `v2.1.0`；不得切换生产软链、合并 `main`、创建 tag、
   发布 Release 或覆盖任何既有资产。
3. Windows CI 通过的是使用生产 NSIS 脚本和极小 probe payload 的事务测试，不是完整
   477MB 更新包从真实 v2.0.1 目录升级的证明。
4. 每次失败后先保留现场并取证，不要先手动重启、删除 `updates`、清理备份或再次更新。
5. 不把 API key、签名私钥、`GO-CLAW-Config/credentials.json`、`secrets/` 或客户数据提交到
   Git，也不要粘贴到公开日志。更新诊断所需文件见 §7.2。

权威现状先读：

- `docs/GO-CLAW-项目事实与发布基线.zh.md`
- 本文
- `docs/GO-CLAW-变更台账.zh.md`
- `docs/superpowers/plans/2026-08-25-go-claw-online-update.md`

计划与上述“已验证现状”冲突时，以现状为准并停止发布。

## 2. 仓库、分支和已知提交

| 项目 | 当前值 |
| --- | --- |
| GitHub 仓库 | `GresonKwan/GO-Claw-2.0` |
| 调试分支 | `codex/portable-updater-v2-1-1` |
| 本文编写前分支 HEAD | `77f7916e0bab08e5bca6d91b485db8dedc3954bc` |
| 在线更新初始实现 | `58b5fbe8` |
| v2.1.1 事务/恢复修复 | `5921dc41` |
| Windows probe 编译修复 | `50a1460b` |
| staging 启动器与合同测试 | `77f7916e` |

在 Windows PowerShell 中获取代码：

```powershell
git clone --recurse-submodules https://github.com/GresonKwan/GO-Claw-2.0.git
Set-Location GO-Claw-2.0
git fetch origin
git switch --track origin/codex/portable-updater-v2-1-1
git submodule update --init --recursive
git status --short --branch
git log -5 --oneline
```

如果本地已经存在同名分支，使用：

```powershell
git switch codex/portable-updater-v2-1-1
git pull --ff-only origin codex/portable-updater-v2-1-1
```

调试前要求工作区干净。不要基于 `main` 或公开 `v2.1.0` tag 修复，因为它们没有本轮
v2.1.1 事务代码。

## 3. 已发生的事故时间线

### 3.1 已确认的 v2.1.0 故障

v2.0.1 可以检查、下载并完成 SHA-256 + Ed25519 验签，但安装器由
`binaries/qwenpaw-backend` 作为当前目录启动。Windows 因此把 `binaries` 视为正在使用，
更新器在约 30 秒重试后记录 `stage=backup:binaries`，随后回滚并重新启动 v2.0.1。

公开 `v2.1.0` 更新包因此不能交付。

### 3.2 已做但尚未完成实机证明的 v2.1.1 修改

- Python 启动 NSIS 时显式把 `cwd` 设为缓存目录；
- NSIS `.onInit` 在备份前立即把当前目录切到 `<root>\updates`；
- 备份失败重试、逐项恢复、`installing.lock`、`install.log` 和
  `last-update-error.txt` 被补齐；
- 恢复不完整时保留锁，Tauri 在后端启动前拒绝运行混合版本；
- CI 使用相同 NSIS 脚本执行成功、目录锁回滚和自动重启 probe；
- 版本提升为 `2.1.1`，发布工作流禁止覆盖已发布资产。

### 3.3 Windows CI 已验证到哪里

GitHub Actions run
[`33369481282`](https://github.com/GresonKwan/GO-Claw-2.0/actions/runs/33369481282)
在提交 `50a1460bb53106f7016c8f73950b13d7ecb1eb18` 上成功，Windows job 为
`99417079152`。其中 `Build portable update package (NSIS)` 执行了
`scripts/verify/test_portable_update.ps1` 并通过。

这个测试证明：

- 更新器能从模拟的 `binaries\qwenpaw-backend` cwd 切走；
- 小型 payload 能完成备份、替换、写版本和自动启动 probe exe；
- 人工占用 `binaries` 时能回滚且不留下混合版本。

这个测试**没有证明**：

- 完整 477MB payload 能在真实 v2.0.1 文件树上全部释放；
- U 盘文件系统、杀毒软件或真实子进程不会继续占用 `binaries`；
- 完整新 exe/backend 自动启动后报告的运行版本一定是 v2.1.1；
- 同一目录多次失败后遗留的备份和锁不会影响下一次测试。

### 3.4 staging 启动误判与最新结果

最初使用 `set GO_CLAW_UPDATE_ENDPOINTS=...` 后再次启动 EXE，没有真正创建新实例。截图中
Windows 托盘仍有旧 GO CLAW；Tauri 单实例插件把第二次启动转发给旧 v2.0.1 进程后退出，旧
后端继续使用它启动时继承的生产 endpoint，所以仍显示 v2.1.0。

提交 `77f7916e` 增加 `scripts/verify/launch_portable_update_staging.cmd`：先结束旧 Tauri 和
backend 进程，再设置 staging endpoint，并从脚本所在目录以绝对路径启动 EXE。它只解决
“旧单实例没有继承 staging 环境变量”，**不证明更新安装成功**。

2026-08-31 用户随后再次进行实机更新，结果仍然失败。失败后的 `install.log`、
`last-update-error.txt`、进程列表和文件树尚未在仓库中取得，因此本次失败处于**原因未知**状态；
不得继续沿用“仍是 updater 自身 cwd 锁”这一未经新证据确认的结论。

### 3.5 2026-09-01 新盘 P0（不要与在线更新事故混淆）

当天新拷贝 v2.1.1 的 G、F 两块空产品盘均出现额度条缺失、生图生视频工具不可用。现场证据为：

- 盘内只有 Main Build 注入的静态 `GO-CLAW-Config/credentials.json`，没有
  `provision.json` 和 `data/instance.id`，所以 `/api/console/quota` 无法识别实例；
- qwen-image/wan27 两个捆绑插件 manifest 的 host 上限仍为 `2.1.0`，在 v2.1.1 上不兼容；
- 本地最小修复后，两块盘的额度接口、两个媒体插件和五个员工均恢复。

PR #4 分支 `codex/hotfix-v2-1-1-media-agents` 已包含媒体插件/员工修复；后续正式构建合同改为
provisioning-only，并增加 Full ZIP schema 3、禁止静态凭据混装及额度运行验证。这些证据证明
“全新 Full ZIP 交付”故障的根因，**不证明** 477MB 在线更新事务成功。生产更新软链仍不得修改，
本交接 §7 的干净 v2.0.1 实机复现和取证门禁保持不变。

## 4. 当前发布和服务器事实

### 4.1 生产（不要修改）

| 项目 | 当前值 |
| --- | --- |
| manifest | `https://goclaw.host:8443/updates/latest.json` |
| manifest 版本 | `2.1.0` |
| 服务器软链真实目标 | `/srv/go-claw-updates/releases/2.1.0-a9ab44b` |
| 状态 | 已知不能完成 v2.0.1 原地更新 |

### 4.2 v2.1.1 staging

| 项目 | 当前值 |
| --- | --- |
| manifest | `https://goclaw.host:8443/updates-staging/2.1.1/latest.json` |
| update exe | `https://goclaw.host:8443/updates-staging/2.1.1/GO-CLAW-Update-2.1.1-setup.exe` |
| update exe 大小 | `477092325` bytes |
| update exe SHA-256 | `1e21ec0e485258513252f19128f09d114e1511e5029b21472f2ff5b6e63ef34d` |
| staging launcher ZIP | `https://goclaw.host:8443/updates-staging/2.1.1/GO-CLAW-v2.1.1-Staging-Test-Launcher.zip` |
| launcher ZIP SHA-256 | `4afad8861d113c840257f5768e6e4aa24b16c9f354e99b0170ca433bcb7f0500` |

服务器为 `1.14.203.54`，更新文件位于
`/srv/go-claw-updates/updates-staging/2.1.1/`，Nginx 配置为
`/etc/nginx/conf.d/newapi-8443.conf`。SSH 私钥不在仓库中；从已有安全备份单独取得，绝不提交。

2026-08-31 已复核生产软链、上述三个 staging 文件 SHA-256、HTTP 200 和 `nginx -t`。

## 5. 运行时合同和关键代码

以下行号以代码 HEAD `77f7916e` 为准。后续修改后应优先按符号名检索。

| 合同 | 实现位置 |
| --- | --- |
| endpoint 默认值与 `GO_CLAW_UPDATE_ENDPOINTS` 覆盖 | `src/qwenpaw/app/go_claw_updates.py:37-44,205-209` |
| 便携根 = `QWENPAW_WORKING_DIR` 的父目录 | `src/qwenpaw/app/go_claw_updates.py:53-59` |
| 下载缓存与 `update-meta.json` | `src/qwenpaw/app/go_claw_updates.py:312-363` |
| 安装前二次 SHA-256 + Ed25519 验证 | `src/qwenpaw/app/go_claw_updates.py:367-374` |
| NSIS 命令 `/S /D=<root>` 及安全 cwd | `src/qwenpaw/app/go_claw_updates.py:415-442` |
| 单实例转发和 `--portable-quit` | `console/src-tauri/src/lib.rs:27-40` |
| backend 打包路径和 cwd | `console/src-tauri/src/backend/command.rs:45-62,125-147` |
| 未完成更新锁阻止启动 | `console/src-tauri/src/portable.rs:104-136` |
| NSIS 初始化、路径检查、切 cwd、建锁 | `console/src-tauri/nsis/go-claw-update.nsi:161-229` |
| 停进程、备份和替换 | `console/src-tauri/nsis/go-claw-update.nsi:231-304` |
| 成功重启与失败恢复 | `console/src-tauri/nsis/go-claw-update.nsi:306-344` |
| Windows 可执行事务测试 | `scripts/verify/test_portable_update.ps1` |

更新 payload 只允许替换：

- `GO-CLAW-Portable.exe`
- `binaries/`
- `LICENSE`
- `README-PORTABLE.zh-CN.txt`

更新不得覆盖：

- `portable.json`
- `GO-CLAW-Config/`
- `data/`、`secrets/`、`logs/`、`cache/`、`backups/`、`updates/`

后端公开更新接口是：

- `GET /api/updates/status`
- `POST /api/updates/check`
- `POST /api/updates/download`
- `POST /api/updates/install`
- `POST /api/updates/install-version`
- `GET /api/updates/releases`

`currentVersion` 来自新 backend 编译入包的 `src/qwenpaw/__version__.py`，而
`updates\version.txt` 是 NSIS 写入的事务标记。两者必须同时为 `2.1.1` 才能判定更新完整。

## 6. 当前最值得验证的假设（不是结论）

按取证优先级排列：

1. 真实 backend 派生的 Python、Node、插件或媒体进程仍以 `binaries` 内路径运行；现有 NSIS
   只按 `GO-CLAW-Portable.exe` 和 `qwenpaw-backend.exe` 名称兜底结束进程，CI probe 没有模拟
   真实进程树。
2. 完整 payload 在 U 盘上触发路径长度、杀毒扫描、写入失败、空间不足或文件系统行为，
   而小型 NTFS runner probe 不覆盖这些条件。
3. 安装已写入部分 v2.1.1 文件但元数据或重启失败，随后回滚到 v2.0.1；必须以
   `install.log` 的最后阶段和备份树判断，不能仅看浏览器版本。
4. 反复使用同一测试目录留下 `backup-*`、`installing.lock` 或缓存，使后续测试不再是干净的
   v2.0.1 → v2.1.1。
5. 自动重启启动了另一个目录中的旧 EXE，或者浏览器仍连接旧端口/旧后端。需同时记录进程
   `ExecutablePath`、浏览器端口、`/api/version` 和两处版本标记。

只有新现场证据支持后，才能改动对应代码。不要同时修改多条假设。

## 7. 全新 Windows 电脑上的唯一复现流程

### 7.1 建立两个互不污染的样本

先把原始 v2.0.1 完整目录保存为只读基准，每次测试都从它复制新目录，禁止在失败目录上连续
重试。第一轮使用短 NTFS 路径隔离 U 盘因素，例如：

```text
C:\GC201-BASELINE
C:\GC201-TRY-001
```

第二轮再从同一基准复制到 U 盘根目录的短路径，例如 `E:\GC201-TRY-001`。如果 NTFS 成功、
U 盘失败，才进入文件系统/杀毒/设备方向；如果两者同阶段失败，优先查进程和安装事务。

每个样本必须保留 `portable.json`、完整 `binaries` 和原来的客户数据副本。不要把真实客户
凭据提交到仓库。

### 7.2 失败后立即采集的最小证据

失败后不要手动双击 EXE。先在 PowerShell 中设置本次实际根目录：

```powershell
$Root = 'C:\GC201-TRY-001'
$Evidence = Join-Path $env:TEMP ('go-claw-update-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $Evidence | Out-Null
```

采集进程及其真实路径：

```powershell
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match 'GO-CLAW|qwenpaw|python|node|ffmpeg' -or
    $_.ExecutablePath -like "$Root*"
  } |
  Select-Object Name,ProcessId,ParentProcessId,ExecutablePath,CommandLine |
  Format-List | Out-File (Join-Path $Evidence 'processes.txt') -Encoding utf8
```

采集事务文件和目录元数据：

```powershell
Get-ChildItem -LiteralPath (Join-Path $Root 'updates') -Force -Recurse |
  Select-Object FullName,Length,LastWriteTime |
  Format-Table -AutoSize | Out-File (Join-Path $Evidence 'updates-tree.txt') -Encoding utf8

$Files = @(
  'updates\install.log',
  'updates\last-update-error.txt',
  'updates\last-update.json',
  'updates\version.txt',
  'updates\installing.lock',
  'updates\cached-update\update-meta.json'
)
foreach ($Relative in $Files) {
  $Source = Join-Path $Root $Relative
  if (Test-Path -LiteralPath $Source) {
    $Name = $Relative.Replace('\', '__')
    Copy-Item -LiteralPath $Source -Destination (Join-Path $Evidence $Name)
  }
}
```

记录新旧程序是否存在、大小、时间和哈希：

```powershell
$Programs = @(
  'GO-CLAW-Portable.exe',
  'binaries\qwenpaw-backend\qwenpaw-backend.exe',
  'updates\cached-update\update.exe'
)
foreach ($Relative in $Programs) {
  $Path = Join-Path $Root $Relative
  if (Test-Path -LiteralPath $Path) {
    Get-Item -LiteralPath $Path |
      Select-Object FullName,Length,CreationTime,LastWriteTime |
      Format-List | Out-File (Join-Path $Evidence 'program-files.txt') -Append -Encoding utf8
    Get-FileHash -Algorithm SHA256 -LiteralPath $Path |
      Format-List | Out-File (Join-Path $Evidence 'program-hashes.txt') -Append -Encoding utf8
  }
}
Compress-Archive -Path (Join-Path $Evidence '*') -DestinationPath "$Evidence.zip"
Write-Host "Evidence: $Evidence.zip"
```

这些命令只收集进程、更新事务文件和程序哈希，不收集 `credentials.json`、`secrets/`、
`data/` 或业务内容。把生成的 ZIP 交给同一台 Windows 机器上的 Codex 分析。

### 7.3 对证据的机械判定顺序

1. `installing.lock` 存在：事务未完整成功或未完整恢复；禁止启动程序，先查 `install.log`。
2. `last-update-error.txt` 存在：读取 `version`、`stage`、`restore`，以它作为本次失败阶段。
3. `install.log` 最后一行是 `stage=restart-new`：文件替换已完成，问题集中在新 EXE 启动。
4. 最后一行是 `stage=backup:*`：仍有句柄或旧备份目标问题；用 `processes.txt` 找路径在根目录
   内的残留进程。
5. `updates\version.txt=2.1.1` 但 UI `/api/version` 是 2.0.1：启动了旧 backend、旧目录或旧
   浏览器会话。
6. `updates\version.txt=2.0.1` 且 `restore=ok`：本次明确回滚，不得称为安装成功。
7. 没有任何安装日志：NSIS 没进入设置日志之后的事务；优先检查 `/D` 根、路径长度、既有锁、
   启动命令和 Windows 事件/安全软件记录。

## 8. 修改和验证纪律

每轮只针对一条已被证据证实的原因做最小修改，并至少执行：

```powershell
uv run pytest tests/unit/app/test_go_claw_updates.py `
  tests/unit/scripts/test_go_claw_update_installer.py `
  tests/unit/scripts/test_go_claw_release_workflows.py `
  tests/unit/scripts/test_portable_staging_launcher.py -q

cargo test --manifest-path console/src-tauri/Cargo.toml portable::tests
```

修改 NSIS 后必须在 Windows 执行真实脚本：

```powershell
.\scripts\verify\test_portable_update.ps1 `
  -NsisScript .\console\src-tauri\nsis\go-claw-update.nsi
```

随后触发 Windows-only workflow，记录 run ID、commit SHA 和 artifact SHA。最终发布门禁不是
CI probe，而是：

1. 从未经失败污染的完整 v2.0.1 样本开始；
2. 通过 staging manifest 下载完整 v2.1.1 更新包；
3. 安装完成后 `GO-CLAW-Portable.exe` 和完整 `binaries` 已归位；
4. `installing.lock`、`last-update-error.txt` 均不存在；
5. `updates\version.txt`、后端 `/api/version`、UI 当前版本均为 `2.1.1`；
6. 程序自动重新启动，数据和本地凭据保持；
7. 同一套验收在本地 NTFS 和目标 U 盘各通过一次。

满足全部条件前，保持 production `2.1.0` 软链不动，并在事实基线中维持“事故未解决”。

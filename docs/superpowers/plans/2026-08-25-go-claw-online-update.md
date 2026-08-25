# GO CLAW 在线更新功能实施计划（方案 C：Tauri updater + 自家 Release）

> 状态：已完成（2026-08-26，代码与 D2 密钥运维均已落地）
> 客户形态：U盘/本地目录，根目录有 `GO CLAW.exe`（非安装版）。更新包必须只替换程序文件，永不触碰 `data/`、`GO-CLAW-Config/`、`portable.json`、`updates/`。

## 〇、现状盘点（已核实，方案以此为基础）

已有可复用资产：

- `console/src-tauri/src/updates.rs`：完整自定义流程——检查（`check_desktop_update` :74）→ 后台下载缓存（`run_background_download` :137）→ **安装前对缓存字节二次验签**（:199-213）→ 停后端 → 启动 NSIS 并退出进程（`install_cached_windows` :241）。当前被 `updates_allowed()`（:29，`!portable`）整体禁用。
- `updates/{cache,remote,signature,version,events}.rs`：缓存、远端 manifest 拉取、minisign 验签、版本比较、事件。
- 前端已有：`contexts/DesktopUpdateContext.tsx`（更新状态机）、`components/UpdateTakeoverPage`（安装接管页）、`App.tsx` 接线。
- `portable.rs:27-35` `PortableState.root`：便携根目录绝对路径（安装时传给 NSIS `/D=`）。
- CI 已产出 NSIS（`desktop-build.yml:181` `bundle/nsis`）和便携 ZIP + `.sha256`。

缺口（本次要补的）：自有签名密钥与通道、便携放行、更新专用 NSIS 包、CI 签名与发布、定时检测、版本历史 UI、回滚。

## 一、各处约定标准（耦合点契约）

**C1. 更新 manifest（CI → 客户端）**——Tauri updater 标准格式，发布为 GitHub Release 资产 `latest.json`：
```json
{
  "version": "2.0.2",
  "notes": "更新说明（中文）",
  "pub_date": "2026-08-26T02:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "url": "https://github.com/GresonKwan/GO-Claw-2.0/releases/download/portable-v2.0.2/GO-CLAW-Update-2.0.2-setup.exe",
      "signature": "<minisign signature of the setup.exe, base64>"
    }
  }
}
```
`endpoints` 指向 `https://github.com/GresonKwan/GO-Claw-2.0/releases/latest/download/latest.json`（GitHub 支持 latest 重定向，免改客户端）。

**C2. 签名**：minisign 密钥对。公钥写进 `tauri.conf.json:78`（替换上游）；私钥存 GitHub Secret `GO_CLAW_UPDATE_SIGN_KEY`，仅 CI 使用。客户端只认这把钥匙 → H1（被上游覆盖）根治。

**C3. 更新 NSIS 包契约**（`install_cached_windows` → NSIS）：
- 调用约定：`<pkg>.exe /S /D=<portable_root>`（静默 + 目标目录；`/D` 必须最后且不带引号——NSIS 硬性要求）。
- 包内容 = 便携 staging 目录全部程序文件（`GO CLAW.exe`、`binaries/`、`resources/` 等），**构建时就不含** `data/`、`GO-CLAW-Config/`、`portable.json`（这三者由 stage 脚本/首启生成，不属于程序文件）。
- 安装逻辑（自定义 `.nsh`）：覆盖写入前把根目录下**除** `data/`、`GO-CLAW-Config/`、`portable.json`、`updates/` 之外的内容移入 `updates/backup-<旧版本号>/`（回滚点），再释放新文件；写 `updates/last-update.json`（版本/时间/备份路径）。
- 若备份或释放失败：尽力将 backup 移回，退出码非 0。

**C4. 前端 ↔ Rust**：复用现有 Tauri commands（`check_desktop_update` / `download_desktop_update` / `install_downloaded_update` / `check_cached_update`）与 `update:*` 事件、前端 `DesktopUpdateContext`。新增仅 2 处：定时触发与版本历史列表。

**C5. portable.json**：新增可选字段 `updates: {"enabled": true, "channel": "stable"}`（缺省即启用 stable；`enabled:false` 时全部更新接口返回 404，前端隐藏区块）。由 `stage_windows_portable.py:184` 写入。

**C6. Release 命名**：tag = `portable-v<version>`；资产 = `GO-CLAW-Portable-*-Windows-x64.zip`(+`.sha256`)、`GO-CLAW-Update-<version>-setup.exe`、`latest.json`。

## 二、文件级改动清单

### A. 配置与密钥

1. `console/src-tauri/tauri.conf.json:78-84`：pubkey 换为 GO CLAW 公钥；endpoint 换为 C1 的 GitHub latest.json URL；`windows.installMode` 保持 `passive` 或改 `quiet`（定 quiet——静默无英文向导）。
2. GitHub Secret 新增 `GO_CLAW_UPDATE_SIGN_KEY`（运维步骤，密钥一次性本地生成，私钥进 Secret、公钥进 A.1，公钥同时记入 `docs/` 备查不含私钥）。

### B. Rust 侧（`console/src-tauri/src/updates.rs`）

3. `updates_allowed()`（:29-31）：由 `!portable` 改为"便携模式仅在 `updates.enabled != false` 时允许"（读 portable.json；非便携/读不到配置按允许）。`PORTABLE_UPDATES_DISABLED` 常量与两个测试（:50-64）同步改写为"配置关闭时拒绝"的断言。
4. `install_cached_windows()`（:241-252）：参数由 `/P /R /UPDATE /NO_QWENPAW_PATH` 改为 `/S /D=<portable_root>`，root 从 `PortableRuntime` state 取（`portable.rs:27`）；非便携运行时回退原参数（保持安装版兼容）。

### C. 更新 NSIS 脚本（新文件 + hooks）

5. 新增 `console/src-tauri/nsis/go-claw-update.nsh`：实现 C3 的安装逻辑（备份 → 选择性释放 → 写 `last-update.json` → 失败回退）。主 `.nsi` 由 Tauri 模板生成，需在打包配置中挂 hooks（参照现有 `nsis-hooks.nsh` 的挂法）。
6. `nsis-hooks.nsh`：增补更新包专用的页面/语言精简（quiet 模式下基本不执行，防御性补齐）。

### D. CI（`.github/workflows/desktop-build.yml`）

7. Windows 打包步骤后新增"更新包构建"步骤：用便携 staging 目录 + `makensis` 产出 `GO-CLAW-Update-<version>-setup.exe`。
8. 新增"签名"步骤：minisign 用 `GO_CLAW_UPDATE_SIGN_KEY` 签 setup.exe（产出 `.minisig`）。
9. 新增"生成 latest.json"步骤（C1 格式，版本号取 `steps.version`，notes 取 release notes 或 commit 摘要）。
10. 新增"发布 Release"步骤（仅 main + dispatch）：`softprops/action-gh-release`，tag `portable-v<version>`，上传 ZIP、`.sha256`、setup.exe、`.minisig`、`latest.json`（`make_latest: true` 或发布后把 `latest` 指向它——保证 endpoints 的 `/releases/latest/download/latest.json` 总是最新）。

### E. 前端

11. `App.tsx`：启动后 5 分钟首次 + 每 6 小时调 `check_desktop_update`（`setInterval`，遵循 C5 的 enabled）。
12. `contexts/DesktopUpdateContext.tsx` + `UpdateTakeoverPage`：过一遍文案（全部中文化），确认便携模式状态机正确（available → downloading → ready → installing → takeover → 进程退出）。
13. `SidebarSettingsPanel.tsx`（齿轮弹层）新增"版本与更新"区块：当前版本、检查更新按钮、新版提示 + 一键安装（二次确认"将自动重启"）、版本历史折叠列表。
14. `api/modules/updates.ts`（新）：封装 invoke 与 GitHub Releases 列表获取（`GET /repos/GresonKwan/GO-Claw-2.0/releases?per_page=10`，公网匿名）。

### F. 版本历史与回滚

15. 版本历史 = GitHub Releases 列表（C6 资产命名解析出版本/日期/资产 URL）；每行提供"安装此版本"（老版本走同一下载-验签-安装流程，实现回滚）。
16. `updates/backup-<ver>/` 是本地快速回滚点；v1 仅作为容灾存在（不自动用），文档注明手工恢复方法。

### G. staging 脚本

17. `scripts/pack-tauri/stage_windows_portable.py:184`：`portable.json` 写入 C5 的 `updates` 字段。

## 三、安全设计

- 签名强制：下载后 + 安装前**两次** minisign 验签（现有 :199-213 逻辑保留）；验签失败即删除缓存并终止。
- 只自动下载，绝不自动安装；安装必须用户点击 + 二次确认。
- 更新包构建时即不含数据/凭证/配置；NSIS 脚本另有目录黑名单（C3）双保险。
- endpoint 固定 GitHub https；manifest 与资产同源（同 Release）。
- `updates.enabled=false` 一键全局关闭（禁网/企业场景）。

## 四、验证计划

1. 单元/Rust 测试：`updates_allowed` 三态（便携+启用/便携+关闭/非便携）；install 参数拼装。
2. NSIS 脚本：本地 makensis 编译 + 在测试目录演练"备份→覆盖→回退"。
3. 端到端（本机）：造一个假 Release（旧版 setup.exe + latest.json），从旧便携包完整走"检测→下载→验签→安装→重启→版本号变化→data/credentials 完好"。
4. CI 全绿后出新包；新包发布后，用上一版包实测一次真实在线更新。

## 五、明确不做

自动安装（永不）、增量差分、macOS 更新（本期 Windows only）、安装版分发、Tauri 英文对话框（用自研中文 UI 驱动命令而非插件 UI）。

---

## 六、审查修正（2026-08-25，全项目 review 后并入，优先级高于前文冲突处）

1. **portable.json 兼容**：`PortableManifest`（`portable.rs:14-24`）带 `deny_unknown_fields`——Rust 侧先给 struct 增加 `updates` 字段（`#[serde(default)]`，schemaVersion 保持 1），stage 脚本**默认不写**该字段（缺省即启用）；仅禁网场景在构建时显式写 `enabled:false`（旧 exe 读含新字段的文件会拒绝启动，故不默认写入）。
2. **更新包内容与替换逻辑一律白名单**：打包只含 `GO CLAW.exe` + `binaries/` + `resources/`（许可/说明）；NSIS 替换同样按白名单覆盖。**严禁**将 `GO-CLAW-Config/`（含批次 credentials.json——若进公开 Release 等于泄露 API key）、`portable.json`、`data/`、`secrets/`、`backups/`、`logs/`、`cache/`、`updates/` 打入或触碰。
3. **插件自装路径改道**：便携模式下 `run_install`（`updates.rs:100-120`，Tauri 插件自装）与 `install_cached_windows` 统一走"`/S /D=<root>` 解压安装"；Header 弹窗的"立即安装"按钮同路径，杜绝装进 Program Files。
4. **三处密钥一致**：`tauri.conf.json` pubkey/endpoint、GitHub Variables `TAURI_UPDATER_PUBKEY`/`TAURI_UPDATER_ENDPOINTS`（构建时注入，优先级更高）、`signature.rs` 二次验签读取源，三者必须同步更新，否则验签必败。
5. **缓存迁移**：便携模式更新缓存从 `%LOCALAPPDATA%` 迁到 `<root>\updates\cached-update`（verify 脚本断言便携不写主机目录，不迁则 CI 必红）。
6. **回滚独立通道**：版本比较器只放行"严格更新"（`version.rs:99-111`），回滚新增独立 command：按 URL 下载 → 复用 `verify_cached_update` 验签 → `install_cached_windows`，绕开比较器与 stale-cache 清理。
7. **`/D=` 参数安全**：用 `std::os::windows::process::CommandExt::raw_arg` 手工拼接未加引号的 `/D=<root>`（NSIS 硬性要求 `/D` 最后且无引号）；root 预检不含 `"` 和换行、规范尾随反斜杠；NSIS 侧校验 `$INSTDIR` 含 `portable.json` 才动文件（防中文/空格/移动盘路径踩雷）。
8. **发布架构**：发布步骤并入 `desktop-publish.yml`（desktop-build.yml 声明不发布）；tag 用滚动 `portable-latest` 保证 endpoint 稳定（避免与正式 release 抢 `/releases/latest`）；复用现有 `TAURI_SIGNING_PRIVATE_KEY` 签名链与 `generate_update_manifest.py`，不另起第二把钥匙。
9. **更新中锁定**：`<root>\updates\installing.lock` 存在期间禁止启动业务（防半更新状态被双击拉起），启动检测清理/回滚。
10. **国内可达性**：endpoint 列表首位加 `https://goclaw.host:8443/updates/latest.json`（nginx 反代 GitHub Release 资产），GitHub 直连失败时自动回退；版本历史接口容忍 403 并本地缓存。
11. **与 CI 验证的共存**：`verify` 环境构建的便携包写 `updates.enabled:false`（或在 verify 脚本注入不可达 endpoint），防止冒烟时被真实新版提示干扰。


---

## 七、实施落点与架构修正（2026-08-26）

**关键架构修正**：便携浏览器模式下 console 无 Tauri IPC（`isDesktopApp()=false`），因此更新编排从 Rust 改为**后端 Python 驱动**（与额度条同构），Rust 侧能力保留给未来安装版。

| 层 | 文件 | 内容 |
|----|------|------|
| 后端编排 | `src/qwenpaw/app/go_claw_updates.py` | 状态机、manifest 拉取（镜像优先双 endpoint）、流式下载、sha256+minisign(Ed25519) 双重验签、`/S /D=` 安装、回滚独立通道、6h 定时检测+inbox 通知 |
| 路由 | `src/qwenpaw/app/routers/updates.py` | `/api/updates/{status,check,download,install,install-version,releases}`，便携关闭时 404 |
| 验签公钥入包 | `scripts/pack-tauri/stage_windows_portable.py` | 从 tauri.conf.json 提取 pubkey 写入 `GO-CLAW-Config/update-pubkey.txt` |
| NSIS 更新包 | `console/src-tauri/nsis/go-claw-update.nsi` | /D 校验 portable.json、taskkill 应用与后端、白名单备份+替换、installing.lock、自动重启 |
| CI | `desktop-build.yml` | 白名单 payload → makensis → tauri signer sign → `build_go_claw_update_manifest.py` 生成 latest.json → 上传 artifact |
| 发布 | `desktop-publish.yml` | setup.exe/.sig/latest.json 附到 Release |
| 前端 | `console/src/layouts/UpdateSection.tsx` + `api/modules/updates.ts` + `SidebarSettingsPanel` | 版本区块：检查/下载进度/一键安装（二次确认）/版本历史+回滚 |
| Rust（保留） | `updates.rs`/`cache.rs`/`portable.rs` | portable.json updates 字段、便携放行、/D= raw_arg、缓存迁根目录、install_update_from_url |
| 测试 | `tests/unit/app/test_go_claw_updates.py` | 版本比较、minisign 往返+篡改拒绝（含 key id 不匹配） |

**耦合契约（最终版）**：manifest=Tauri 标准 latest.json；签名=minisign（公钥入包、私钥仅 CI secret）；安装契约=`"<pkg>" /S /D=<root>`（无引号、raw 拼接）；数据黑名单=`data/secrets/logs/cache/backups/updates/GO-CLAW-Config/portable.json`；payload 白名单=`GO-CLAW-Portable.exe/binaries/LICENSE/README`。

**D2 密钥运维（已完成）**：已生成 GO CLAW 专用、非空口令保护的 Tauri 签名密钥，并将公钥同步到 `tauri.conf.json`、GitHub Variable `TAURI_UPDATER_PUBKEY` 与便携包自动生成链。保管、发布前检查、恢复与轮换规则见 `docs/GO-CLAW-在线更新签名密钥运维.zh.md`。

**可选镜像运维（未实施）**：goclaw.host nginx 增加 `/updates/` 反代到 GitHub Release 资产（镜像 endpoint 已内置为首选，未配置时会自动回退 GitHub 直连）。

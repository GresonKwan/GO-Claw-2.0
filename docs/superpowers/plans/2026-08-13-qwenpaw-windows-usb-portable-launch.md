# QwenPaw v2.0.1 Windows USB Portable Launch Implementation Plan

> 状态：已完成（2026-08-24 补标，见 GO CLAW 变更台账）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 10/11 x64 上，从 U 盘解压后的目录直接双击 `QwenPaw-Portable.exe`，无需安装或管理员权限即可启动 QwenPaw 核心，并自动打开本机客户端页面；QwenPaw 的配置、工作区、密钥、备份和应用日志跟随 U 盘移动。

**Architecture:** 复用 v2.0.1 已有的 Tauri 托盘外壳、PyInstaller sidecar、内置 Python/Node 运行时和后端就绪协议，不重写核心。新增由同一个 Rust binary 编译出的 portable flavor：通过 exe 同目录的 `portable.json` 启用便携路径契约，后端就绪后默认用系统浏览器打开 `/console`，可选尝试内置 WebView 并在失败时回退浏览器。portable flavor 禁用 NSIS 自动更新，用位置历史对配置中的 U 盘绝对路径做边界安全的内存重映射。

**Tech Stack:** Python 3.11 + PyInstaller onedir、Rust 2021 + Tauri 2、React/Vite 控制台、PowerShell、pytest、Cargo tests、GitHub Actions Windows runner。

---

## 评估结论与范围

### 结论

- 可行性高。v2.0.1 已有 Windows Tauri shell、后台 sidecar、自动初始化、动态端口、`QWENPAW_BACKEND_READY` 就绪协议、托盘退出、Python/Node 独立运行时和 `/api/healthz`；本项目主要是路径契约、启动界面策略和便携目录打包，不需要改 agent 核心。
- 建议第一版只支持 Windows 10/11 x64。官方 v2.0.1 Windows 发布物本身也是 x64 安装包；ARM64 放到后续里程碑。
- “双击即可”按以下口径验收：不安装 QwenPaw、不依赖系统 Python/Node、不要求管理员权限；系统浏览器是可接受的客户端承载方式。远程模型调用仍然需要网络和用户自己的 API key。
- 第一版默认 `clientMode: "browser"`，这是 U 盘场景最稳、改动最小的方案；同时实现 `"auto"`，在 WebView2 可用时使用内置窗口，创建失败则打开浏览器。固定版 WebView2 不进入第一版。
- 预计开发量 3–5 个工程日，另加 1–2 天真实 Windows/U 盘矩阵测试。代码签名和完整发布自动化若一起完成，按 1–2 周准备更稳妥。

### 为什么不直接分发现有安装包或单个 EXE

现有 NSIS 产物会安装到用户目录，并把日志、工作目录、WebView2 数据和更新缓存写到系统盘。Tauri raw exe 也不是单文件应用；它运行时仍需要旁边的 `binaries/qwenpaw-backend`、`binaries/python-runtime` 和 `binaries/node-runtime`。所以正确发布物是一个可整体复制到 U 盘的目录/ZIP，而不是孤立 exe。

### 关键缺口

1. `QWENPAW_WORKING_DIR`、`QWENPAW_SECRET_DIR`、`QWENPAW_BACKUP_DIR` 已支持环境覆盖，但 Tauri 当前没有按 exe 目录设置它们。
2. 初始配置把 `workspace_dir`、`media_dir` 等写成绝对路径。U 盘盘符从 `E:` 变成 `F:` 后，现有逻辑只会迁移旧的 `~/.copaw`，不会迁移任意旧 U 盘根目录。
3. shell 日志当前写 `%LOCALAPPDATA%`，WebView2 数据使用系统默认目录，更新缓存也在系统目录。
4. portable 目录没有 WebView2 安装器语义。把固定版 WebView2 塞进 U 盘会明显增大体积，而且 Windows 10 的 unpackaged Fixed Runtime 120+ 需要额外 ACL 处理；默认浏览器模式更稳。
5. 当前更新器下载并执行 NSIS 安装包，这会把 portable 用户带回“安装到电脑”的路径，必须在 portable 模式禁用。
6. 当前第二次启动会让新 sidecar 的 singleton guard 终止旧 sidecar。应由 shell 先做单实例，把第二次双击转成“再次显示页面”。

### 非目标与真实限制

- 不承诺 Windows “法证级零痕迹”。应用自己的数据放在 U 盘，但 Windows SmartScreen、Defender、最近使用记录，以及系统浏览器自身历史/缓存仍可能留在电脑上。
- 第一版不内置大模型权重。“核心”是 QwenPaw 后端、控制台、Python/Node runtime；本地模型由用户另行下载，可能额外占数 GB。
- 不支持运行中直接拔盘。必须通过托盘 Quit 让后端完成有界的优雅退出，然后再安全弹出 U 盘。
- exFAT 没有 NTFS ACL；`secrets/.master_key` 与密文同盘时，只能防止随手查看，不能抵御 U 盘遗失后的离线攻击。敏感场景应使用 BitLocker To Go，或后续增加口令派生密钥。
- 未签名 exe 在可移动介质上很容易触发 SmartScreen。公开发布前强烈建议做 Authenticode 签名；开发验证包可以先用 SHA-256 校验值交付。

### 验收标准

1. 在没有安装 QwenPaw、Python、Node 的干净 Windows 10/11 x64 机器上，把 ZIP 解压到 NTFS 或 exFAT U 盘后双击 `QwenPaw-Portable.exe`。
2. 120 秒内 `/api/healthz` 返回 200，系统浏览器或内置 WebView 自动打开 `http://127.0.0.1:随机端口/console`。
3. 首次启动自动生成配置；退出再启动仍使用同一个工作区、会话和端口偏好。
4. 将同一目录从一个路径/盘符移动到另一个路径/盘符，agent profile、workspace、媒体目录仍能加载；位于 U 盘目录以外的用户自定义绝对路径不被改写。
5. QwenPaw 自己的 `data/`、`secrets/`、`backups/`、`logs/`、`cache/` 全在 portable 根目录；测试前后不新建 `%USERPROFILE%\.qwenpaw`，不在 `%LOCALAPPDATA%\io.agentscope.qwenpaw.desktop` 写应用日志或更新缓存。
6. 第二次双击不重启或杀死正在工作的后端，只重新聚焦内置窗口或再次打开当前浏览器页面。
7. portable 模式的更新检查返回“无更新”，安装/下载命令明确拒绝；安装版的更新行为保持不变。
8. 从托盘 Quit 后，shell 与 `qwenpaw-backend.exe` 都退出，配置和内存索引完成落盘。
9. 发布 ZIP 包含许可证、中文快速说明、portable manifest 和 SHA-256 文件；解压后的资源布局通过自动化校验。

### 目标目录布局

```text
QwenPaw-Portable-2.0.1-Windows-x64/
├── QwenPaw-Portable.exe
├── portable.json
├── LICENSE
├── README-PORTABLE.zh-CN.txt
├── binaries/
│   ├── qwenpaw-backend/
│   │   └── qwenpaw-backend.exe
│   ├── python-runtime/
│   │   └── python/python.exe
│   └── node-runtime/
│       └── node.exe
├── data/                    # 首次启动创建
├── secrets/                 # 首次启动创建，不放进 data/workspace
├── backups/                 # 首次启动创建
├── logs/                    # 首次启动创建
└── cache/webview2/          # 仅 clientMode=auto/webview 时创建
```

## Task 0: 建立可提交的干净基线

**Files:**

- Verify: `src/qwenpaw/__version__.py`
- Verify: `console/src-tauri/Cargo.toml`

- [ ] **Step 1: 从官方 tag 创建独立实现仓库**

当前分析目录来自官方 tag archive，不带 `.git`；不要在上层 GO Claw 的脏工作树里做实现提交。执行：

```powershell
git clone --branch v2.0.1 --single-branch https://github.com/agentscope-ai/QwenPaw.git QwenPaw-portable
Set-Location QwenPaw-portable
git rev-parse HEAD
```

Expected: `ed5857b546e732174d601b0ea5ca1a081a900b98`。

- [ ] **Step 2: 创建实现分支并记录干净状态**

```powershell
git switch -c codex/windows-usb-portable-v2.0.1
git status --short
python -c "from qwenpaw.__version__ import __version__; assert __version__ == '2.0.1'"
```

Expected: `git status --short` 无输出，版本断言退出 0。

- [ ] **Step 3: 跑最小基线测试**

```powershell
uv venv
uv pip install -e ".[test,dev]"
uv run pytest tests/unit/tauri/test_entry.py -q
cargo test --manifest-path console/src-tauri/Cargo.toml
```

Expected: 两组测试全部通过。若官方 tag 在当前 Rust 解析版本下出现锁文件问题，先记录原始错误，不要无理由升级依赖。

## Task 1: 增加可移动路径历史和配置重映射

**Files:**

- Create: `src/qwenpaw/portable.py`
- Modify: `src/qwenpaw/tauri/entry.py:330-375`
- Modify: `src/qwenpaw/config/utils.py:54-91`
- Create: `tests/unit/test_portable.py`
- Modify: `tests/unit/tauri/test_entry.py`

- [ ] **Step 1: 先写位置历史和边界重映射的失败测试**

在 `tests/unit/test_portable.py` 写清楚三条行为：记录当前位置、移动后把旧根目录加入历史、只改写旧根目录边界内的已知路径键。

```python
from __future__ import annotations

import json
from pathlib import Path

from qwenpaw.portable import (
    PORTABLE_ROOT_HISTORY_ENV,
    prepare_portable_location_history,
)
from qwenpaw.config.utils import _normalize_working_dir_bound_paths


def test_portable_history_survives_directory_move(monkeypatch, tmp_path):
    old_data = tmp_path / "old" / "data"
    old_data.mkdir(parents=True)
    prepare_portable_location_history(old_data)
    new_data = tmp_path / "new" / "data"
    new_data.parent.mkdir()
    old_data.rename(new_data)
    history = prepare_portable_location_history(new_data)
    marker = new_data / ".portable-location.json"

    assert str(old_data.resolve()) in history
    assert str(new_data.resolve()) in history
    assert json.loads(marker.read_text("utf-8"))[
        "workingDirs"
    ] == history


def test_normalize_rebases_known_paths_but_preserves_external(monkeypatch, tmp_path):
    old_root = tmp_path / "old" / "data"
    new_root = tmp_path / "new" / "data"
    monkeypatch.setenv(
        PORTABLE_ROOT_HISTORY_ENV,
        json.dumps([str(old_root), str(new_root)]),
    )
    monkeypatch.setattr("qwenpaw.config.utils.WORKING_DIR", new_root)
    original = {
        "agents": [{"workspace_dir": str(old_root / "workspaces" / "default")}],
        "channels": {"x": {"media_dir": str(old_root / "media")}},
        "coding_mode": {"project_dir": str(tmp_path / "external-project")},
        "label": str(old_root / "must-not-change-because-key-is-not-a-path"),
    }

    normalized = _normalize_working_dir_bound_paths(original)

    assert normalized["agents"][0]["workspace_dir"] == str(
        new_root / "workspaces" / "default"
    )
    assert normalized["channels"]["x"]["media_dir"] == str(new_root / "media")
    assert normalized["coding_mode"]["project_dir"] == str(
        tmp_path / "external-project"
    )
    assert normalized["label"] == original["label"]


def test_normalize_does_not_match_similar_prefix(monkeypatch, tmp_path):
    old_root = tmp_path / "disk" / "data"
    new_root = tmp_path / "moved" / "data"
    monkeypatch.setenv(PORTABLE_ROOT_HISTORY_ENV, json.dumps([str(old_root)]))
    monkeypatch.setattr("qwenpaw.config.utils.WORKING_DIR", new_root)

    value = str(old_root.parent / "database" / "media")
    assert _normalize_working_dir_bound_paths({"media_dir": value}) == {
        "media_dir": value,
    }
```

- [ ] **Step 2: 运行测试确认先失败**

```powershell
uv run pytest tests/unit/test_portable.py -q
```

Expected: collection 因 `qwenpaw.portable` 不存在而失败。

- [ ] **Step 3: 实现原子位置历史文件**

新增 `src/qwenpaw/portable.py`。历史文件放在 `WORKING_DIR` 内，目录移动时会一起移动；保留所有已知旧位置，避免一次启动失败后丢失可迁移根目录。

```python
from __future__ import annotations

import json
import os
from pathlib import Path

PORTABLE_MODE_ENV = "QWENPAW_PORTABLE"
PORTABLE_ROOT_HISTORY_ENV = "QWENPAW_PORTABLE_ROOT_HISTORY"
_LOCATION_FILE = ".portable-location.json"
_SCHEMA_VERSION = 1


def is_portable_mode() -> bool:
    return os.environ.get(PORTABLE_MODE_ENV, "").lower() in {
        "1", "true", "yes", "on",
    }


def prepare_portable_location_history(working_dir: Path) -> list[str]:
    current = str(working_dir.expanduser().resolve())
    marker = working_dir / _LOCATION_FILE
    history: list[str] = []
    if marker.is_file():
        try:
            raw = json.loads(marker.read_text(encoding="utf-8"))
            if raw.get("schemaVersion") == _SCHEMA_VERSION:
                history = [
                    str(value) for value in raw.get("workingDirs", [])
                    if isinstance(value, str) and value
                ]
        except (OSError, ValueError, TypeError):
            history = []
    if current not in history:
        history.append(current)
    working_dir.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"schemaVersion": _SCHEMA_VERSION, "workingDirs": history},
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, marker)
    os.environ[PORTABLE_ROOT_HISTORY_ENV] = json.dumps(history)
    return history
```

- [ ] **Step 4: 扩展现有路径规范化逻辑**

在 `src/qwenpaw/config/utils.py` 中保留 `~/.copaw` 兼容逻辑，再解析 `QWENPAW_PORTABLE_ROOT_HISTORY`。仅处理 `workspace_dir`、`media_dir`、`project_dir` 三种键；使用 `Path.relative_to` 做路径边界判断，不能用字符串 `startswith`。

```python
def _portable_roots() -> list[Path]:
    raw = os.environ.get("QWENPAW_PORTABLE_ROOT_HISTORY", "")
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    return [Path(v).expanduser() for v in values if isinstance(v, str) and v]


def _rebase_portable_path(value: str) -> str:
    candidate = Path(value).expanduser()
    current = Path(WORKING_DIR)
    for old_root in _portable_roots():
        if os.path.normcase(str(old_root)) == os.path.normcase(str(current)):
            continue
        try:
            relative = candidate.relative_to(old_root)
        except ValueError:
            continue
        return str(current / relative)
    return value
```

把 `_walk` 的键集合改为：

```python
if key in {"workspace_dir", "media_dir", "project_dir"}:
    rewritten = _rewrite_path_value(obj)
    if isinstance(rewritten, str):
        return _rebase_portable_path(rewritten)
    return rewritten
```

Windows 的路径大小写测试必须在 Windows CI 上执行；不要在 POSIX 上用 `PureWindowsPath` 假装覆盖真实 `Path` 行为。

- [ ] **Step 5: 在 sidecar 初始化前准备历史**

在 `src/qwenpaw/tauri/entry.py::main` 导入 `WORKING_DIR` 后、读取 `config.json` 前加入：

```python
from qwenpaw.portable import (
    is_portable_mode,
    prepare_portable_location_history,
)

if is_portable_mode():
    prepare_portable_location_history(WORKING_DIR)
```

并在 `tests/unit/tauri/test_entry.py::test_main_supports_frozen_entry_without_package_context` mock `prepare_portable_location_history`，另加断言：portable 环境下该函数在 `_run_backend_server` 之前被调用。

- [ ] **Step 6: 跑精确测试和配置回归**

```powershell
uv run pytest tests/unit/test_portable.py tests/unit/tauri/test_entry.py -q
uv run pytest tests/unit -q -k "config or agent_config or portable"
```

Expected: 全部通过；外部 `project_dir` 不被移动。

- [ ] **Step 7: 提交**

```powershell
git add src/qwenpaw/portable.py src/qwenpaw/tauri/entry.py src/qwenpaw/config/utils.py tests/unit/test_portable.py tests/unit/tauri/test_entry.py
git commit -m "feat(portable): rebase data paths across removable drives"
```

## Task 2: 建立 Rust portable 路径契约并把日志留在 U 盘

**Files:**

- Create: `console/src-tauri/src/portable.rs`
- Modify: `console/src-tauri/src/lib.rs:1-80`
- Modify: `console/src-tauri/src/backend.rs:314-337`
- Create: `console/src-tauri/tauri.portable.conf.json`

- [ ] **Step 1: 写 portable manifest/path resolver 的失败单测**

在新文件 `console/src-tauri/src/portable.rs` 先写测试模块，固定预期路径，不修改进程环境：

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifest_resolves_all_mutable_paths_beside_exe() {
        let temp = tempfile::tempdir().unwrap();
        let exe = temp.path().join("QwenPaw-Portable.exe");
        std::fs::write(&exe, b"").unwrap();
        std::fs::write(
            temp.path().join(PORTABLE_MANIFEST),
            br#"{"schemaVersion":1,"clientMode":"browser"}"#,
        )
        .unwrap();

        let state = PortableState::detect_from_exe(&exe).unwrap().unwrap();

        assert_eq!(state.root, temp.path());
        assert_eq!(state.working_dir, temp.path().join("data"));
        assert_eq!(state.secret_dir, temp.path().join("secrets"));
    assert_eq!(state.backup_dir, temp.path().join("backups"));
    assert_eq!(state.log_dir, temp.path().join("logs"));
    assert_eq!(state.cache_dir, temp.path().join("cache"));
    assert_eq!(state.webview_dir, temp.path().join("cache/webview2"));
        assert_eq!(state.client_mode, ClientMode::Browser);
    }

    #[test]
    fn missing_manifest_means_installed_mode() {
        let temp = tempfile::tempdir().unwrap();
        let exe = temp.path().join("qwenpaw-desktop.exe");
        assert!(PortableState::detect_from_exe(&exe).unwrap().is_none());
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
cargo test --manifest-path console/src-tauri/Cargo.toml portable::tests
```

Expected: 因类型和实现不存在而编译失败。

- [ ] **Step 3: 实现 manifest、路径和环境设置**

`portable.json` 只负责显式启用模式，不能用“exe 在可移动盘”做隐式判断。核心实现如下：

```rust
use serde::Deserialize;
use std::path::{Path, PathBuf};

pub(crate) const PORTABLE_MANIFEST: &str = "portable.json";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "camelCase")]
pub(crate) enum ClientMode {
    Browser,
    Auto,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct PortableManifest {
    schema_version: u8,
    #[serde(default = "default_client_mode")]
    client_mode: ClientMode,
}

fn default_client_mode() -> ClientMode { ClientMode::Browser }

#[derive(Clone, Debug)]
pub(crate) struct PortableState {
    pub(crate) root: PathBuf,
    pub(crate) working_dir: PathBuf,
    pub(crate) secret_dir: PathBuf,
    pub(crate) backup_dir: PathBuf,
    pub(crate) log_dir: PathBuf,
    pub(crate) cache_dir: PathBuf,
    pub(crate) webview_dir: PathBuf,
    pub(crate) client_mode: ClientMode,
}

impl PortableState {
    fn detect_from_exe(exe: &Path) -> Result<Option<Self>, String> {
        let root = exe.parent().ok_or("portable exe has no parent directory")?;
        let marker = root.join(PORTABLE_MANIFEST);
        if !marker.is_file() { return Ok(None); }
        let manifest: PortableManifest = serde_json::from_slice(
            &std::fs::read(&marker).map_err(|e| format!("cannot read {}: {e}", marker.display()))?
        ).map_err(|e| format!("invalid {}: {e}", marker.display()))?;
        if manifest.schema_version != 1 {
            return Err(format!("unsupported portable schema {}", manifest.schema_version));
        }
        Ok(Some(Self {
            root: root.to_path_buf(),
            working_dir: root.join("data"),
            secret_dir: root.join("secrets"),
            backup_dir: root.join("backups"),
            log_dir: root.join("logs"),
            cache_dir: root.join("cache"),
            webview_dir: root.join("cache").join("webview2"),
            client_mode: manifest.client_mode,
        }))
    }

    pub(crate) fn detect() -> Result<Option<Self>, String> {
        let exe = std::env::current_exe().map_err(|e| format!("cannot resolve executable: {e}"))?;
        Self::detect_from_exe(&exe)
    }

    pub(crate) fn prepare(&self) -> Result<(), String> {
        for dir in [
            &self.working_dir,
            &self.secret_dir,
            &self.backup_dir,
            &self.log_dir,
            &self.cache_dir,
        ] {
            std::fs::create_dir_all(dir)
                .map_err(|e| format!("cannot create {}: {e}", dir.display()))?;
        }
        std::env::set_var("QWENPAW_PORTABLE", "1");
        std::env::set_var("QWENPAW_WORKING_DIR", &self.working_dir);
        std::env::set_var("QWENPAW_SECRET_DIR", &self.secret_dir);
        std::env::set_var("QWENPAW_BACKUP_DIR", &self.backup_dir);
        std::env::set_var("QWENPAW_DISABLE_KEYRING", "1");
        std::env::set_var("PIP_CACHE_DIR", self.cache_dir.join("pip"));
        std::env::set_var("UV_CACHE_DIR", self.cache_dir.join("uv"));
        Ok(())
    }
}
```

不要覆盖 `TEMP`、`TMP` 或整个用户 `HOME`；这些会引发第三方库兼容性和 U 盘写放大问题。

- [ ] **Step 4: 在 Tauri setup 里最早准备 portable 环境**

在 `lib.rs` 加 `mod portable;`。构建 Builder 前只调用 `PortableState::detect()`，把 `Option<PortableState>` 作为 managed state；在 `.setup` 中必须先 `portable.prepare()`，再执行 `backend::setup(app)` 和 `tray::setup(app)`。manifest 或目录不可写时，用已注册的 `tauri-plugin-dialog` 显示错误，再让 setup 返回失败。

```rust
let portable_state = portable::PortableState::detect()
    .unwrap_or_else(|err| panic!("portable startup validation failed: {err}"));

// ... Builder plugins and handlers ...
.manage(portable_state)
.setup(|app| {
    if let Some(state) = app.state::<Option<portable::PortableState>>().as_ref() {
        state.prepare().map_err(std::io::Error::other)?;
    }
    backend::setup(app)?;
    tray::setup(app)?;
    Ok(())
})
```

实现时不要保留 `panic!` 作为最终用户错误路径；把 detect error 存成 startup state，并在 setup 中显示本地对话框。测试纯 resolver，避免并行 Rust tests 竞争全局环境变量。

- [ ] **Step 5: portable 模式切换 logger target**

在 `backend::setup` 中根据 `Option<PortableState>` 选择 `TargetKind::Folder` 或现有 `TargetKind::LogDir`：

```rust
let file_target = match app.state::<Option<PortableState>>().as_ref() {
    Some(portable) => Target::new(TargetKind::Folder {
        path: portable.log_dir.clone(),
        file_name: Some("qwenpaw-desktop".into()),
    }),
    None => Target::new(TargetKind::LogDir {
        file_name: Some("qwenpaw-desktop".into()),
    }),
};
```

后端 `desktop.log` 已依据 `WORKING_DIR` 写入 `data/desktop.log`，无需再改。

- [ ] **Step 6: 增加独立 portable Tauri flavor**

新增 `console/src-tauri/tauri.portable.conf.json`。数组遵循 JSON Merge Patch，会整体替换，因此把完整 main window 配置复制过来并只新增 `"create": false`：

```json
{
  "productName": "QwenPaw Portable",
  "identifier": "io.agentscope.qwenpaw.portable",
  "app": {
    "windows": [
      {
        "label": "main",
        "create": false,
        "title": "QwenPaw Portable",
        "width": 1280,
        "height": 800,
        "minWidth": 960,
        "minHeight": 600,
        "resizable": true,
        "fullscreen": false,
        "dragDropEnabled": false
      }
    ]
  },
  "bundle": { "active": false }
}
```

安装版继续使用原配置自动创建窗口；portable 二次构建才合并这个 flavor，避免改变现有安装版首屏行为。
portable 使用独立 identifier，避免 single-instance mutex、系统路径或后续协议注册与已安装的 `io.agentscope.qwenpaw.desktop` 相互阻塞。

- [ ] **Step 7: 运行 Rust tests 和格式检查**

```powershell
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo test --manifest-path console/src-tauri/Cargo.toml portable::tests
cargo test --manifest-path console/src-tauri/Cargo.toml
```

Expected: 全部通过。

- [ ] **Step 8: 提交**

```powershell
git add console/src-tauri/src/portable.rs console/src-tauri/src/lib.rs console/src-tauri/src/backend.rs console/src-tauri/tauri.portable.conf.json
git commit -m "feat(portable): bind desktop state to executable directory"
```

## Task 3: 后端就绪后自动打开客户端，并提供浏览器回退

**Files:**

- Create: `console/src-tauri/src/client.rs`
- Modify: `console/src-tauri/src/lib.rs`
- Modify: `console/src-tauri/src/backend.rs:40-105`
- Modify: `console/src-tauri/src/backend/events.rs:25-70`
- Modify: `console/src-tauri/src/tray.rs:180-215`
- Modify: `console/src-tauri/src/external_link.rs`

- [ ] **Step 1: 写 URL 与模式选择失败测试**

先在 `client.rs` 写纯函数测试：

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn browser_url_uses_loopback_console_without_desktop_flag() {
        assert_eq!(
            browser_console_url(54321),
            "http://127.0.0.1:54321/console?portable=1"
        );
    }

    #[test]
    fn native_mode_starts_from_existing_bootstrap_config() {
        assert_eq!(launch_strategy(ClientMode::Browser), LaunchStrategy::Browser);
        assert_eq!(launch_strategy(ClientMode::Auto), LaunchStrategy::WebviewThenBrowser);
    }
}
```

- [ ] **Step 2: 运行确认编译失败**

```powershell
cargo test --manifest-path console/src-tauri/Cargo.toml client::tests
```

- [ ] **Step 3: 实现 portable client state 和系统浏览器打开**

复用已经注册的 shell plugin，不新增 opener crate。把 `external_link.rs` 中 Rust 内部打开能力拆成：

```rust
pub(crate) fn open_system_url(app: &tauri::AppHandle, url: &str) -> Result<(), String> {
    validate_external_url(url)?;
    #[allow(deprecated)]
    app.shell().open(url.to_string(), None).map_err(|err| err.to_string())
}
```

`client.rs` 管理最近端口和最后实际模式：

```rust
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LaunchStrategy { Browser, WebviewThenBrowser }

#[derive(Default)]
pub(crate) struct ClientState {
    port: std::sync::Mutex<Option<u16>>,
    browser_fallback: std::sync::atomic::AtomicBool,
}

fn browser_console_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/console?portable=1")
}

pub(crate) fn open_browser(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    external_link::open_system_url(app, &browser_console_url(port))
}
```

- [ ] **Step 4: 实现 auto 模式的 WebView 创建与回退**

portable config 的 main window `create=false`。`clientMode=auto` 时，在单独线程里用原有 window config 构建 bootstrap WebView，并把 UDF 放到 U 盘：

```rust
fn try_open_webview(app: &tauri::AppHandle, data_dir: PathBuf) -> Result<(), String> {
    let config = app.config().app.windows.first()
        .ok_or("main window config is missing")?;
    tauri::WebviewWindowBuilder::from_config(app, config)
        .map_err(|e| e.to_string())?
        .data_directory(data_dir)
        .build()
        .map(|_| ())
        .map_err(|e| e.to_string())
}
```

如果 build 返回错误，记录完整错误，设置 `browser_fallback=true`，调用 `open_browser`。默认 manifest 用 browser，因此 exFAT/缺 WebView2 的主路径不会创建 UDF。不能在同步 Tauri event handler 中直接创建 WebView；从 backend stdout async watcher 转交到独立线程。

- [ ] **Step 5: 让 ready event 只为当前 generation 打开一次**

把 `BackendState::set_port_if_current` 改成返回 `bool`：仅当 generation 当前且端口首次从 `None` 变成 `Some` 时返回 true。`events.rs`：

```rust
if app.state::<BackendState>().set_port_if_current(generation, port) {
    client::open_when_ready(app.clone(), port);
}
```

安装模式检测为 `None` 时 `open_when_ready` 必须 no-op，因为安装版已有 bootstrap window。portable 模式才浏览器/建窗口。

- [ ] **Step 6: 让托盘 Show 在无 WebView 时重新打开浏览器**

将 `BackendState::port()` 暴露为 `pub(crate)` 查询方法。`tray::show_main_window` 保留现有窗口聚焦逻辑；没有窗口且处于 portable 模式时，用当前 backend port 调用 `client::open_browser`。

后端在 ready 前失败时，portable 模式没有 bootstrap UI。对以下错误用 `tauri-plugin-dialog` 显示本地对话框，并提示日志位置：sidecar 不存在、spawn 失败、ready 前进程退出。对话框正文不得包含 shutdown token 或 API key。

- [ ] **Step 7: 补 current-generation 和重复 ready 测试**

扩展 `backend/events.rs`/`backend.rs` 单测，断言：旧 generation 不打开、同 generation 重复 ready 只打开一次、restart 后新 generation 可以再次打开。

- [ ] **Step 8: 运行测试**

```powershell
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo test --manifest-path console/src-tauri/Cargo.toml client::tests
cargo test --manifest-path console/src-tauri/Cargo.toml backend
```

- [ ] **Step 9: 提交**

```powershell
git add console/src-tauri/src/client.rs console/src-tauri/src/lib.rs console/src-tauri/src/backend.rs console/src-tauri/src/backend/events.rs console/src-tauri/src/tray.rs console/src-tauri/src/external_link.rs
git commit -m "feat(portable): open console when sidecar is ready"
```

## Task 4: 禁用安装式更新并处理重复双击

**Files:**

- Modify: `console/src-tauri/Cargo.toml`
- Modify: `console/src-tauri/Cargo.lock`
- Modify: `console/src-tauri/src/lib.rs`
- Modify: `console/src-tauri/src/updates.rs`
- Modify: `console/src-tauri/src/updates/cache.rs`

- [ ] **Step 1: 写 portable update policy 的失败测试**

在 `updates.rs` 增加纯策略函数，避免测试全局环境：

```rust
#[cfg(test)]
mod portable_policy_tests {
    use super::*;

    #[test]
    fn portable_build_never_uses_installer_updates() {
        assert!(!updates_allowed(true));
        assert!(updates_allowed(false));
    }
}
```

- [ ] **Step 2: 实现所有 updater 命令的同一入口守卫**

```rust
fn is_portable(app: &AppHandle) -> bool {
    app.state::<Option<crate::portable::PortableState>>().is_some()
}

fn updates_allowed(portable: bool) -> bool { !portable }
```

行为固定为：

- `check_desktop_update` / `check_cached_update`: portable 返回 `Ok(None)`；
- `install_desktop_update` / `download_desktop_update` / `install_downloaded_update`: portable 返回 `Err("desktop installer updates are disabled in portable mode")`；
- `supports_cached_updates` 接受 portable 参数或由 caller 先 guard，不能创建 `%LOCALAPPDATA%` cache；
- installed 模式原逻辑完全不变。

- [ ] **Step 3: 增加 Tauri single-instance plugin**

在 `Cargo.toml` 加：

```toml
tauri-plugin-single-instance = "2"
```

在 `lib.rs` 中将它注册为第一个 plugin。回调不启动 backend，只调用 `client::show_or_open(&app)`；installed 模式聚焦 main window，portable 浏览器模式重新打开当前 URL。

```rust
.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
    crate::client::show_or_open(app);
}))
```

- [ ] **Step 4: 更新锁文件并运行回归**

```powershell
cargo check --manifest-path console/src-tauri/Cargo.toml
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo test --manifest-path console/src-tauri/Cargo.toml
```

Expected: installed update tests不变，portable policy tests通过。

- [ ] **Step 5: 提交**

```powershell
git add console/src-tauri/Cargo.toml console/src-tauri/Cargo.lock console/src-tauri/src/lib.rs console/src-tauri/src/updates.rs console/src-tauri/src/updates/cache.rs
git commit -m "feat(portable): disable installer updates and enforce single instance"
```

## Task 5: 生成 portable 目录和 ZIP 发布物

**Files:**

- Create: `scripts/pack-tauri/stage_windows_portable.py`
- Create: `tests/unit/scripts/test_stage_windows_portable.py`
- Modify: `scripts/pack-tauri/build_win_pyinstaller.ps1`
- Create: `scripts/pack-tauri/README-PORTABLE.zh-CN.txt`

- [ ] **Step 1: 写 staging layout 的失败测试**

测试使用几字节假文件，不复制真实 runtime：

```python
def test_stage_portable_layout_and_manifest(tmp_path):
    target = tmp_path / "target" / "release"
    binaries = tmp_path / "binaries"
    target.mkdir(parents=True)
    (target / "qwenpaw-desktop.exe").write_bytes(b"MZ-test")
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "README.txt").write_text("portable\n", encoding="utf-8")
    for relative in (
        "qwenpaw-backend/qwenpaw-backend.exe",
        "python-runtime/python/python.exe",
        "node-runtime/node.exe",
    ):
        path = binaries / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime")

    output = stage_portable(
        version="2.0.1",
        exe=target / "qwenpaw-desktop.exe",
        binaries=binaries,
        dist=tmp_path / "dist",
        license_file=tmp_path / "LICENSE",
        readme_file=tmp_path / "README.txt",
    )

    root = output.stage_dir
    assert (root / "QwenPaw-Portable.exe").is_file()
    assert (root / "portable.json").read_text("utf-8") == (
        '{\n  "schemaVersion": 1,\n  "clientMode": "browser"\n}\n'
    )
    assert output.zip_path.name == "QwenPaw-Portable-2.0.1-Windows-x64.zip"
    assert output.sha256_path.read_text("ascii").endswith(
        "  QwenPaw-Portable-2.0.1-Windows-x64.zip\n"
    )
```

- [ ] **Step 2: 运行确认失败**

```powershell
uv run pytest tests/unit/scripts/test_stage_windows_portable.py -q
```

- [ ] **Step 3: 实现严格 staging script**

`stage_windows_portable.py` 必须：

1. 校验四个必需入口文件存在；
2. 新建版本化 stage 目录，拒绝把 `dist`、repo root 或空路径当删除目标；
3. 复制 raw Tauri exe 并改名；
4. `copytree` 三个 runtime 目录；
5. 写固定 schema 的 `portable.json`；
6. 复制 LICENSE/README；
7. 用 Zip64 创建 ZIP；
8. 流式计算 SHA-256 并写 `QwenPaw-Portable-2.0.1-Windows-x64.zip.sha256`；
9. 打印压缩前/后字节数，供发布记录真实体积。

主函数接口固定为：

```text
python scripts/pack-tauri/stage_windows_portable.py \
  --version 2.0.1 \
  --exe console/src-tauri/target/release/qwenpaw-desktop.exe \
  --binaries console/src-tauri/binaries \
  --dist dist
```

- [ ] **Step 4: 写中文快速说明**

`README-PORTABLE.zh-CN.txt` 必须包含：双击入口、10–120 秒首启等待、托盘 Quit 后再拔盘、默认浏览器策略、数据目录、API key/U 盘遗失风险、推荐 exFAT/NTFS、SmartScreen 说明、core 不含模型权重、日志位置和校验 SHA-256 的 PowerShell 命令。

- [ ] **Step 5: 在 Windows build 后追加 portable flavor build**

保留第一次标准 NSIS build，然后追加：

```powershell
Write-Host "== Step 4: Building portable flavor ==" -ForegroundColor Yellow
Set-Location console
npm exec -- tauri build --no-bundle `
  --config src-tauri/tauri.version.conf.json `
  --config src-tauri/tauri.portable.conf.json
if ($LASTEXITCODE -ne 0) { throw "Portable Tauri build failed" }
Set-Location $REPO_ROOT

python scripts/pack-tauri/stage_windows_portable.py `
  --version $VERSION `
  --exe console/src-tauri/target/release/qwenpaw-desktop.exe `
  --binaries console/src-tauri/binaries `
  --dist $DIST
if ($LASTEXITCODE -ne 0) { throw "Portable staging failed" }
```

标准 NSIS bundle 必须在第二次 raw build 之前已生成并保留。若 CLI 的多 `--config` 在锁定的 Tauri 版本行为不同，用一个构建时生成的合并 JSON 文件，不改全局 `tauri.conf.json`。

- [ ] **Step 6: 跑 staging tests 和静态检查**

```powershell
uv run pytest tests/unit/scripts/test_stage_windows_portable.py -q
uvx ruff check scripts/pack-tauri/stage_windows_portable.py tests/unit/scripts/test_stage_windows_portable.py
uvx black --check scripts/pack-tauri/stage_windows_portable.py tests/unit/scripts/test_stage_windows_portable.py
```

- [ ] **Step 7: 提交**

```powershell
git add scripts/pack-tauri/stage_windows_portable.py scripts/pack-tauri/build_win_pyinstaller.ps1 scripts/pack-tauri/README-PORTABLE.zh-CN.txt tests/unit/scripts/test_stage_windows_portable.py
git commit -m "build(portable): stage self-contained Windows USB archive"
```

## Task 6: 加入真实 Windows portable 验证和盘符移动测试

**Files:**

- Create: `scripts/verify/launch_tauri_windows_portable.ps1`
- Create: `.github/actions/verify-tauri-windows-portable/action.yml`
- Modify: `.github/workflows/desktop-build.yml:90-165`
- Modify: `scripts/verify/desktop_verify.py` only if a new `portable-browser` UI mode is required

- [ ] **Step 1: 编写 portable launcher verifier**

脚本必须创建隔离的测试根目录并解压 ZIP，而不是直接从 repo 启动。启动前快照：

```powershell
$profileData = Join-Path $env:USERPROFILE ".qwenpaw"
$localData = Join-Path $env:LOCALAPPDATA "io.agentscope.qwenpaw.desktop"
$profileExistedBefore = Test-Path $profileData
$localExistedBefore = Test-Path $localData
```

启动 `QwenPaw-Portable.exe` 后，从 `$portableRoot\data\desktop_port` 读取端口，轮询 `http://127.0.0.1:$port/api/healthz`，状态必须最终为 200。设置：

```powershell
$env:BASE_URL = "http://127.0.0.1:$port"
$env:PORTABLE_ROOT = $portableRoot
```

浏览器页面由现有 `desktop_verify.py` 的 standalone Chromium 驱动；不要要求 CDP 连接 WebView。

- [ ] **Step 2: 加便携性断言**

验证完成后断言：

```powershell
@(
  "data\config.json",
  "data\desktop_port",
  "data\desktop.log",
  "data\.portable-location.json",
  "logs\qwenpaw-desktop.log"
) | ForEach-Object {
  if (-not (Test-Path (Join-Path $portableRoot $_))) {
    throw "portable output missing: $_"
  }
}
if (-not $profileExistedBefore -and (Test-Path $profileData)) {
  throw "portable run wrote to $profileData"
}
if (-not $localExistedBefore -and (Test-Path $localData)) {
  throw "portable run wrote to $localData"
}
```

如果 verifier 配置了 API key，再断言 `secrets\.master_key` 存在；无 API key 的 smoke run 只要求 `secrets\` 目录存在。两种情况都不得把 `secrets\` 上传为 CI artifact。

注意：系统浏览器自己的 profile 不在这条断言范围。

- [ ] **Step 3: 测试路径/盘符移动**

首次退出后，把整个 portable 目录复制到包含空格和中文的第二个绝对路径，例如 `$env:RUNNER_TEMP\QwenPaw 移动盘\second`。保留 `data/.portable-location.json`，删除旧目录，再启动第二份。调用 `/api/agents` 或读 `data/config.json`，确认返回的 `workspace_dir` 指向新根目录；另外在 agent 的 `coding_mode.project_dir` 放一个旧根目录外的临时路径，确认保持原值。

在 Windows 上额外用 `subst P:` / `subst R:` 做两个盘符回合；若 GitHub hosted runner 不允许 `subst`，本地 U 盘测试矩阵补充该项，CI 仍保留两个不同绝对路径测试。

- [ ] **Step 4: 测试第二次双击和优雅退出**

记录第一个 backend PID，再启动第二次 exe：

- backend PID 不变；
- `desktop_port` 不变；
- 第一实例仍健康；
- 通过托盘或测试专用、带 shutdown token 的现有桌面命令退出后，shell/backend 在 60 秒内都不存在。

测试代码不得把 shutdown token 写入 artifact 日志。

- [ ] **Step 5: 建 composite action 并接入 workflow**

`verify-tauri-windows-portable/action.yml` 安装现有 verifier 依赖，调用 launcher，再用：

```powershell
python scripts/verify/desktop_verify.py `
  --base-url $env:BASE_URL `
  --ui-mode tauri-windows `
  --headed
```

在 `desktop-build.yml` 的 Windows job 中：

1. 标准安装版验证保持不变；
2. 新增 portable 验证；
3. always cleanup 同时杀 `QwenPaw-Portable` 和 `qwenpaw-backend`；
4. failure artifact 上传 portable 的 `logs/` 和 `data/desktop.log`；
5. 上传 ZIP 与 `.sha256`，artifact 名 `QwenPaw-Portable-Windows-${version}`。

- [ ] **Step 6: 在 Windows runner 跑完整 job**

```powershell
gh workflow run desktop-build.yml --ref codex/windows-usb-portable-v2.0.1
gh run watch --exit-status
```

Expected: 安装版和 portable 版两套验证均通过，ZIP artifact 可下载。

- [ ] **Step 7: 提交**

```powershell
git add scripts/verify/launch_tauri_windows_portable.ps1 .github/actions/verify-tauri-windows-portable/action.yml .github/workflows/desktop-build.yml scripts/verify/desktop_verify.py
git commit -m "test(portable): verify USB launch and drive relocation on Windows"
```

## Task 7: 文档、安全边界和发布口径

**Files:**

- Create: `website/public/docs/portable-windows.zh.md`
- Create: `website/public/docs/portable-windows.en.md`
- Modify: `website/public/docs/desktop.zh.md`
- Modify: `website/public/docs/desktop.en.md`
- Modify: `.github/workflows/desktop-publish.yml` only if portable artifact is approved for public release

- [ ] **Step 1: 写用户文档**

中英文页面明确写：

- Windows 10/11 x64；
- 下载 ZIP、整体解压到 U 盘、双击入口；
- 默认系统浏览器是产品设计，不是错误；
- 首次启动 10–120 秒；
- runtime/data 目录不可拆散；
- 退出/安全弹出流程；
- 盘符变化自动处理的范围；
- 浏览器和 Windows 仍可能有系统痕迹；
- secrets 同盘风险与 BitLocker To Go 建议；
- local model 体积与 U 盘性能建议；
- SmartScreen、SHA-256、签名状态；
- updater 在 portable 模式禁用，升级方式是退出后替换 runtime 文件并保留 `data/`、`secrets/`、`backups/`。

- [ ] **Step 2: 定义安全升级流程**

不能让用户把新 ZIP 直接覆盖正在运行的目录。第一版文档流程：

1. 托盘 Quit；
2. 备份旧 portable 根目录；
3. 解压新版本到新目录；
4. 复制 `data/`、`secrets/`、`backups/` 到新目录；
5. 首启验证后删除旧 runtime；
6. 不单独复制 `.master_key`，必须让整个 `secrets/` 一起移动。

- [ ] **Step 3: 仅在真实 artifact 验证后接发布 workflow**

公开发布名固定为：

```text
QwenPaw-Portable-2.0.1-Windows-x64.zip
QwenPaw-Portable-2.0.1-Windows-x64.zip.sha256
```

`desktop-publish.yml` 只发布，不把 portable ZIP加入现有 Tauri updater manifest；安装版 updater manifest 继续只指向 NSIS。

- [ ] **Step 4: 文档检查与提交**

```powershell
npm --prefix website ci
npm --prefix website run build
git diff --check
git add website/public/docs/portable-windows.zh.md website/public/docs/portable-windows.en.md website/public/docs/desktop.zh.md website/public/docs/desktop.en.md .github/workflows/desktop-publish.yml
git commit -m "docs(portable): document Windows USB distribution and risks"
```

如果尚未批准公开发布，不修改 `desktop-publish.yml`，也不要把它加入 commit。

## Task 8: 最终验证、占位符扫描和人工 U 盘矩阵

**Files:**

- Verify all modified files
- Create: `dist/QwenPaw-Portable-2.0.1-Windows-x64.zip` (build artifact, do not commit)
- Create: `dist/QwenPaw-Portable-2.0.1-Windows-x64.zip.sha256` (build artifact, do not commit)

- [ ] **Step 1: 跑 Python、Rust、前端的精确回归**

```powershell
uv run pytest tests/unit/test_portable.py tests/unit/tauri tests/unit/scripts/test_stage_windows_portable.py -q
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo clippy --manifest-path console/src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path console/src-tauri/Cargo.toml
npm --prefix console ci
npm --prefix console run format:check
npm --prefix console run test:run
```

Expected: 全部退出 0。

- [ ] **Step 2: 从零构建并校验 ZIP**

```powershell
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory dist | Out-Null
./scripts/pack-tauri/build_win_pyinstaller.ps1
Get-FileHash dist/QwenPaw-Portable-2.0.1-Windows-x64.zip -Algorithm SHA256
Get-Content dist/QwenPaw-Portable-2.0.1-Windows-x64.zip.sha256
```

Expected: 两个 SHA-256 完全相同；记录 ZIP 和解压后总大小，不在文档猜测体积。

- [ ] **Step 3: 扫描临时代码和危险路径**

```powershell
rg -n "TODO|FIXME|XXX|HACK|placeholder|not implemented" `
  src/qwenpaw/portable.py `
  console/src-tauri/src/portable.rs `
  console/src-tauri/src/client.rs `
  scripts/pack-tauri/stage_windows_portable.py `
  scripts/verify/launch_tauri_windows_portable.ps1

rg -n "%LOCALAPPDATA%|USERPROFILE.*\.qwenpaw|app_local_data_dir|LogDir" `
  console/src-tauri/src src/qwenpaw/tauri scripts/verify
```

Expected: 第一条无未处理占位；第二条只剩 installed-mode 分支和明确断言，portable 路径不能走这些分支。

- [ ] **Step 4: 审查路径和类型一致性**

人工确认：

- Rust `PortableState` 的数据、密钥、备份、日志、缓存目录与 Python/子进程环境映射一致；
- manifest 使用 `schemaVersion` / `clientMode`，Rust serde rename 与 staging script 一致；
- `project_dir` 只有位于历史 working root 下才改写；
- keyring 在 portable 模式明确禁用；
- portable update 从不创建 cached-update；
- browser URL 只绑定 `127.0.0.1`，不暴露到 LAN；
- readiness 以 `/api/healthz == 200` 为准，而不只看端口打开；
- 日志与错误消息不泄漏 secret、API key 或 shutdown token。

- [ ] **Step 5: 实体设备矩阵**

至少手工执行：

| 场景 | 文件系统 | 系统 | 期望 |
|---|---|---|---|
| U 盘首次启动 | exFAT | Windows 10 x64 | 浏览器自动打开，120 秒内健康 |
| U 盘首次启动 | NTFS | Windows 11 x64 | 浏览器自动打开；auto 模式可开内置窗口 |
| 盘符变更 | exFAT | Windows 11 x64 | agent/workspace 延续 |
| 无 WebView2/损坏 WebView2 | NTFS | Windows 10 x64 | browser 模式仍可用，auto 回退 |
| 非管理员标准账户 | NTFS | Windows 11 x64 | 无 UAC，核心启动；记录 sandbox 自动降级提示 |
| 慢速 USB 3 闪存 | exFAT | Windows 10 x64 | 不假死；首启时间写入测试记录 |
| 断网启动 | 任意 | Windows 11 x64 | 核心/本地 UI 启动；远程模型不可调用有清晰错误 |

不要做“运行中直接拔盘”的破坏性自动测试；用文档和退出流程覆盖。

- [ ] **Step 6: 最终 diff 自审**

```powershell
git status --short
git diff --check
git diff --stat v2.0.1...HEAD
git log --oneline --decorate v2.0.1..HEAD
```

确认没有提交 `dist/`、runtime 二进制、API key、测试日志、`.master_key` 或上层 GO Claw 文件。

## 后续里程碑（不阻塞第一版）

1. Authenticode EV/组织代码签名，降低 removable-drive SmartScreen 摩擦。
2. portable 原生差分更新器：下载 ZIP 到 U 盘、退出、原子替换 runtime，永不执行 NSIS。
3. 用户口令派生 master key，改善 U 盘遗失场景；注意这会改变“完全无交互双击”体验。
4. Windows ARM64 runtime/build/test 矩阵。
5. 针对 NTFS 的固定 WebView2 flavor；只有在体积、ACL、更新责任和安全补丁策略都明确后再提供。
6. U 盘写入耐久优化：减少日志、SQLite WAL 和小文件写放大，并给出性能等级提示。

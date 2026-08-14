# GO CLAW Customer Rebrand and Preset Digital Employees Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 QwenPaw 内部协议和便携路径机制兼容的前提下，把 Windows 便携产品的客户可见层统一为 GO CLAW、固定简体中文、精简顶栏，并在全新数据目录中幂等创建 5 名可编辑数字员工，最终产出可在任意 U 盘盘符和中文路径双击运行的完整 ZIP。

**Architecture:** 前端只保留 `zh` 运行时并通过现有语言 API 非阻塞同步后端；品牌资源直接进入 Vite/Tauri 构建输入；业务员工继续使用现有 `AgentProfileConfig`、技能池和插件工具。启动时以版本化 `presets-v1` 迁移替换上游 QA 员工的自动创建调用，先把随包媒体插件复制到用户插件目录，再通过分阶段工作区和原子标记创建缺失员工。Python 包名、CLI、API、环境变量、数据目录、sidecar、Tauri identifier 和 `window.QwenPaw` 全部保持不变。

**Tech Stack:** React 18、TypeScript 5.8、Vite 6、Vitest、Ant Design、i18next、Python 3.11、Pydantic、pytest、Tauri 2、Rust、PyInstaller、PowerShell、GitHub Actions、Playwright。

---

## 执行总则

- 工作目录固定为 `/Volumes/固态2/2026/0811 GO Claw 2.0/upstream/worktrees/GO-Claw-customer-rebrand`，分支固定为 `codex/go-claw-customer-rebrand`。
- 每个任务必须按“先写失败测试 → 运行并确认失败原因 → 最小实现 → 运行通过 → 提交”的顺序执行；不得把多个任务压成一个大提交。
- 客户品牌只使用 `GO CLAW`；文件系统安全名只使用 `GO-CLAW`。
- 内部兼容字面值 `qwenpaw`、`QWENPAW_*`、`.qwenpaw`、`qwenpaw-backend.exe`、`qwenpaw-desktop`、`window.QwenPaw`、`X-QwenPaw-Desktop-Shutdown-Token`、Tauri identifier 均不得重命名。
- 固定员工顺序为 `default`、`marketing-growth`、`content-production`、`data-processing`、`business-analysis`；全新目录不得再自动创建上游 `default_qa_agent`，否则 UI 会出现第 6 名员工。
- 旧数据中的额外员工（包括已存在的 QA 员工）保留，不删除、不改名、不调模型；“当前数字员工（5）”是全新数据目录的确定性验收结果。
- 所有二进制品牌资源只从已确认目录复制，并在复制后核对 SHA-256；不得重新绘制、从小尺寸放大或使用旧图作为回退。
- 每完成一个任务都运行 `git diff --check`；任何构建、测试或资源缺失失败都不得进入下一任务。

## 规格覆盖映射

| 已批准要求 | 唯一落地任务 | 最终证据 |
| --- | --- | --- |
| GO CLAW Logo、标题、头像、窗口、安装器和图标 | Task 1、3、4、8 | 资源摘要合同、Header 测试、Rust 测试、Windows 截图 |
| 固定中文并同步后端 | Task 2 | i18n/同步单测、HTML lang、Windows UI 断言 |
| 删除文档、GitHub、语言入口 | Task 3 | Header 桌面/移动测试、Playwright 禁止项 |
| 客户术语统一为数字员工 | Task 4 | `zh.json` 静态扫描、员工选择器测试 |
| 五名员工、固定顺序、可编辑生命周期 | Task 5、7 | 定义测试、迁移矩阵、真实 `/api/agents` 验证 |
| Qwen-Image/Wan 2.7 随包、内容生产启用、无 Key | Task 5、6、11 | plugin/config 单测、冻结依赖、产物无密钥检查 |
| `presets-v1` 只执行一次、失败重试、删除不重建 | Task 7 | marker/部分失败/重启测试 |
| U 盘盘符自适配、中文路径、单实例 | Task 9、11、12 | 双 subst 盘符、PID/port、路径重绑 CI |
| 完整 ZIP 与 SHA-256 | Task 9、10、12 | GitHub Actions artifact、checksum 验证 |

## Task 1：建立品牌资源单一来源和静态合同

**Files:**

- Create: `console/public/go-claw-horizontal.svg`
- Create: `console/public/go-claw-horizontal-white.svg`
- Create: `console/public/go-claw-mark.svg`
- Create: `console/public/go-claw-favicon-64.png`
- Create: `scripts/pack/assets/go-claw-app-icon-1024.png`
- Create: `tests/unit/branding/test_go_claw_customer_contract.py`
- Delete after all references are migrated: `console/public/logo-dark.svg`
- Delete after all references are migrated: `console/public/logo-light.svg`
- Delete after all references are migrated: `console/public/online.svg`
- Delete after all references are migrated: `console/public/qwenpaw.png`
- Delete after all references are migrated: `console/public/qwenpawBack.png`
- Delete after icon generation is repointed: `scripts/pack/assets/icon.svg`
- Delete after icon generation is repointed: `scripts/pack/assets/icon.ico`
- Delete after icon generation is repointed: `scripts/pack/assets/icon.icns`

- [ ] **Step 1: 先写失败的资源合同测试。**

  在 `test_go_claw_customer_contract.py` 中定义仓库根目录、目标资源和固定摘要：

  ```python
  ASSET_SHA256 = {
      "console/public/go-claw-horizontal.svg":
          "9a947dfcecd81e50f1332c090429660350e10754c418a93bcb4a0091a530f831",
      "console/public/go-claw-horizontal-white.svg":
          "76c14d9fca5cb6d8f641005e584bb06cf6dec5ecf8fea4bdc4df95abeb9b552e",
      "console/public/go-claw-mark.svg":
          "fd98f1f953e8c989ac5878fe173dc2dec276bab0f8e52eff93ca90fe4f34d658",
      "console/public/go-claw-favicon-64.png":
          "d6253ebb4472c5c66fabfd560aa342569af060f11d974284e81887153472441f",
      "scripts/pack/assets/go-claw-app-icon-1024.png":
          "5d4c3032d2f0a538ff391f2e7a501e4c2681b278906f0db2e294b334da1781ae",
  }
  ```

  测试逐个断言文件存在且摘要完全一致；此时应因文件尚不存在而失败。

- [ ] **Step 2: 运行失败测试。**

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Expected: FAIL，首个错误为 `go-claw-horizontal.svg` 不存在，而不是测试导入或语法错误。

- [ ] **Step 3: 从确认目录机械复制资源。**

  复制映射必须严格为：

  ```text
  go-claw-v3-horizontal.svg                 -> console/public/go-claw-horizontal.svg
  go-claw-v3-horizontal-white.svg           -> console/public/go-claw-horizontal-white.svg
  go-claw-v3-mark.svg                       -> console/public/go-claw-mark.svg
  png/go-claw-v3-favicon-64.png             -> console/public/go-claw-favicon-64.png
  png/go-claw-v3-app-icon-1024.png           -> scripts/pack/assets/go-claw-app-icon-1024.png
  ```

  源目录固定为 `/Users/gresonkwan/Documents/PPT大师/GO_CLAW_LOGO_V3_HYBRID_副本`。二进制 PNG 使用机械复制，SVG 不改路径数据、颜色或 viewBox。

- [ ] **Step 4: 运行资源合同。**

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Expected: PASS。

- [ ] **Step 5: 提交。**

  ```bash
  git add console/public/go-claw-* scripts/pack/assets/go-claw-app-icon-1024.png tests/unit/branding/test_go_claw_customer_contract.py
  git commit -m "feat(brand): add verified GO CLAW assets"
  ```

## Task 2：把前端运行时锁定为简体中文

**Files:**

- Modify: `console/src/i18n.ts`
- Create: `console/src/i18n.test.ts`
- Create: `console/src/utils/fixedChineseLanguage.ts`
- Create: `console/src/utils/fixedChineseLanguage.test.ts`
- Modify: `console/src/App.tsx`
- Modify: `console/index.html`

- [ ] **Step 1: 写 i18n 失败测试。**

  `i18n.test.ts` 在动态导入前设置 `localStorage.language = "en"` 并把 `navigator.language` 模拟为 `en-US`，然后断言：

  ```ts
  expect(i18n.language).toBe("zh");
  expect(i18n.options.fallbackLng).toEqual(["zh"]);
  expect(i18n.options.supportedLngs).toContain("zh");
  expect(i18n.options.supportedLngs).not.toContain("en");
  ```

  每个用例前执行 `vi.resetModules()` 和 `localStorage.clear()`，防止单例缓存污染。

- [ ] **Step 2: 写后端同步失败测试。**

  `fixedChineseLanguage.test.ts` 覆盖三个行为：删除旧语言缓存、调用 `changeLanguage("zh")`、调用 `updateLanguage("zh")`；当后端 Promise reject 时，函数 resolve 且调用错误记录器，不把异常抛到 React。

  目标函数签名固定为：

  ```ts
  export async function synchronizeFixedChineseLanguage(
    languageEngine: Pick<i18n, "language" | "changeLanguage">,
    updateLanguage: (language: string) => Promise<unknown> =
      languageApi.updateLanguage,
    reportError: (message: string, error: unknown) => void = console.error,
  ): Promise<void>
  ```

- [ ] **Step 3: 运行并确认旧行为失败。**

  Run: `cd console && npm run test:run -- src/i18n.test.ts src/utils/fixedChineseLanguage.test.ts`

  Expected: FAIL；旧实现解析为 `en`，且同步函数尚不存在。

- [ ] **Step 4: 最小实现固定中文。**

  `i18n.ts` 只导入 `zh.json`，只注册：

  ```ts
  const resources = { zh: { translation: zh } };
  i18n.use(initReactI18next).init({
    resources,
    lng: "zh",
    fallbackLng: "zh",
    supportedLngs: ["zh"],
    nonExplicitSupportedLngs: false,
    interpolation: { escapeValue: false },
  });
  ```

  `synchronizeFixedChineseLanguage` 先 `localStorage.removeItem("language")`，必要时切换到 `zh`，再尝试保存后端；两段均不得阻塞页面渲染。

- [ ] **Step 5: 简化 `App.tsx`。**

  删除英文、日文、俄文和印尼文 Ant Design/dayjs import、locale map 和 `languageChanged` 监听；固定：

  ```ts
  const antdLocale = zhCN;
  dayjs.locale("zh-cn");
  useEffect(() => {
    void synchronizeFixedChineseLanguage(i18n);
    void useUploadLimitStore.getState().fetch();
  }, [i18n]);
  ```

  `ConfigProvider` 的 `prefix="qwenpaw"` 和 `prefixCls="qwenpaw"` 是 CSS/插件兼容标识，必须保留。

- [ ] **Step 6: 固定 HTML；语言组件延后到 Header 任务删除。**

  把 `console/index.html` 改为 `<html lang="zh-CN">`。本任务暂时保留 LanguageSwitcher 源文件，避免 Header import 在 Task 3 开始前破坏类型检查；运行时 i18n 已只有 `zh`，Task 3 会同时删除 Header 引用和组件文件。

- [ ] **Step 7: 运行测试和类型检查。**

  Run: `cd console && npm run test:run -- src/i18n.test.ts src/utils/fixedChineseLanguage.test.ts`

  Run: `cd console && npx tsc -b --noEmit`

  Expected: PASS。

- [ ] **Step 8: 提交。**

  ```bash
  git add console/src/i18n.ts console/src/i18n.test.ts console/src/utils/fixedChineseLanguage.ts console/src/utils/fixedChineseLanguage.test.ts console/src/App.tsx console/index.html
  git commit -m "feat(i18n): lock GO CLAW console to Chinese"
  ```

## Task 3：精简顶栏并接入 24px GO CLAW Logo

**Files:**

- Modify: `console/src/layouts/Header.tsx`
- Modify: `console/src/layouts/index.module.less`
- Modify: `console/src/layouts/constants.ts`
- Modify: `console/src/layouts/constants.test.ts`
- Create: `console/src/layouts/Header.customer.test.tsx`
- Delete: `console/src/components/LanguageSwitcher/index.tsx`
- Delete: `console/src/components/LanguageSwitcher/index.module.less`
- Delete: `console/src/components/LanguageSwitcher/LanguageSwitcher.test.tsx`

- [ ] **Step 1: 写 Header 客户行为失败测试。**

  使用现有 `renderWithProviders`，mock `api.getVersion`、桌面更新上下文、Tauri `invoke` 和插件 Slot。断言：

  ```ts
  expect(screen.getByAltText("GO CLAW")).toHaveAttribute(
    "src", "/go-claw-horizontal.svg",
  );
  expect(screen.queryByText("文档资料")).not.toBeInTheDocument();
  expect(screen.queryByText("GitHub")).not.toBeInTheDocument();
  expect(screen.queryByTitle("语言")).not.toBeInTheDocument();
  expect(screen.queryByTitle("文档资料")).not.toBeInTheDocument();
  ```

  再切换深色主题，断言 Logo 为 `/go-claw-horizontal-white.svg`。Logo 元素增加 `data-testid="go-claw-header-logo"`，便于 Windows E2E 使用。

- [ ] **Step 2: 运行失败测试。**

  Run: `cd console && npm run test:run -- src/layouts/Header.customer.test.tsx src/layouts/constants.test.ts`

  Expected: FAIL；页面仍出现旧 Logo、资源、GitHub 或语言入口。

- [ ] **Step 3: 删除桌面和移动资源菜单。**

  从 `Header.tsx` 删除 `LanguageSwitcher`、`LANGUAGE_LIST`、`MenuProps`、`resourcesMenuItems`、`mobileMenuItems`、资源/GitHub图标和 Dropdown；随后删除三个 LanguageSwitcher 文件。保留 `Slot("header.left")`、`Slot("header.right")`、CodingMode、主题、版本和更新状态。

  主题按钮不再包在 `hideOnMobile` 中，使移动端仍有主题入口；删除只承载资源菜单的移动端 `InfoCircleOutlined` 按钮。

- [ ] **Step 4: 取消更新弹窗对旧品牌文档正文的抓取。**

  删除 `faq.*.md` fetch、`QwenPaw如何更新` 正则和语言分支；web fallback 直接使用本地中文 `UPDATE_MD`。`getReleaseNotesUrl()` 仅保留给“查看更新详情”按钮，不能重新出现在顶栏。

- [ ] **Step 5: 替换 Logo 和尺寸。**

  ```tsx
  <img
    data-testid="go-claw-header-logo"
    src={isDark
      ? "/go-claw-horizontal-white.svg"
      : "/go-claw-horizontal.svg"}
    alt="GO CLAW"
    className={styles.logoImg}
  />
  ```

  `.logoImg` 固定 `height: 24px; width: auto; display: block;`。保留 `logoWrapper` 的 8 次点击 DevTools 手势和版本号相邻布局。

- [ ] **Step 6: 收敛本地更新文案。**

  `UPDATE_MD` 改为单一中文字符串，产品名为 GO CLAW；真实命令 `pip install -U qwenpaw`、`uv tool upgrade qwenpaw` 可保留。删除 `GITHUB_URL/getDocsUrl/getFeatureDemosUrl/getFaqUrl` 的 Header import；若常量已无其他消费者，则同步删除对应 export 和旧测试。

- [ ] **Step 7: 运行测试和类型检查。**

  Run: `cd console && npm run test:run -- src/layouts/Header.customer.test.tsx src/layouts/constants.test.ts`

  Run: `cd console && npx tsc -b --noEmit`

  Run: `rg -n "LanguageSwitcher|LANGUAGE_LIST|resourcesMenuItems|mobileMenuItems" console/src`

  Expected: 测试通过，`rg` 无输出。

- [ ] **Step 8: 提交。**

  ```bash
  git add console/src/layouts console/src/components/LanguageSwitcher
  git commit -m "feat(header): simplify GO CLAW customer navigation"
  ```

## Task 4：完成前端客户品牌和“数字员工”术语替换

**Files:**

- Modify: `console/index.html`
- Modify: `console/src/pages/Login/index.tsx`
- Modify: `console/src/tauri/BackendLoadingPage.tsx`
- Modify: `console/src/pages/Chat/index.tsx`
- Modify: `console/src/pages/Chat/OptionsPanel/defaultConfig.ts`
- Modify: `console/src/pages/Settings/Market/components/SkillIcon.tsx`
- Modify: `console/src/pages/Settings/PluginManager/components/MarketPluginList.tsx`
- Modify: `console/src/pages/Agent/Config/components/AgentLoopCard.tsx`
- Modify: `console/src/layouts/index.module.less`
- Modify: `console/src/locales/zh.json`
- Modify: `console/src/components/AgentSelector/AgentSelector.test.tsx`
- Modify: `console/src/utils/agentDisplayName.ts`
- Modify: `tests/unit/branding/test_go_claw_customer_contract.py`

- [ ] **Step 1: 扩展静态失败合同。**

  合同只扫描客户可见文件，不扫描 `window.QwenPaw` SDK、Python 包名或技术注释。断言：

  ```python
  assert "QwenPaw" not in customer_text
  assert "智能体" not in zh_locale_text
  assert re.search(r"(?<![A-Za-z])Agent(?![A-Za-z])", zh_locale_text) is None
  ```

  扫描集必须包含本任务列出的 TSX/JSON/HTML、两个媒体插件 `plugin.json`、Tauri 客户配置、便携 README 和 staging 脚本；内部兼容文件不做全仓盲扫。

- [ ] **Step 2: 扩展员工选择器失败测试。**

  把 mock 数据改为 5 名已启用员工并按固定 ID 排序，翻译 mock 对 `agent.currentWorkspace` 返回“当前数字员工”。断言页面出现 `当前数字员工 (5)`，打开下拉后依次出现“通用数字员工、营销获客、内容生产、数据处理、商业分析”。

- [ ] **Step 3: 运行失败测试。**

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Run: `cd console && npm run test:run -- src/components/AgentSelector/AgentSelector.test.tsx`

  Expected: FAIL，列出旧品牌和旧术语。

- [ ] **Step 4: 替换主要品牌位。**

  - `index.html`: favicon 指向 `/go-claw-favicon-64.png`，title 为 `GO CLAW`。
  - Login: 浅色/深色横版 Logo，alt 为 GO CLAW。
  - BackendLoadingPage: 使用 `/go-claw-mark.svg`，alt 为 GO CLAW，主色改为 `#FF4A18`。
  - Chat: 默认 nick 为 `GO CLAW`，默认 avatar 为 `/go-claw-mark.svg`。
  - Chat Options: “Work with GO CLAW”，头像使用 mark。
  - SkillIcon: 内部 provider key `qwenpaw` 保留，显示 label 改为 `GO CLAW`。
  - PluginManager 和 AgentLoopCard 的硬编码 fallback 文案改为 GO CLAW。
  - 更新弹窗背景改用 GO CLAW mark 或纯色，不再引用 `qwenpawBack.png`。

- [ ] **Step 5: 全面修改 `zh.json`。**

  使用以下唯一映射，不改 JSON key：

  | 旧客户文案 | 新客户文案 |
  | --- | --- |
  | QwenPaw | GO CLAW |
  | 默认智能体 | 通用数字员工 |
  | 当前智能体 | 当前数字员工 |
  | 智能体 | 数字员工 |
  | 子智能体 | 子数字员工 |
  | 多智能体 | 多数字员工 |
  | Agent（客户标签） | 数字员工 |
  | ACP Agent | ACP 数字员工 |

  `agent.json`、`agent ID`、`~/.qwenpaw`、`qwenpaw` CLI、Qwen-Image 模型名属于真实技术名，保持原拼写。更新、登录、重启、沙箱、插件兼容、编程模式、记忆和 Loop 文案中的产品主体全部改为 GO CLAW。

- [ ] **Step 6: 维护默认员工显示兼容。**

  `DEFAULT_AGENT_DISPLAY_NAME = "Default Agent"` 保留作为识别上游默认名的内部哨兵；`agent.defaultDisplayName` 已变成“通用数字员工”。这样旧配置还没跑迁移时也不会在 UI 显示英文默认名。

- [ ] **Step 7: 运行 JSON、静态合同和前端测试。**

  Run: `python -m json.tool console/src/locales/zh.json >/dev/null`

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Run: `cd console && npm run test:run -- src/components/AgentSelector/AgentSelector.test.tsx`

  Run: `cd console && npx tsc -b --noEmit`

  Expected: PASS。

- [ ] **Step 8: 确认旧资源无引用后删除。**

  Run: `rg -n "logo-dark|logo-light|online\.svg|qwenpaw\.png|qwenpawBack" console/src console/index.html`

  Expected: 无输出；随后删除 Task 1 列出的旧前端资源。

- [ ] **Step 9: 提交。**

  ```bash
  git add console tests/unit/branding
  git commit -m "feat(ui): complete GO CLAW customer copy"
  ```

## Task 5：定义 4 名专业数字员工的能力和中文提示词

**Files:**

- Create: `src/qwenpaw/agents/go_claw_presets.py`
- Create: `src/qwenpaw/agents/md_files/go-claw-marketing-growth/zh/AGENTS.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-marketing-growth/zh/SOUL.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-marketing-growth/zh/PROFILE.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-content-production/zh/SOUL.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-content-production/zh/PROFILE.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-data-processing/zh/AGENTS.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-data-processing/zh/SOUL.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-data-processing/zh/PROFILE.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-business-analysis/zh/AGENTS.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-business-analysis/zh/SOUL.md`
- Create: `src/qwenpaw/agents/md_files/go-claw-business-analysis/zh/PROFILE.md`
- Create: `tests/unit/agents/test_go_claw_presets.py`

- [ ] **Step 1: 写定义失败测试。**

  测试导入 `PRESET_ORDER`、`SPECIALIST_PRESETS`、`build_preset_agent_config`，断言 ID/名称/技能/模板目录完全为：

  ```python
  PRESET_ORDER = (
      "default",
      "marketing-growth",
      "content-production",
      "data-processing",
      "business-analysis",
  )
  ```

  ```python
  EXPECTED_SKILLS = {
      "marketing-growth": (
          "browser_visible", "file_reader", "docx", "pptx", "xlsx",
      ),
      "content-production": (
          "file_reader", "docx", "pptx", "pdf",
      ),
      "data-processing": ("file_reader", "xlsx", "pdf"),
      "business-analysis": (
          "browser_visible", "file_reader", "xlsx", "docx", "pptx", "pdf",
      ),
  }
  ```

  内容生产配置必须显式启用 `generate_image_qwen`、`edit_image_qwen`、`text_to_video_wan`、`image_to_video_wan`、`reference_to_video_wan`，每个 `BuiltinToolConfig.config == {}` 且序列化结果不含 `api_key`。

- [ ] **Step 2: 运行失败测试。**

  Run: `python -m pytest tests/unit/agents/test_go_claw_presets.py -q`

  Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 实现不可变预置定义。**

  使用 frozen dataclass：

  ```python
  @dataclass(frozen=True)
  class DigitalEmployeePreset:
      id: str
      name: str
      description: str
      skill_names: tuple[str, ...]
      md_template_id: str
      required_builtin_tools: tuple[str, ...]
      plugin_tools: tuple[str, ...] = ()
  ```

  `build_preset_agent_config` 构造普通 `AgentProfileConfig`，固定 `language="zh"`，使用现有 `ChannelConfig/MCPConfig/HeartbeatConfig/ToolsConfig`。先保留 ToolsConfig 默认值，再确保角色所需 built-in tool 为 enabled；插件工具用 `BuiltinToolConfig` 显式创建、enabled、空 config。不得创建新 Agent 类型或新 API 字段。

- [ ] **Step 4: 写入确定性角色提示词。**

  每个模板都包含 `AGENTS.md`、`SOUL.md`、`PROFILE.md`，不含 `BOOTSTRAP.md`，避免首次聊天重新询问身份。内容必须覆盖：

  - 营销获客：先确认产品、客群、地域、预算、周期；需要时检索最新信息并附来源；输出客户画像、渠道优先级、活动节奏、转化漏斗、线索表和可直接使用的营销文案；不得伪造客户或数据。
  - 内容生产：可完成选题、文章、社媒文案、图片提示词、视频脚本、分镜；只有配置 DashScope API Key 后才调用 Qwen-Image/Wan 2.7；无 Key 时继续完成文字方案并明确给出配置路径，绝不声称已生成媒体。
  - 数据处理：处理前保留原始文件，先说明字段和质量问题；记录清洗、合并、公式、统计和图表步骤；输出文件与处理日志可追溯；不得静默覆盖源数据或臆造缺失值。
  - 商业分析：先定义问题、口径和时间范围；使用网页与表格资料时给出处；结论分为“事实、假设、推断”；输出行业/竞品/经营指标、机会、风险和行动建议，不把假设包装成事实。

  `PROFILE.md` 写固定中文名称和交付物；`SOUL.md` 写角色性格与边界；`AGENTS.md` 写执行流程和工具使用规则。

- [ ] **Step 5: 运行定义和模板测试。**

  Run: `python -m pytest tests/unit/agents/test_go_claw_presets.py -q`

  Expected: PASS；并确认 12 个模板文件均为 UTF-8、无 `QwenPaw`、无密钥格式。

- [ ] **Step 6: 提交。**

  ```bash
  git add src/qwenpaw/agents/go_claw_presets.py src/qwenpaw/agents/md_files/go-claw-* tests/unit/agents/test_go_claw_presets.py
  git commit -m "feat(agents): define GO CLAW digital employees"
  ```

## Task 6：把 Qwen-Image 和 Wan 2.7 作为无密钥内置插件随包交付

**Files:**

- Create: `src/qwenpaw/app/go_claw_bundled_plugins.py`
- Create: `tests/unit/app/test_go_claw_bundled_plugins.py`
- Modify: `plugins/tool/qwen-image/plugin.json`
- Modify: `plugins/tool/qwen-image/qwen_image_tool.py`
- Modify: `plugins/tool/wan27/plugin.json`
- Modify: `plugins/tool/wan27/wan27_tool.py`
- Modify: `scripts/pack-tauri/qwenpaw.spec`
- Modify: `scripts/pack-tauri/build_pyinstaller.ps1`
- Modify: `scripts/pack-tauri/build_pyinstaller.sh`
- Modify: `tests/unit/branding/test_go_claw_customer_contract.py`

- [ ] **Step 1: 写插件复制失败测试。**

  用临时目录构造包含两个 manifest 的 bundled root，断言 `ensure_bundled_media_plugins()`：

  - 按 manifest ID 识别 `qwen-image-tool` 和 `wan27-tool`；
  - 只在目标 ID 不存在时复制；
  - 先复制到同级 `.go-claw-plugin.tmp` 再 `Path.replace()`；
  - 已有同 ID 插件无论目录名是什么都保留；
  - 规范目标目录存在但 manifest 是另一个 ID 时抛出明确冲突错误；
  - 返回两个已安装 manifest 路径，供迁移完成条件检查。

- [ ] **Step 2: 运行失败测试。**

  Run: `python -m pytest tests/unit/app/test_go_claw_bundled_plugins.py -q`

  Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现源目录解析和原子复制。**

  唯一查找顺序：

  ```python
  frozen_root = Path(__file__).resolve().parents[1] / "bundled_plugins"
  source_root = Path(__file__).resolve().parents[3] / "plugins" / "tool"
  ```

  冻结目录存在时优先使用；源码运行时使用仓库 `plugins/tool`。目标使用现有 `get_plugins_dir()`，不得改变 `PLUGINS_DIR` 或插件 loader。复制前忽略 `._*`、`__pycache__` 和 `.DS_Store`。

- [ ] **Step 4: 把插件树和依赖冻结进 PyInstaller。**

  `qwenpaw.spec` 增加：

  ```python
  datas += collect_tree(
      REPO_ROOT / "plugins" / "tool" / "qwen-image",
      "qwenpaw/bundled_plugins/qwen-image",
  )
  datas += collect_tree(
      REPO_ROOT / "plugins" / "tool" / "wan27",
      "qwenpaw/bundled_plugins/wan27",
  )
  datas += collect_data_files("dashscope")
  ```

  并在现有 `Analysis(..., hiddenimports=[...])` 列表中加入 `*collect_submodules("dashscope")`，不创建一个与当前 spec 结构不匹配的临时 `hiddenimports` 变量。

  同时把 `dashscope` 加入 `_metadata_pkgs`，让插件 loader 能验证 `>=1.25.16`；扩展 `collect_tree()` 过滤 `._*`、`.DS_Store`、`__pycache__`，防止 macOS AppleDouble 文件进入 ZIP。

  在 Windows 和 macOS PyInstaller 构建脚本安装 `dashscope>=1.25.16`，并在冻结前执行 `import dashscope` 检查。`httpx` 已是核心依赖，不重复增加。这样首次 U 盘启动不会为了媒体插件临时联网 pip install。

- [ ] **Step 5: 本地化插件客户元数据和缺 Key 错误。**

  manifest 中作者改为 `GO CLAW Team`，名称、描述、配置 label/help/hint 改为中文；`Qwen-Image`、`Wan 2.7`、`DashScope` 是模型/服务名，保持原名。工具代码在未配置时返回中文可执行提示：“请在当前数字员工的工具配置中填写 DashScope API Key”；保留 error state，禁止空 Key 发请求。

- [ ] **Step 6: 运行测试和 manifest 校验。**

  Run: `python -m pytest tests/unit/app/test_go_claw_bundled_plugins.py tests/unit/branding/test_go_claw_customer_contract.py -q`

  Run: `python -m json.tool plugins/tool/qwen-image/plugin.json >/dev/null && python -m json.tool plugins/tool/wan27/plugin.json >/dev/null`

  Expected: PASS。

- [ ] **Step 7: 提交。**

  ```bash
  git add src/qwenpaw/app/go_claw_bundled_plugins.py tests/unit/app/test_go_claw_bundled_plugins.py plugins/tool/qwen-image plugins/tool/wan27 scripts/pack-tauri/qwenpaw.spec scripts/pack-tauri/build_pyinstaller.ps1 scripts/pack-tauri/build_pyinstaller.sh tests/unit/branding/test_go_claw_customer_contract.py
  git commit -m "feat(plugins): bundle GO CLAW media tools"
  ```

## Task 7：实现 `presets-v1` 原子迁移并接入启动链

**Files:**

- Create: `src/qwenpaw/app/go_claw_presets.py`
- Create: `tests/unit/app/test_go_claw_presets.py`
- Modify: `src/qwenpaw/app/_app.py`

- [ ] **Step 1: 写迁移矩阵失败测试。**

  测试至少覆盖 8 个场景：

  1. 空数据目录得到 5 个固定 ID、default active、4 个 specialist enabled+pinned、固定顺序。
  2. default 名为 `Default Agent` 时改成“通用数字员工”。
  3. default 已自定义名称时保持不变。
  4. 同 ID specialist 已存在时不改工作区、agent.json、模型、技能或工具。
  5. 第一次成功后删除 specialist，再启动因 marker 存在而不重建。
  6. 创建第 3 个 specialist 失败时不写 marker；重试只补缺失项。
  7. marker 通过临时文件和 `replace()` 写入，包含 `version == "presets-v1"` 和 UTC `completedAt`。
  8. 插件安装失败时不写 marker、不启动半配置媒体员工。
  9. 四个 specialist ID 不进入任何 protected-ID 列表；通过现有 router 能更新、停用、取消置顶和删除，只有 `default` 继续受保护。

- [ ] **Step 2: 运行失败测试。**

  Run: `python -m pytest tests/unit/app/test_go_claw_presets.py -q`

  Expected: FAIL，迁移模块不存在。

- [ ] **Step 3: 实现安全入口和 marker。**

  ```python
  PRESET_VERSION = "presets-v1"
  MARKER_RELATIVE_PATH = Path(".migrations/go-claw-presets-v1.json")

  def ensure_go_claw_presets() -> bool:
      try:
          return _ensure_go_claw_presets()
      except Exception:
          logger.error("GO CLAW presets-v1 initialization failed", exc_info=True)
          return False
  ```

  marker 已存在且 JSON version 正确时立即返回；损坏/版本不符视为未完成并安全重试。写 marker 前创建父目录，写 `.tmp`，flush 后 `replace()`。

- [ ] **Step 4: 实现 specialist 分阶段工作区。**

  对缺失 ID 使用同卷临时目录 `.marketing-growth.go-claw-presets-v1.tmp`：初始化 sessions/memory/skills、下载技能、复制角色模板、写 agent.json（其中 workspace_dir 指向最终目录），再原子 rename 到 `workspaces/<id>`，对最终目录运行 `reconcile_workspace_manifest()` 修正 staged path 派生的 workspace identity，最后把 `AgentProfileRef(enabled=True, pinned=True)` 写入 root config。

  崩溃恢复规则固定为：

  - 只有临时目录：下次删掉这个精确临时目录并重建；
  - 已有规范目录且 agent.json 的 ID 正确、root ref 缺失：只补 root ref；
  - 规范目录 agent.json 属于其他 ID：停止并记录冲突，不覆盖；
  - root ref 已存在：视为用户所有，完全保留。

- [ ] **Step 5: 处理 default 和顺序。**

  只在 default agent.json 名称严格等于 `Default Agent` 时改名。最终顺序：先放 `PRESET_ORDER` 中实际存在的 ID，再按原 `agent_order` 和 profiles 插入顺序附加所有旧员工，避免丢失用户排序。

- [ ] **Step 6: 把插件存在作为迁移完成条件。**

  在创建员工前调用 `ensure_bundled_media_plugins()`；只有两个插件 ID 均可从目标目录解析、4 个 specialist profile 和 agent.json 均存在、root config 已保存时才写 marker。预置文件和 marker 中不得出现 `api_key`、`sk-` 或环境密钥值。

- [ ] **Step 7: 修改启动链并避免第 6 名员工。**

  `_app.py` 的同步迁移顺序固定为：

  ```python
  migrate_legacy_workspace_to_default_agent()
  ensure_default_agent_exists()
  migrate_legacy_skills_to_skill_pool()
  ensure_go_claw_presets()
  ```

  删除 lifespan 对 `ensure_qa_agent_exists()` 的自动调用和 import，但保留 `migration.py` 中 QA 函数、常量和测试，保证旧数据/内部 API 兼容。不得删除旧用户已经存在的 QA 员工。

- [ ] **Step 8: 运行迁移、排序和启动测试。**

  Run: `python -m pytest tests/unit/app/test_go_claw_presets.py tests/unit/app/test_agents_ordering.py tests/unit/app/test_agents_workspace_initialization.py -q`

  Expected: PASS。

- [ ] **Step 9: 提交。**

  ```bash
  git add src/qwenpaw/app/go_claw_presets.py src/qwenpaw/app/_app.py tests/unit/app/test_go_claw_presets.py
  git commit -m "feat(startup): provision GO CLAW preset employees"
  ```

## Task 8：换牌 Tauri 窗口、安装器、托盘、快捷方式和图标

**Files:**

- Modify: `console/src-tauri/tauri.conf.json`
- Modify: `console/src-tauri/tauri.portable.conf.json`
- Modify: `console/src-tauri/Cargo.toml`
- Modify: `console/src-tauri/src/client.rs`
- Modify: `console/src-tauri/src/tray.rs`
- Modify: `console/src-tauri/src/portable.rs`
- Modify: `console/src-tauri/src/lib.rs`
- Modify: `console/src-tauri/nsis-hooks.nsh`
- Modify: `console/src-tauri/nsis-languages/English.nsh`
- Modify: `console/src-tauri/nsis-languages/SimpChinese.nsh`
- Modify: `console/src-tauri/nsis-languages/Indonesian.nsh`
- Modify: `console/src-tauri/nsis-languages/Japanese.nsh`
- Modify: `console/src-tauri/nsis-languages/Russian.nsh`
- Modify: `console/src-tauri/nsis-languages/PortugueseBR.nsh`
- Modify: `console/src-tauri/nsis/qwenpaw-desktop-debug.cmd`
- Modify: `console/src-tauri/nsis/qwenpaw-desktop-debug.ps1`
- Modify: `scripts/pack-tauri/build_win_pyinstaller.ps1`
- Modify: `scripts/pack-tauri/build_macos_pyinstaller.sh`
- Modify: `tests/unit/branding/test_go_claw_customer_contract.py`

- [ ] **Step 1: 写/扩展失败合同和 Rust 测试。**

  静态合同断言 productName/title/tooltip/错误框/快捷方式中不含 `QwenPaw`，且 config 引用 `icons/icon.ico`、`icons/icon.icns`。更新 `portable.rs` 现有测试期望 `GO-CLAW-Portable.exe`。

- [ ] **Step 2: 运行失败测试。**

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Run: `cargo test --manifest-path console/src-tauri/Cargo.toml portable`

  Expected: FAIL，仍为旧产品名和旧 EXE 名。

- [ ] **Step 3: 修改共享 Tauri 客户元数据。**

  - 安装版 `productName` 和 window title：`GO CLAW`。
  - 便携 config `productName` 和 title：`GO CLAW`。
  - Cargo package name、binary name和 identifier 保留；description/author/repository 显示元数据改为 GO CLAW 和用户提供的仓库 URL。
  - updater endpoint、shutdown header、环境变量和 sidecar 名保持原样。

- [ ] **Step 4: 修改 Rust/NSIS 可见字符串。**

  启动失败框、fatal 日志前缀、托盘 tooltip、NSIS 安装/重试文案、Debug 快捷方式显示名全部使用 GO CLAW。NSIS 宏名、变量名、`qwenpaw.exe` CLI、debug 脚本文件名和内部 process name 保留。

- [ ] **Step 5: 让 Tauri 图标真正来自 1024px GO CLAW 源图。**

  Windows/macOS 构建脚本都执行：

  ```text
  npm exec -- tauri icon ../scripts/pack/assets/go-claw-app-icon-1024.png
  ```

  Tauri bundle/installer/uninstaller icon 全部改指向 `icons/icon.ico`、`icons/icon.icns`。构建前显式检查 1024px 源图存在；生成命令失败立即终止。旧 `scripts/pack/assets/icon.*` 不再被引用后删除。

- [ ] **Step 6: 运行 Rust、配置和静态合同。**

  Run: `cargo test --manifest-path console/src-tauri/Cargo.toml`

  Run: `python -m json.tool console/src-tauri/tauri.conf.json >/dev/null && python -m json.tool console/src-tauri/tauri.portable.conf.json >/dev/null`

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Expected: PASS。

- [ ] **Step 7: 提交。**

  ```bash
  git add console/src-tauri scripts/pack-tauri/build_win_pyinstaller.ps1 scripts/pack-tauri/build_macos_pyinstaller.sh scripts/pack/assets tests/unit/branding/test_go_claw_customer_contract.py
  git commit -m "feat(desktop): rebrand GO CLAW shell and installer"
  ```

## Task 9：统一 Windows 便携产物名称和使用说明

**Files:**

- Modify: `scripts/pack-tauri/stage_windows_portable.py`
- Modify: `tests/unit/scripts/test_stage_windows_portable.py`
- Modify: `scripts/pack-tauri/README-PORTABLE.zh-CN.txt`
- Modify: `scripts/pack-tauri/build_win_pyinstaller.ps1`
- Modify: `scripts/verify/launch_tauri_windows_portable.ps1`
- Modify: `.github/actions/verify-tauri-windows-portable/action.yml`
- Modify: `tests/unit/branding/test_go_claw_customer_contract.py`

- [ ] **Step 1: 先改 staging 测试期望。**

  固定断言：

  ```python
  assert (root / "GO-CLAW-Portable.exe").read_bytes() == b"MZ-test"
  assert output.zip_path.name == "GO-CLAW-Portable-2.0.1-Windows-x64.zip"
  prefix = "GO-CLAW-Portable-2.0.1-Windows-x64/"
  assert prefix + "GO-CLAW-Portable.exe" in names
  ```

- [ ] **Step 2: 运行并观察旧命名失败。**

  Run: `python -m pytest tests/unit/scripts/test_stage_windows_portable.py -q`

  Expected: FAIL，实际仍为 QwenPaw 名称。

- [ ] **Step 3: 修改 staging 和 README。**

  `ARCHIVE_STEM = "GO-CLAW-Portable-{version}-Windows-x64"`，启动器固定复制为 `GO-CLAW-Portable.exe`。README 标题、双击步骤、目录绑定说明和 PowerShell SHA 命令使用新名称，并明确“盘符从 E/F/G 改变时无需修改配置”。

- [ ] **Step 4: 修改构建和 PowerShell 验收。**

  所有 ZIP glob、EXE path、shell process name 改为 GO-CLAW；`qwenpaw-backend`、`.qwenpaw` 隔离检查、`QWENPAW_*` secret env 保留。两个 subst backing path 使用 `GO CLAW 首次盘` 和 `GO CLAW 中文移动盘`，继续覆盖中文路径。

- [ ] **Step 5: 运行测试和 PowerShell 静态解析。**

  Run: `python -m pytest tests/unit/scripts/test_stage_windows_portable.py tests/unit/test_portable.py tests/unit/branding/test_go_claw_customer_contract.py -q`

  Run on Windows: `powershell -NoProfile -Command "[scriptblock]::Create((Get-Content scripts/verify/launch_tauri_windows_portable.ps1 -Raw)) | Out-Null"`

  Expected: PASS。

- [ ] **Step 6: 提交。**

  ```bash
  git add scripts/pack-tauri/stage_windows_portable.py scripts/pack-tauri/README-PORTABLE.zh-CN.txt scripts/pack-tauri/build_win_pyinstaller.ps1 scripts/verify/launch_tauri_windows_portable.ps1 .github/actions/verify-tauri-windows-portable/action.yml tests/unit/scripts/test_stage_windows_portable.py tests/unit/branding/test_go_claw_customer_contract.py
  git commit -m "feat(portable): rename GO CLAW Windows artifacts"
  ```

## Task 10：更新安装版、macOS 共享脚本和所有桌面发布产物链

**Files:**

- Modify: `scripts/verify/launch_tauri_windows.ps1`
- Modify: `scripts/verify/launch_tauri_macos.sh`
- Modify: `scripts/pack-tauri/build_macos_pyinstaller.sh`
- Modify: `console/src-tauri/src/updates/cache.rs`
- Modify: `.github/workflows/desktop-build.yml`
- Modify: `.github/workflows/desktop-release.yml`
- Modify: `.github/workflows/fork-verify-desktop.yml`
- Modify: `.github/workflows/desktop-publish.yml`
- Modify: `.github/workflows/desktop-promote.yml`
- Modify: `tests/unit/branding/test_go_claw_customer_contract.py`

- [ ] **Step 1: 定义唯一外部产物命名。**

  ```text
  Windows installer: GO-CLAW-2.0.1-Windows-x64-Setup.exe
  Windows artifact:  GO-CLAW-Windows-2.0.1
  Portable artifact: GO-CLAW-Portable-Windows-2.0.1
  macOS ZIP:         GO-CLAW-2.0.1-macOS.zip
  macOS updater:     GO-CLAW-2.0.1-macOS.app.tar.gz
  macOS artifact:    GO-CLAW-macOS-2.0.1
  ```

  updater manifest/endpoint 文件名 `qwenpaw-tauri-latest.json` 属于现有协议，保持不变；manifest 内的可下载二进制 basename 改为上述 GO-CLAW 名称。

- [ ] **Step 2: 先扩展静态合同。**

  扫描这些 workflow/script，禁止客户 artifact glob/label 再出现 `QwenPaw-Portable`、`QwenPaw-Tauri`、`QwenPaw Desktop`；允许 secrets、数据路径、内部进程和 endpoint 中的小写 `qwenpaw`。

- [ ] **Step 3: 运行失败合同。**

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Expected: FAIL，并列出仍使用旧产物名的 workflow 行。

- [ ] **Step 4: 更新安装验证和 updater cache。**

  Windows 安装脚本查找 GO CLAW registry DisplayName 和安装目录，但仍寻找内部 `qwenpaw-desktop.exe`；macOS 查找 `GO CLAW.app`。`updates/cache.rs` 生成与新 manifest 一致的 basename，并更新相应 Rust 单测。

- [ ] **Step 5: 机械迁移全部工作流消费者。**

  从构建上传、下载 artifact、release attach、OSS versioned/latest、updater metadata symlink 到 promote/index merge 全链路同时改名。不得只改 `desktop-build.yml` 而留下 publish/promote glob，否则后续 release 会找不到文件。所有 workflow display name 和 release fallback notes 使用 GO CLAW。

- [ ] **Step 6: 验证 YAML 和无旧 artifact 名。**

  Run: `python - <<'PY'
  from pathlib import Path
  import yaml
  for path in Path('.github/workflows').glob('*.yml'):
      yaml.safe_load(path.read_text(encoding='utf-8'))
  print('workflow yaml ok')
  PY`

  Run: `rg -n "QwenPaw-(Portable|Tauri|Desktop)|QwenPaw Desktop|QwenPaw Portable" .github scripts/pack-tauri scripts/verify console/src-tauri`

  Expected: YAML 解析通过；`rg` 只允许内部兼容注释/协议项，客户 artifact 和显示名零命中。

- [ ] **Step 7: 运行 Rust 和静态合同。**

  Run: `cargo test --manifest-path console/src-tauri/Cargo.toml`

  Run: `python -m pytest tests/unit/branding/test_go_claw_customer_contract.py -q`

  Expected: PASS。

- [ ] **Step 8: 提交。**

  ```bash
  git add scripts/verify scripts/pack-tauri/build_macos_pyinstaller.sh console/src-tauri/src/updates/cache.rs .github/workflows tests/unit/branding/test_go_claw_customer_contract.py
  git commit -m "ci(desktop): migrate GO CLAW artifact pipeline"
  ```

## Task 11：把五名员工、品牌和无密钥要求加入真实桌面验收

**Files:**

- Modify: `scripts/verify/desktop_verify.py`
- Create: `tests/unit/scripts/test_desktop_verify_go_claw.py`
- Modify: `scripts/verify/launch_tauri_windows_portable.ps1`
- Modify: `.github/actions/verify-tauri-windows-portable/action.yml`
- Modify: `.github/actions/verify-tauri-windows/action.yml`
- Modify: `console/src/components/AgentSelector/index.tsx`

- [ ] **Step 1: 写 verifier 单元失败测试。**

  mock `_http` 返回 `/api/agents` 和 `/api/agents/content-production`，断言 verifier 拒绝：员工缺失/乱序/未置顶、content media tools 未启用、tool config 含非空 api_key、HTML title 不是 GO CLAW。

- [ ] **Step 2: 运行失败测试。**

  Run: `python -m pytest tests/unit/scripts/test_desktop_verify_go_claw.py -q`

  Expected: FAIL，验证函数尚不存在。

- [ ] **Step 3: 增加 API 合同验证。**

  `verify_go_claw_employees(base_url)` 检查前 5 个 ID 和中文名称、default active、4 个 specialist enabled+pinned；读取内容生产 agent config，检查 5 个媒体 tool enabled 且 config 不含有效 key。插件 API/磁盘 manifest 还要确认 `qwen-image-tool` 和 `wan27-tool` 已发现。

- [ ] **Step 4: 增加 UI shell 验证。**

  `AgentSelector` 标签增加 `data-testid="digital-employee-count"`。Playwright 在不需要 API Key 的 UI-load 阶段断言：

  - `html[lang="zh-CN"]`；
  - `[data-testid="go-claw-header-logo"]` 可见且 naturalHeight > 0；
  - `[data-testid="digital-employee-count"]` 文本包含 `当前数字员工 (5)`；
  - 页面/顶栏不包含 `QwenPaw`、`文档资料`、`GitHub`、语言切换按钮；
  - 聊天 textarea 可见。

  把 `verify_frontend()` 的 HTML 断言从旧 `qwenpaw` 改为 `<title>GO CLAW</title>` 和 favicon 文件名。

- [ ] **Step 5: 加强便携磁盘和退出验证。**

  PowerShell 在第二盘符启动后检查 marker、5 个 workspace/agent.json、两个插件 manifest；继续验证相同 backend PID/port、外部 project_dir 不重绑、用户 profile/LocalAppData 无新增、优雅退出成功。

- [ ] **Step 6: 运行 verifier 单元测试。**

  Run: `python -m pytest tests/unit/scripts/test_desktop_verify_go_claw.py tests/unit/scripts/test_stage_windows_portable.py tests/unit/test_portable.py -q`

  Expected: PASS。

- [ ] **Step 7: 提交。**

  ```bash
  git add scripts/verify/desktop_verify.py scripts/verify/launch_tauri_windows_portable.ps1 tests/unit/scripts/test_desktop_verify_go_claw.py .github/actions/verify-tauri-windows-portable/action.yml .github/actions/verify-tauri-windows/action.yml console/src/components/AgentSelector/index.tsx
  git commit -m "test(desktop): verify GO CLAW customer package"
  ```

## Task 12：完整本地回归、Windows CI 和最终 ZIP 交付

**Files:**

- Modify only if verification reveals scoped defects: files already listed above
- Produce in CI/download directory: `GO-CLAW-Portable-2.0.1-Windows-x64.zip`
- Produce in CI/download directory: `GO-CLAW-Portable-2.0.1-Windows-x64.zip.sha256`

- [ ] **Step 1: 运行定向 Python 回归。**

  ```bash
  python -m pytest \
    tests/unit/branding/test_go_claw_customer_contract.py \
    tests/unit/agents/test_go_claw_presets.py \
    tests/unit/app/test_go_claw_bundled_plugins.py \
    tests/unit/app/test_go_claw_presets.py \
    tests/unit/app/test_agents_ordering.py \
    tests/unit/scripts/test_stage_windows_portable.py \
    tests/unit/scripts/test_desktop_verify_go_claw.py \
    tests/unit/test_portable.py -q
  ```

  Expected: 全部 PASS。

- [ ] **Step 2: 运行完整前端质量门。**

  ```bash
  cd console
  npm run test:run
  npm run lint
  npm run format:check
  npm run build:prod
  npm run build:tauri-bootstrap
  cd ..
  ```

  Expected: 全部 exit 0；生产 dist 的 HTML 只注册中文并引用 GO CLAW 资源。

- [ ] **Step 3: 运行后端和 Rust 回归。**

  ```bash
  python -m pytest tests/unit -m "not slow" -q
  cargo test --manifest-path console/src-tauri/Cargo.toml
  git diff --check
  git status --short
  ```

  Expected: 测试通过、无 whitespace error；status 只包含本计划改动，完成提交后为空。

- [ ] **Step 4: 提交验证中必要的最小修复。**

  仅当 Step 1–3 暴露本改造缺陷时修复并重新运行对应失败命令；不得顺手修改无关上游问题。最终提交：

  ```bash
  git add -A
  git commit -m "test(release): complete GO CLAW verification gates"
  ```

  如果没有新增改动，不创建空提交。

- [ ] **Step 5: 推送分支并触发唯一 Windows 构建。**

  ```bash
  git push -u origin codex/go-claw-customer-rebrand
  gh workflow run desktop-build.yml \
    --ref codex/go-claw-customer-rebrand \
    -f ref=codex/go-claw-customer-rebrand \
    -f windows_only=true
  GO_CLAW_RUN_ID=$(gh run list \
    --workflow desktop-build.yml \
    --branch codex/go-claw-customer-rebrand \
    --event workflow_dispatch \
    --limit 1 \
    --json databaseId \
    --jq '.[0].databaseId')
  gh run watch "$GO_CLAW_RUN_ID" --exit-status
  ```

  把输出的 `GO_CLAW_RUN_ID` 和 run URL 记录到交付摘要。任何 installer、portable relocation、UI、员工或 LLM gate 失败都必须修复后重跑；不得只下载失败 run 的中间文件。

- [ ] **Step 6: 下载并校验最终产物。**

  ```bash
  gh run download "$GO_CLAW_RUN_ID" \
    -n GO-CLAW-Portable-Windows-2.0.1 \
    -D dist/final-go-claw-windows
  cd dist/final-go-claw-windows
  shasum -a 256 -c GO-CLAW-Portable-2.0.1-Windows-x64.zip.sha256
  unzip -l GO-CLAW-Portable-2.0.1-Windows-x64.zip | sed -n '1,80p'
  ```

  Expected: SHA-256 `OK`；ZIP 根目录为同名 stem；包含 `GO-CLAW-Portable.exe`、`binaries/qwenpaw-backend/qwenpaw-backend.exe`、Python/Node runtime、README、portable.json。

- [ ] **Step 7: 最终交付检查。**

  在 GitHub run 中确认：两个模拟盘符和中文路径启动通过、第二次双击 PID/端口不变、自动拉起 UI、五名员工顺序正确、媒体工具存在但无 key、GO CLAW 品牌可见、旧导航/语言入口不可见、优雅退出通过。然后向用户交付 ZIP、SHA-256、run URL 和测试摘要。

## 最终验收清单

- [ ] 全新 ZIP 解压后双击 `GO-CLAW-Portable.exe`，无需安装 Python/Node。
- [ ] U 盘从任意盘符移动后数据和工作区自动绑定新盘符。
- [ ] Web UI 自动打开，HTML/Ant Design/dayjs/后端语言均为中文。
- [ ] 顶栏 GO CLAW 横版 Logo 高 24px；深色主题使用白色版本。
- [ ] 顶栏和移动端无文档、GitHub、语言入口；主题、代码模式、版本/更新状态保留。
- [ ] 全新目录显示“当前数字员工 (5)”和固定五员工顺序。
- [ ] 4 名 specialist 可编辑、停用、取消置顶、删除；删除后不自动重建。
- [ ] 内容生产能完成文字任务；媒体工具缺 Key 时给中文配置提示，不伪造结果。
- [ ] 客户产物和客户 UI 无旧 QwenPaw 品牌；内部兼容标识保持不变。
- [ ] 最终 ZIP、SHA-256 和 Windows CI 验收记录齐全。

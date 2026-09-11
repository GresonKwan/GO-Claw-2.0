# GO CLAW Windows 产品 U 盘交付标准

> 状态：规范性文档。创建日期：2026-09-07（Asia/Shanghai）。
>
> v2.1.2 只能满足现有 WebView2 或浏览器回退场景；“缺少 WebView2 时自动联网安装并继续打开原生客户端”从 v2.1.3 起实施。已发布 v2.1.2 资产不得原地覆盖。
>
> v2.1.3 发布前复核：2026-09-11。目录、WebView2、凭据边界和首次运行禁止项不变；新增生产组件源与 stable channel 约束。

## 1. 支持边界

- 标准平台：Windows 10/11 x64；U 盘可读写，建议 exFAT；
- 用户入口始终只有盘根目录的 `GO-CLAW-Portable.exe`；不得要求用户进入子目录寻找另一个启动器；
- “任意机器双击即可运行”指上述受支持平台。企业安全策略、杀毒软件或系统管理员明确禁止安装微软运行时的机器必须安全失败并给出原因，产品不得尝试绕过系统策略；
- FAT32 不作为新产品盘标准格式，因为单文件 4 GiB 限制会影响视频和后续交付物；现有 FAT32 盘应在无客户数据时重制为 exFAT。

## 2. 出厂根目录唯一结构

```text
<ProductDrive>:\
├── GO-CLAW-Portable.exe
├── portable.json
├── binaries\
├── GO-CLAW-Config\
│   ├── provision.json
│   ├── credentials.example.json
│   └── update-pubkey.txt
├── WebView2\
│   └── MicrosoftEdgeWebview2Setup.exe
├── MANIFEST.json
├── SHA256SUMS.txt
├── START-HERE.zh-CN.txt
├── README-PORTABLE.zh-CN.txt
└── LICENSE
```

所有产品盘必须由同一部署脚本从同一个已验签构建生成；禁止分别采用“只复制 Portable”“复制 Full 包附件”或人工补文件等不同口径。

## 3. 各项内容合同

### 3.1 程序与运行时

- `GO-CLAW-Portable.exe`：唯一用户启动入口；文件版本、产品版本、UI 版本和 Manifest 版本必须一致；
- `portable.json`：合法 schema，标准值为 `clientMode=auto`；
- `binaries/`：完整的签名活动程序槽、后端、Node/Python runtime、媒体插件和更新引擎，不得拆分；
- `GO-CLAW-Config/provision.json`：新盘自动开通配置；共享 HMAC 的可提取局限按 provisioning 专题文档记录；
- `GO-CLAW-Config/update-pubkey.txt`：必须与客户端内置公钥及 CI Variable 一致；
- `credentials.example.json` 只作格式说明。正式产品盘不得包含静态 `credentials.json`。
- v2.1.3 及以后，产品内更新入口优先使用 `https://goclaw.host:8443/updates`；生产 v2 index 与
  manifest 必须同为 `channel=stable`，所有组件 URL 必须保持该受信同源。GitHub Release 只作公开归档
  或人工恢复来源，不得成为标准产品盘在线更新的唯一运行时依赖。

### 3.2 WebView2

- v2.1.3 标准联网交付携带微软官方 x64 Evergreen **Bootstrapper**（约 1.8 MB）；必须准确标记为 `evergreen-bootstrapper` 和 `requiresNetwork=true`，不得再误标为 Standalone；
- CI 必须验证：普通 PE 文件、微软 Authenticode 有效、签名主体为 Microsoft Corporation、下载来源和构建记录固定、内部 `OriginalFilename=MicrosoftEdgeUpdateSetup.exe`、文件身份与 Bootstrapper 类型正确，SHA-256 写入 Manifest；产品内规范落盘名仍为 `MicrosoftEdgeWebview2Setup.exe`，不得把两者混为一项；不能因为文件约 1.8 MB 或内部属于 Edge Update 安装器而把合法 Bootstrapper 当成损坏文件；
- v2.1.3 启动器必须在创建 WebView 前检查系统级和用户级 WebView2；缺失时从当前产品根解析 Bootstrapper，执行 `/silent /install`，有界等待并复验。安装需要客户机能访问微软下载服务；
- 安装成功后只重试一次原生 WebView。必要时只允许受循环标记保护的一次自重启；不得重复安装、重复启动后端或无限等待；
- 无网络、安装失败或被系统策略阻止时，记录非秘密阶段、退出码和日志位置，只打开一次系统浏览器作为兜底；若系统浏览器可用，用户仍可访问本地 GO CLAW Web UI，但不得声称断网机器必能打开原生窗口；
- 可另做“离线交付 profile”携带约 127 MB 的官方 x64 Evergreen Standalone Installer，但它不是 v2.1.3 标准产品盘的必需项，且 manifest/type/文件名必须与联网 profile 区分；
- Manifest 或安装器本身不会执行自动安装。只有“正确安装器 + 启动器编排代码 + 安装后复验”三者同时存在，才能满足单 EXE 目标。

### 3.3 Manifest、校验和说明

- 产品盘只保留一个规范名称 `MANIFEST.json`，`platform=windows-x86_64`，版本与实际客户端一致；
- Manifest 的文件路径必须相对盘根目录，不得保留 Full ZIP 内的 `Portable/` 前缀；
- Manifest 与 `SHA256SUMS.txt` 必须覆盖全部出厂文件，包括 WebView2 Bootstrapper；不得覆盖首次运行生成的数据；
- Manifest 必须准确记录 WebView2 分发类型和联网要求。标准 profile 必须写 `evergreen-bootstrapper`、`requiresNetwork=true`；离线 profile 才能写 `evergreen-standalone-x64`；
- `START-HERE.zh-CN.txt` 和 `README-PORTABLE.zh-CN.txt` 的版本、启动方式、WebView2 行为、退出和安全弹盘说明必须与本次构建一致；不得沿用旧版本标题；
- Manifest 是被动校验元数据，不替代签名、不安装依赖，也不改变启动行为。

## 4. 出厂时禁止存在

以下目录和文件只能在首次运行后生成，出厂验收时必须不存在：

- `data/`、`secrets/`、`backups/`、`logs/`、`cache/`、`updates/`；
- `credentials.json`、`instance.id`、聊天数据库、媒体产物、账本 profile；
- `installing.lock`、更新失败摘要、旧版本备份、测试 token、私钥、构建缓存和调试日志。

Windows 自动创建的隐藏 `System Volume Information` 不属于产品内容，不参与文件清单，也不得由部署脚本删除。

## 5. 标准部署顺序

1. 按物理磁盘序列号确认目标，不仅依赖 E/F/G 盘符；
2. 仅在明确授权且确认无客户数据时格式化为 exFAT；
3. 验证正式构建来源、版本、签名和完整清单；
4. 使用唯一部署脚本把规范结构写入盘根目录，不使用删除型镜像参数；
5. 按产品盘根相对路径逐项验证 SHA-256；
6. 验证 WebView2 Bootstrapper 的微软签名、正确分发类型和联网声明；
7. 验证禁止项不存在、根 EXE 唯一且没有产品进程；
8. 记录盘符、物理序列号尾部、文件系统、版本、文件数、总字节数、根 EXE SHA-256 和失败数。

## 6. 双击启动验收矩阵

| 场景 | 预期结果 |
| --- | --- |
| 已安装可用 WebView2 | 不启动安装器，直接打开原生客户端 |
| 未安装 WebView2、机器联网 | 使用盘内 Bootstrapper 联网完成安装，原生客户端打开 |
| 未安装 WebView2、机器断网 | 有界失败并只回退一次系统浏览器；不得承诺原生窗口可用 |
| 标准非管理员账户 | 按用户安装并打开客户端；不得要求用户手动找安装器 |
| 安装器缺失、损坏或签名无效 | 不执行文件，有界失败并一次性浏览器回退 |
| 企业策略禁止安装 | 不绕过策略；显示原因、日志位置并一次性浏览器回退 |
| U 盘盘符变化 | 从当前 EXE 根重新解析全部路径，行为不变 |

## 7. E/G 盘历史快照（2026-09-07，不作为当前产品事实）

- 当时 E 盘：客户端 v2.1.2 正确，但为 FAT32；携带的 1,783,000 字节文件实际是联网 Bootstrapper，Manifest 误标 Standalone，且路径带 `Portable/` 前缀；README 标题仍为 2.0.1。不符合本标准；
- 当时 G 盘：客户端 v2.1.2 正确，但缺少 `WebView2/`、根 Manifest、SHA256SUMS 和 START-HERE；README 标题仍为 2.0.1。不符合本标准；
- 两盘根 EXE SHA-256 均为 `F81A2331B4FABFBC5DB51C117ED9BE7A401978DEA2AA33621D0E2C37351D777C`，差异来自包装和部署流程，不是客户端二进制版本不同。

## 8. 版本约束

- v2.1.2：允许已有 WebView2 时打开原生客户端，缺失时浏览器回退；不得宣称自动安装；
- v2.1.3：完成本标准中的可信联网 Bootstrapper、自动检测/安装/复验/重试，并通过上述矩阵后，才允许使用“联网 Windows 10/11 x64 上，一个标准 U 盘、双击一个 EXE 打开客户端”的交付表述；离线原生启动只有采用并验证离线 profile 时才可单独宣称；
- 不得覆盖已发布 v2.1.2 Release、tag、签名文件或生产清单。

## 9. 版本维护规则

- 每个新版本立项时和正式发布前，必须各复核一次本标准；
- 如果版本改变产品盘目录、运行时依赖、开通/配置方式、更新保留边界、签名或 Manifest、随盘说明、部署流程，必须在同一变更中同步更新本标准；
- 如果复核确认无需修改，也要在该版本计划或发布检查表中记录“已复核，无需修改”，避免因沉默而无法区分“确认未受影响”和“从未检查”；
- 此要求是文档与交付口径复核，不得实现为启动时扫描、联网校验或其他会增加用户运行开销的门禁。

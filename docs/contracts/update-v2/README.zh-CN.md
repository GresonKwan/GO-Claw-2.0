# v2 组件发布机器合同

状态：2026-09-05 本地 schema、确定性分包、签名索引、历史目录、独立安装协调器、Bridge、产品
更新按钮和 draft Release 构建/发布工作流已接线；1.43GB full staging 已做两轮确定性分包且逐文件
SHA-256 相同。**尚未切换生产更新源或发布正式 Release**，本地产物未签名，客户盘 A/B 验收仍未完成。上层约束见
[v2.1.2 合同](../v2.1.2/README.zh-CN.md) UP-C1–4，实施进度见
[实施计划](../../superpowers/plans/2026-09-03-go-claw-v2-1-2-implementation-plan.md)。

OSS 发布采用 fail-closed 配置：仅接受 `GO_CLAW_OSS_BUCKET`、`GO_CLAW_OSS_PUBLIC_BASE_URL`、
`GO_CLAW_OSS_ENDPOINT`、`GO_CLAW_OSS_ACCESS_KEY_ID`、`GO_CLAW_OSS_ACCESS_KEY_SECRET`，且在上传前
拒绝包含 `qwenpaw` 或 `agentscope` 的目标。没有配置时不得使用任何上游默认地址。

## 文件职责

| 文件 | 用途 |
| --- | --- |
| `release-index.schema.json` | schemaVersion=2，小型发现目录，版本/commit/摘要/签名引用 |
| `release-catalog.schema.json` | schemaVersion=2、有界且签名的历史 release index 目录，供跨版本规划 |
| `windows-release.schema.json` | schemaVersion=2，精确程序文件归属、组件包和目标槽位删除清单 |
| `transaction.schema.json` | schemaVersion=1，未来引擎持久化 journal 结构，不是现行启动授权 |
| `fixtures/*.valid.json` | 合成结构样本；签名为无效占位值，严禁用于发布 |
| `../../../scripts/pack-tauri/update_components.py` | 纯路径/归属/摘要逻辑，不在客户启动或 check 中扫描 |
| `../../../scripts/pack-tauri/build_component_packages.py` | 固定排序/ZIP 元数据、流式校验；只输出 unsigned draft |
| `../../../scripts/pack-tauri/build_release_index_v2.py` | 已签名 manifest/组件/Bridge 验证后构建待签名 index |
| `../../../scripts/pack-tauri/assemble_component_manifest.py` | 验证签名组件，要求壳/后端/Python/Node/文档/媒体种子齐全，装配待签名 manifest |
| `../../../scripts/pack-tauri/build_release_catalog_v2.py` | 验证每份已签名 index 后生成待签名的最多 50 版历史目录 |

schema 是结构校验，不是安装授权。Python 语义检查还负责 Windows 设备名、重解析点、路径大小写
冲突、唯一归属、包文件覆盖、字节数和内容摘要；最终引擎必须重复校验并遵守安装锁及活动槽位约束。
允许新增可选字段，未知主 schema/入口/组件拒绝。普通客户端不得将旧 status 伪装为 schemaVersion=2。

## 本地工具输入与输出

分包工具只接受**不可变的构建 staging**和逐文件精确 assignments：

```json
[
  {"relativePath":"GO-CLAW-Portable.exe","component":"desktop-shell","mount":"bootstrap"},
  {"relativePath":"binaries/qwenpaw-backend/qwenpaw-backend.exe","component":"backend-core","mount":"slot"}
]
```

样例不完整；真实 staging 的 `binaries` 与白名单根程序文件必须全部恰好归属一次。重型依赖和只读
插件种子使用 `build_assignments()` 从已知 PyInstaller 布局生成精确归属，不得把上述两项样例当
通用分包配置。省略 `--assignments` 使用默认归属器；未知程序布局拒绝。PYZ 仍在 backend-core，
只有独立落盘的重型依赖才单独复用，不能声称 PyInstaller 的全部 Python 内容都可独立更新。
实际 Full staging 构建仍需在本机 Main Build 验收；签名命令与 workflow 接线已完成 Task 1.3 的代码落地。

`build_component_packages.py --root <staging> --assignments <json> --output <新目录>
--base-url <HTTPS资产目录> --trusted-host <受信主机>` 生成按 contentDigest 命名的组件 ZIP 与
`components.unsigned.json`。新目录必须位于 staging 外且不存在；中途失败保留诊断用部分产物，
不得发布或覆盖重用。ZIP 的顺序、时间、文件模式与压缩等级固定；可重现范围是相同固定 Python/zlib
构建环境。内存按 1MiB 数据块使用，metadata 与文件数线性增长；不全量读入视频/运行库大文件。

签名与索引顺序：组件打包 → 既有 signer 签组件 → 完成 release manifest → signer 签 manifest
与 Bridge → 本工具验证并生成 index → signer 签**原始 index 字节**。工具不读取私钥、不下载、不上传。
`assemble_component_manifest.py` 接收 `--draft`、`--pubkey-config`（现有 Tauri 配置）、
`--version`、`--commit`、`--channel`、`--trusted-host`、`--output`，读取组件旁的 `.zip.sig`；
全部通过后独占创建 manifest。输出仍须签名，不能把 unsigned draft 直接用于发布。
索引命令参数为 `--manifest`、`--manifest-url`、`--bridge`、`--bridge-url`、`--pubkey-file`、
`--legacy-latest`、`--output` 和重复的 `--trusted-host`；大包只从 manifest 同目录读取。
manifest/Bridge 的 `.sig` 为 Tauri base64 签名块；组件签名在 manifest 内。

保留当前公钥链，组件链要求现代 minisign `ED`（BLAKE2b 预摘要），并验证 trusted comment 全局签名。
旧 `Ed`/无算法前缀不能被重新解释为 `ED`；本新工具拒绝，既有 legacy 更新验签行为不改。
新旧目录必须同 version/buildCommit，旧 Windows 条目的 URL/signature 必须指向同一 Bridge；旧
latest 的 `buildCommit` 是兼容的附加字段，后续构建接线需提供。Bridge 内嵌目标摘要核验由其构建与
实机合同负责，本工具不以 exe 验签成功代替 Bridge 行为验收。

## 验证

使用包含项目 `test` extra 的 Python 环境运行现有 scripts 单测，无新增 CI job：

```powershell
python -m pytest --confcutdir=tests/unit/scripts tests/unit/scripts/test_v212_contracts.py tests/unit/scripts/test_update_components.py tests/unit/scripts/test_release_index_v2.py -q
```

`--confcutdir` 仅在本地隔离纯构建合同测试与全应用依赖；完整项目测试仍走既有测试流程。
测试使用小型临时程序树和临时签名 key，绝不读取/修改产品盘、客户聊天、余额、生产签名密钥或更新源。
结构样本通过与签名通过分别报告；UI、真实 A/B 更新、断电回滚和旧用户无损验收仍按主计划执行。

## Rust 模块实施边界（2026-09-04）

`console/src-tauri/src/update_engine/` 已新增 manifest/paths/verify/state/slots/planner/extract/
download/progress；由 `tests/update_engine_contract.rs` 编译并测试。17 项测试覆盖路径、
组件摘要、已知 ED 验签向量、文件内容复用、ZIP 校验、日志恢复、独占锁、数据根不随槽位变化及进度。
09-05 已挂到 PortableState 启动解析，新增独立 CLI、安装/恢复协调器、HTTP/SSE 状态和统一更新
按钮。Bridge 的 headless 可执行合同与正常 UI 脚本均使用 NSIS 3.11 编译通过；前者验证中文/空格
便携根、精确参数和客户数据摘要不变。不能据此认为真实签名大包或生产 A/B 已验收。

2026-09-04 补充：Rust manifest 语义校验与 Python 装配器一样要求完整固定入口文件、运行库及
两个媒体插件种子，缺任一项拒绝安装规划/完整树验证/槽位解析；仅遍历清单，不扫描客户数据。
槽位解析先验证原始 manifest 字节签名再反序列化。机器 fixture 是结构示例，只有一个 core.exe
的 fixture 不满足可运行产品语义；Rust 正向测试使用完整合成清单，不降低规则迁就简化样本。

下载实现已编译，但还未覆盖真实 HTTP Range/断网矩阵；续传、重试/取消、缓存隔离和完整恢复协调
仍需在发布前复核。bootstrap/recovery/独立 binary、壳备份事务和绑定进程的健康通道已开发，
离线中断恢复与真实签名/子进程/U 盘验收必须分开记录。CLI install/recover 不供客户手工猜参数执行。
本地流故障测试已覆盖 response body 中断/短读：重试前截回完整 range 检查点并恢复增量摘要，
避免失败后缀与重试数据拼接；计数保留真实传输字节，越界/取消/磁盘错误不作网络重试。
这不是实际 HTTPS Range/ETag、服务器忽略 Range 的大包或无进展超时验收。
同一 journal 交易的来源/目标版本、槽位、generation、manifest 和新旧壳摘要一经持久化不可改写；
发现目标变化在写入前返回 TARGET_CHANGED，当前/上一 journal 均保留。新增逐字段拒绝回归。
Rust 最低版本提升至 1.88（ZIP 依赖要求）；本机使用隔离的 stable 1.98.1 + MSVC 编译。

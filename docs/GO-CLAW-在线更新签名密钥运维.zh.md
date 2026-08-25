# GO CLAW 在线更新签名密钥运维

> 状态：已生效（2026-08-26 首次建钥）。
> 范围：Tauri updater / minisign(Ed25519) 更新包签名，不是 Windows Authenticode 代码签名证书。

## 1. 密钥身份与唯一信任链

- 当前 minisign 注释 Key ID：`B40B8ADD55C769D7`（原始 key-id 字节 hex：`d769c755dd8a0bb4`）。
- 当前 Tauri 公钥：

  ```text
  dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEI0MEI4QURENTVDNzY5RDcKUldUWGFjZFYzWW9MdEVycDBDMGNBN1NZWWpNbmg2NDIwYitxUEF3OEs0VWpPdjJIdE1ENFVTNkcK
  ```

以下三个消费点必须字符级一致：

1. `console/src-tauri/tauri.conf.json` 的 `plugins.updater.pubkey`；
2. GitHub Actions Variable `TAURI_UPDATER_PUBKEY`；
3. 便携包内 `GO-CLAW-Config/update-pubkey.txt`。

第 3 处不手工维护，由 `scripts/pack-tauri/stage_windows_portable.py`
每次从第 1 处自动生成。GitHub Variable 在 CI 构建时会覆盖基础配置，
所以第 1、2 处任一不一致都必须停止发布。

## 2. 私钥保管

| 对象 | 存放位置 | 规则 |
|------|----------|------|
| 加密私钥主副本 | `~/Library/Application Support/GO CLAW/keys/tauri-updater.key` | 仓库外；目录 `0700`，文件 `0600` |
| 加密私钥灾备副本 | `/Volumes/固态2/GO-CLAW-Secrets/tauri-updater.key` | 与主副本分属不同磁盘；目录 `0700`，文件 `0600` |
| 私钥口令 | macOS 登录钥匙串 | service=`GO CLAW Tauri Updater`，account=`TAURI_SIGNING_PRIVATE_KEY_PASSWORD` |
| CI 私钥 | GitHub Secret `TAURI_SIGNING_PRIVATE_KEY` | 内容是加密私钥文件全文，不是路径 |
| CI 口令 | GitHub Secret `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | 与钥匙串中口令一致 |

私钥和口令禁止进入 Git、`.env`、issue、聊天、构建日志或便携包；
不通过邮件/即时通讯工具传递私钥。协作者发版只使用 GitHub Actions，
默认不获得私钥。

## 3. GitHub 初始化与恢复

目标仓库固定为 `GresonKwan/GO-Claw-2.0`，所有 `gh` 命令必须显式带
`-R GresonKwan/GO-Claw-2.0`，防止误写上游仓库。同步顺序为：

1. 从加密私钥文件写入 `TAURI_SIGNING_PRIVATE_KEY`；
2. 从 macOS 钥匙串通过管道写入 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`，不在终端打印；
3. 从 `.pub` 文件写入 `TAURI_UPDATER_PUBKEY`；
4. 只查看 Secret 名称/更新时间，不尝试回读内容。

GitHub Secret 不可回读，因此它不是备份。主副本丢失时，从外置卷复制
灾备副本，再从钥匙串取回口令。如两个加密副本或口令同时丢失，
已安装客户端将无法继续通过现有信任链接收新更新。

## 4. 每次发布前必查

1. 确认 `tauri.conf.json`、`TAURI_UPDATER_PUBKEY`、本地 `.pub` 三者完全相等；
2. 用本地主副本签名一个无敏感探针文件，再用包内同源公钥验签；
3. 确认 CI 中两个 Secret 与一个 Variable 均已配置；
4. 确认 `generate_update_manifest.py --pubkey-config` 的 key-id 检查通过；
5. 发布后从 Release 下载 `setup.exe` / `.sig` / `latest.json`，至少完成一次客户端真实验签。

每 6 个月做一次保管审计：比对两个加密副本、用灾备副本完成签名探针、
核对 GitHub 配置名称和权限，并在变更台账的“运营侧变更”记录日期与结果。

## 5. 轮换与泄露处置

当前客户端是单公钥信任。不做“直接替换 Secret + 公钥”的原地轮换，
否则已安装客户端会永久拒绝新签名。正常轮换必须单独建计划，分两阶段：

1. 用旧私钥签名“桥接版”，桥接版内置新公钥；转换 CI 需显式分离
   “本次产物签名旧公钥”和“包内下一代公钥”的 key-id 检查；
2. 确认受支持客户端已升级到桥接版后，再切换 GitHub Secret/Variable 并发布新钥签名版。

触发轮换的条件：疑似泄露、维护人员权限变更、保管介质失窃或算法/工具链风险。
不为了日历频率冒险更换单公钥。

如疑似私钥泄露，立即暂停更新发布、限制 Release/Actions 权限、保留审计证据，
并通过完整安装包和客户通知建立新信任链；不得继续用可疑私钥发布普通更新。

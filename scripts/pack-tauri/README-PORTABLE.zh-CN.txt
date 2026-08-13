QwenPaw Portable 2.0.1（Windows 10/11 x64）
================================================

快速启动
--------
1. 将 ZIP 完整解压到 NTFS 或 exFAT 格式的 U 盘目录。
2. 双击 QwenPaw-Portable.exe。
3. 首次启动需要初始化，通常等待 10–120 秒；准备完成后会自动打开系统默认浏览器。

请勿只复制 EXE。binaries、portable.json 与 EXE 必须保持在同一完整目录结构中。

数据与退出
----------
QwenPaw 的数据存放在 EXE 同目录下的 data、secrets、backups、logs 和 cache 目录。
U 盘盘符变化后，QwenPaw 会自动迁移自身工作区、媒体和项目路径。
运行时请勿拔出 U 盘。请先通过系统托盘图标选择 Quit，确认程序退出后再安全弹出。

API 与模型
----------
启动本地核心和客户端页面不要求 API Key。调用在线模型时，仍需在客户端中配置相应服务商的 API Key。
本压缩包不包含本地大模型权重；本地模型可能需要额外数 GB 空间。

安全说明
--------
secrets 与应用数据保存在同一 U 盘。U 盘遗失可能导致离线数据泄露，敏感场景建议使用 BitLocker To Go。
Windows SmartScreen 可能提示未识别的应用；请确认下载来源并核对 SHA-256 后再运行。
系统浏览器自身的历史、缓存以及 Windows 最近使用记录不属于便携数据范围。

日志与校验
----------
启动问题请查看 logs\qwenpaw-desktop.log 和 data\desktop.log。
在 PowerShell 中校验 ZIP：

  Get-FileHash .\QwenPaw-Portable-2.0.1-Windows-x64.zip -Algorithm SHA256

将输出与同目录 .zip.sha256 文件中的值对比。

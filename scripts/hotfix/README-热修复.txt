GO CLAW v2.1.1 媒体工具 / 数字员工紧急热修复
====================================================

适用版本：仅 v2.1.1

普通修复：
1. 将本目录中的 PS1、JS 和 CMD 三个文件复制到产品盘根目录。
2. 双击“运行-GO-CLAW-v2.1.1-热修复.cmd”。
3. 等待 GO CLAW 重新启动并显示“热修复成功”。

脚本会：
- 正常退出 GO CLAW；
- 备份并更新 qwen-image / wan27 两个内置媒体插件；
- 自动识别失败或不可读的内置数字员工；
- 将故障 workspace 移入 data\hotfix-backups 后重新生成；
- 重启并验证两个媒体插件已启用、修复员工为 running。

所有被替换内容都会保存在：
data\hotfix-backups\日期时间\

如果 Windows 报“文件或目录损坏且无法读取”：
1. 不要拔出产品盘。
2. 以管理员身份打开 PowerShell。
3. 进入产品盘根目录，运行：
   powershell -ExecutionPolicy Bypass -File .\GO-CLAW-v2.1.1-Hotfix.ps1 -ProductRoot . -RepairFailedEmployees -RunCheckDisk

该模式会先执行 CHKDSK /F，再进行同样的可回滚修复。

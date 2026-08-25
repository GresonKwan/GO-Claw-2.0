; ============================================================================
; GO CLAW 便携版在线更新安装包
; 用法: GO-CLAW-Update-<ver>-setup.exe /S /D=<便携根目录>
; 契约（与 console/src-tauri/src/updates.rs 的 install_cached_windows 对齐）：
;   - 静默安装（/S），目标目录由 /D 传入（必须含 portable.json）
;   - 白名单替换：仅 GO-CLAW-Portable.exe / binaries / LICENSE / README
;   - 绝不触碰 data/secrets/logs/cache/backups/updates/GO-CLAW-Config/portable.json
;   - 替换前将旧程序文件备份到 updates\backup-<旧版本>\（回滚点）
;   - 安装期间写 updates\installing.lock，完成即删（半更新状态防启动）
; ============================================================================

!ifndef GO_CLAW_VERSION
  !define GO_CLAW_VERSION "unknown"
!endif

!include LogicLib.nsh

Name "GO CLAW Update ${GO_CLAW_VERSION}"
OutFile "GO-CLAW-Update-${GO_CLAW_VERSION}-setup.exe"
Unicode true
SetCompressor /SOLID lzma
SilentInstall silent
RequestExecutionLevel user
ShowInstDetails hide
ShowUninstDetails hide

Var OldVersion

!macro GO_CLAW_BACKUP_ITEM path
  IfFileExists "$INSTDIR\${path}" 0 +7
    CreateDirectory "$INSTDIR\updates\backup-$OldVersion"
    ClearErrors
    Rename "$INSTDIR\${path}" "$INSTDIR\updates\backup-$OldVersion\${path}"
    IfErrors 0 +4
      DetailPrint "backup failed: ${path}"
      SetErrorLevel 1
      Abort "无法备份 ${path}，已中止（未做任何修改）"
!macroend

Function .onInit
  ; /D= 传入的 $INSTDIR 必须是有效便携根（防参数错配误伤其它目录）
  IfFileExists "$INSTDIR\portable.json" go_claw_root_valid
    MessageBox MB_ICONSTOP|MB_OK "GO CLAW 更新失败：目标目录不是有效的 GO CLAW 便携目录（未找到 portable.json）。$\r$\n$\r$\n$INSTDIR"
    Abort
  go_claw_root_valid:

  ; 读取旧版本号（无则 unknown）
  StrCpy $OldVersion "unknown"
  IfFileExists "$INSTDIR\updates\version.txt" 0 +6
    FileOpen $0 "$INSTDIR\updates\version.txt" r
    IfErrors +4
    FileRead $0 $1
    StrCpy $OldVersion $1
    FileClose $0

  ; 安装锁：存在即拒绝并发安装
  IfFileExists "$INSTDIR\updates\installing.lock" 0 +3
    MessageBox MB_ICONSTOP|MB_OK "检测到未完成的更新（installing.lock）。请先重启 GO CLAW 完成恢复，或手动删除 updates\installing.lock 后重试。"
    Abort
  CreateDirectory "$INSTDIR\updates"
  FileOpen $0 "$INSTDIR\updates\installing.lock" w
  FileWrite $0 "${GO_CLAW_VERSION}"
  FileClose $0
FunctionEnd

Section "KillRunningApp"
  ; 更新由后端拉起安装包时应用仍在运行：先结束应用与后端进程
  ; （安装包由后端进程 spawn，taskkill 发生在此之后，不影响安装本身）
  ExecWait 'taskkill /F /IM GO-CLAW-Portable.exe'
  ExecWait 'taskkill /F /IM qwenpaw-backend.exe'
  ; 等待文件锁释放
  Sleep 2000
SectionEnd

Section "BackupOldVersion"
  ; 同版本重复安装时先清掉旧备份点，避免 Rename 目标已存在而失败
  RMDir /r "$INSTDIR\updates\backup-$OldVersion"

  ; 备份旧程序文件（白名单项；不存在的项自动跳过）
  !insertmacro GO_CLAW_BACKUP_ITEM "GO-CLAW-Portable.exe"
  !insertmacro GO_CLAW_BACKUP_ITEM "binaries"
  !insertmacro GO_CLAW_BACKUP_ITEM "LICENSE"
  !insertmacro GO_CLAW_BACKUP_ITEM "README-PORTABLE.zh-CN.txt"
SectionEnd

Section "InstallNewVersion"
  ; payload 由 CI 暂存（仅白名单内容），按原结构释放到便携根
  SetOutPath "$INSTDIR"
  File /r "payload\*.*"

  ; 记录版本与更新历史
  FileOpen $0 "$INSTDIR\updates\version.txt" w
  FileWrite $0 "${GO_CLAW_VERSION}"
  FileClose $0

  FileOpen $0 "$INSTDIR\updates\last-update.json" w
  FileWrite $0 '{"version": "${GO_CLAW_VERSION}", "previous": "$OldVersion"}'
  FileClose $0
SectionEnd

Function .onInstSuccess
  Delete "$INSTDIR\updates\installing.lock"
  ; 安装完成自动重启 GO CLAW
  Exec '"$INSTDIR\GO-CLAW-Portable.exe"'
FunctionEnd

Function .onInstFailed
  ; 尽力清理锁，便于人工介入（备份仍在 backup-<旧版本> 下可手工恢复）
  Delete "$INSTDIR\updates\installing.lock"
FunctionEnd

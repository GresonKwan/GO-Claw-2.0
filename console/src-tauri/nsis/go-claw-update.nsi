; ============================================================================
; GO CLAW 便携版在线更新安装包
; 用法: GO-CLAW-Update-<ver>-setup.exe /S /D=<便携根目录>
; 契约（与 console/src-tauri/src/updates.rs 的 install_cached_windows 对齐）：
;   - 静默安装（/S），目标目录由 /D 传入（必须含 portable.json）
;   - 白名单替换：仅 GO-CLAW-Portable.exe / binaries / LICENSE / README
;   - 绝不触碰 data/secrets/logs/cache/backups/updates/GO-CLAW-Config/portable.json
;   - 先完整释放到 updates\staging-<新版本>，再停止应用并切换文件
;   - 替换前将旧程序文件备份到 updates\backup-<旧版本>\（回滚点）
;   - 任一步失败均自动恢复旧程序并重新启动，禁止遗留半更新状态
;   - 安装期间写 updates\installing.lock，成功或回滚完成后删除
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
Var BackupStarted
Var RestartOnFailure
Var FailureStage
Var RetryCount

!macro GO_CLAW_BACKUP_ITEM_RETRY path id
  IfFileExists "$INSTDIR\${path}" 0 go_claw_backup_done_${id}
  StrCpy $RetryCount 0
  go_claw_backup_retry_${id}:
    CreateDirectory "$INSTDIR\updates\backup-$OldVersion"
    ClearErrors
    Rename "$INSTDIR\${path}" "$INSTDIR\updates\backup-$OldVersion\${path}"
    IfErrors 0 go_claw_backup_done_${id}
    IntOp $RetryCount $RetryCount + 1
    IntCmp $RetryCount 30 go_claw_backup_failed_${id} go_claw_backup_wait_${id} go_claw_backup_failed_${id}
  go_claw_backup_wait_${id}:
    Sleep 1000
    Goto go_claw_backup_retry_${id}
  go_claw_backup_failed_${id}:
    StrCpy $FailureStage "backup:${path}"
    DetailPrint "backup failed after retries: ${path}"
    SetErrorLevel 1
    Abort "无法备份 ${path}，已自动恢复旧版本。请关闭仍在运行的 GO CLAW 相关进程后重试。"
  go_claw_backup_done_${id}:
!macroend

!macro GO_CLAW_INSTALL_STAGED_ITEM path id
  IfFileExists "$INSTDIR\updates\staging-${GO_CLAW_VERSION}\${path}" 0 go_claw_stage_missing_${id}
    ClearErrors
    Rename "$INSTDIR\updates\staging-${GO_CLAW_VERSION}\${path}" "$INSTDIR\${path}"
    IfErrors 0 go_claw_install_done_${id}
      StrCpy $FailureStage "install:${path}"
      SetErrorLevel 1
      Abort "无法安装 ${path}，已自动恢复旧版本。"
  go_claw_stage_missing_${id}:
    StrCpy $FailureStage "staging-missing:${path}"
    SetErrorLevel 1
    Abort "更新包缺少 ${path}，已自动恢复旧版本。"
  go_claw_install_done_${id}:
!macroend

Function RestoreBackup
  StrCmp $BackupStarted "1" 0 go_claw_restore_done

  ; 只恢复确实已经移入备份的项目。若某项因文件锁未能移动，原项仍在
  ; 根目录，绝不能先删除它（本次 2.0.1 -> 2.1.0 故障即发生在此阶段）。
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\GO-CLAW-Portable.exe" 0 go_claw_restore_binaries
    Delete "$INSTDIR\GO-CLAW-Portable.exe"
    Rename "$INSTDIR\updates\backup-$OldVersion\GO-CLAW-Portable.exe" "$INSTDIR\GO-CLAW-Portable.exe"

  go_claw_restore_binaries:
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\binaries\*.*" 0 go_claw_restore_license
    RMDir /r "$INSTDIR\binaries"
    Rename "$INSTDIR\updates\backup-$OldVersion\binaries" "$INSTDIR\binaries"

  go_claw_restore_license:
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\LICENSE" 0 go_claw_restore_readme
    Delete "$INSTDIR\LICENSE"
    Rename "$INSTDIR\updates\backup-$OldVersion\LICENSE" "$INSTDIR\LICENSE"

  go_claw_restore_readme:
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\README-PORTABLE.zh-CN.txt" 0 go_claw_restore_done
    Delete "$INSTDIR\README-PORTABLE.zh-CN.txt"
    Rename "$INSTDIR\updates\backup-$OldVersion\README-PORTABLE.zh-CN.txt" "$INSTDIR\README-PORTABLE.zh-CN.txt"

  go_claw_restore_done:
FunctionEnd

Function .onInit
  StrCpy $BackupStarted "0"
  StrCpy $RestartOnFailure "0"
  StrCpy $FailureStage "initialization"

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

Section "StagePayload"
  ; 在停止应用、移动任何旧文件之前先完整释放新版本。即使 U 盘空间不足
  ; 或更新包解压失败，旧程序也仍保持原样并继续运行。
  StrCpy $FailureStage "staging"
  RMDir /r "$INSTDIR\updates\staging-${GO_CLAW_VERSION}"
  CreateDirectory "$INSTDIR\updates\staging-${GO_CLAW_VERSION}"
  SetOutPath "$INSTDIR\updates\staging-${GO_CLAW_VERSION}"
  ClearErrors
  File /r "payload\*.*"
  IfErrors 0 go_claw_stage_complete
    SetErrorLevel 1
    Abort "更新文件释放失败，旧版本未被修改。请检查 U 盘剩余空间后重试。"
  go_claw_stage_complete:
SectionEnd

Section "StopRunningApp"
  ; 优先复用便携客户端自身的退出协议，让后端完整执行 shutdown hooks 并
  ; 释放 binaries 下的 exe/dll。最多等待 60 秒，失败才使用 taskkill 兜底。
  StrCpy $FailureStage "stop-running-app"
  StrCpy $RestartOnFailure "1"
  IfFileExists "$INSTDIR\GO-CLAW-Portable.exe" 0 go_claw_force_stop
    Exec '"$INSTDIR\GO-CLAW-Portable.exe" --portable-quit'
    ExecWait `powershell.exe -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -Command "Wait-Process -Name 'GO-CLAW-Portable' -Timeout 60 -ErrorAction SilentlyContinue"`
  go_claw_force_stop:
  ExecWait 'taskkill /F /IM GO-CLAW-Portable.exe'
  ExecWait 'taskkill /F /IM qwenpaw-backend.exe'
  ; 杀毒软件、子进程和可移动盘缓存可能稍晚释放句柄；备份宏还会重试。
  Sleep 3000
SectionEnd

Section "BackupOldVersion"
  StrCpy $FailureStage "backup"
  ; 同版本重复安装时先清掉旧备份点，避免 Rename 目标已存在而失败
  RMDir /r "$INSTDIR\updates\backup-$OldVersion"
  StrCpy $BackupStarted "1"

  ; 备份旧程序文件（白名单项；不存在的项自动跳过）
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "GO-CLAW-Portable.exe" "exe"
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "binaries" "binaries"
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "LICENSE" "license"
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "README-PORTABLE.zh-CN.txt" "readme"
SectionEnd

Section "InstallNewVersion"
  StrCpy $FailureStage "install"
  ; staging 已完整落盘；同一卷内 Rename 可快速切换，缩短应用停机时间。
  !insertmacro GO_CLAW_INSTALL_STAGED_ITEM "GO-CLAW-Portable.exe" "exe"
  !insertmacro GO_CLAW_INSTALL_STAGED_ITEM "binaries" "binaries"
  !insertmacro GO_CLAW_INSTALL_STAGED_ITEM "LICENSE" "license"
  !insertmacro GO_CLAW_INSTALL_STAGED_ITEM "README-PORTABLE.zh-CN.txt" "readme"
  RMDir /r "$INSTDIR\updates\staging-${GO_CLAW_VERSION}"

  ; 记录版本与更新历史
  FileOpen $0 "$INSTDIR\updates\version.txt" w
  FileWrite $0 "${GO_CLAW_VERSION}"
  FileClose $0

  FileOpen $0 "$INSTDIR\updates\last-update.json" w
  FileWrite $0 '{"version": "${GO_CLAW_VERSION}", "previous": "$OldVersion"}'
  FileClose $0
SectionEnd

Function .onInstSuccess
  Delete "$INSTDIR\updates\last-update-error.txt"
  Delete "$INSTDIR\updates\installing.lock"
  ; 安装完成自动重启 GO CLAW
  Exec '"$INSTDIR\GO-CLAW-Portable.exe"'
FunctionEnd

Function .onInstFailed
  ; 自动回滚已移动的旧程序，保证任何失败都至少能重新启动原版本。
  Call RestoreBackup
  RMDir /r "$INSTDIR\updates\staging-${GO_CLAW_VERSION}"
  Delete "$INSTDIR\updates\installing.lock"

  FileOpen $0 "$INSTDIR\updates\last-update-error.txt" w
  FileWrite $0 "version=${GO_CLAW_VERSION}$\r$\nstage=$FailureStage$\r$\n"
  FileClose $0

  StrCmp $RestartOnFailure "1" 0 go_claw_failed_done
  IfFileExists "$INSTDIR\GO-CLAW-Portable.exe" 0 go_claw_failed_done
    Exec '"$INSTDIR\GO-CLAW-Portable.exe"'
  go_claw_failed_done:
FunctionEnd

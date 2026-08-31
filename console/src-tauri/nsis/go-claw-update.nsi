; ============================================================================
; GO CLAW 便携版在线更新安装包
; 用法: GO-CLAW-Update-<ver>-setup.exe /S /D=<便携根目录>
; 契约（与 console/src-tauri/src/updates.rs 的 install_cached_windows 对齐）：
;   - 静默安装（/S），目标目录由 /D 传入（必须含 portable.json）
;   - 白名单替换：仅 GO-CLAW-Portable.exe / binaries / LICENSE / README
;   - 绝不触碰 data/secrets/logs/cache/backups/updates/GO-CLAW-Config/portable.json
;   - 替换前将旧程序文件备份到 updates\backup-<旧版本>\（回滚点）
;   - 备份完成后直接释放到便携根，避免额外目录导致 Windows MAX_PATH 超限
;   - 任一步失败均校验回滚；仅完整回滚后重启，禁止运行混合版本
;   - 安装期间写 updates\installing.lock，成功或完整回滚后删除
; ============================================================================

!ifndef GO_CLAW_VERSION
  !define GO_CLAW_VERSION "unknown"
!endif

!ifndef GO_CLAW_BACKUP_RETRIES
  !define GO_CLAW_BACKUP_RETRIES 30
!endif

!ifndef GO_CLAW_MAX_RELATIVE_PATH
  !define GO_CLAW_MAX_RELATIVE_PATH 220
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
Var RestoreFailed
Var RestoreStatus
Var QuitExitCode
Var UpdateLog
Var LogHandle
Var LockOwned
Var RootPathLength
Var FullPathLength

Function LogLine
  Exch $0
  ClearErrors
  FileOpen $LogHandle "$UpdateLog" a
  IfErrors go_claw_log_done
  FileWrite $LogHandle "$0$\r$\n"
  FileClose $LogHandle
  go_claw_log_done:
  Pop $0
FunctionEnd

!macro GO_CLAW_LOG line
  Push "${line}"
  Call LogLine
!macroend

!macro GO_CLAW_BACKUP_ITEM_RETRY path id
  IfFileExists "$INSTDIR\${path}" 0 go_claw_backup_done_${id}
  StrCpy $RetryCount 0
  go_claw_backup_retry_${id}:
    CreateDirectory "$INSTDIR\updates\backup-$OldVersion"
    ClearErrors
    Rename "$INSTDIR\${path}" "$INSTDIR\updates\backup-$OldVersion\${path}"
    IfErrors 0 go_claw_backup_done_${id}
    IntOp $RetryCount $RetryCount + 1
    IntCmp $RetryCount ${GO_CLAW_BACKUP_RETRIES} go_claw_backup_failed_${id} go_claw_backup_wait_${id} go_claw_backup_failed_${id}
  go_claw_backup_wait_${id}:
    Sleep 1000
    Goto go_claw_backup_retry_${id}
  go_claw_backup_failed_${id}:
    StrCpy $FailureStage "backup:${path}"
    !insertmacro GO_CLAW_LOG "version=${GO_CLAW_VERSION} stage=$FailureStage retries=$RetryCount"
    DetailPrint "backup failed after retries: ${path}"
    SetErrorLevel 1
    Abort "无法备份 ${path}，已自动恢复旧版本。请关闭仍在运行的 GO CLAW 相关进程后重试。"
  go_claw_backup_done_${id}:
!macroend

Function RestoreBackup
  StrCpy $RestoreFailed "0"
  StrCpy $RestoreStatus "not-needed"
  StrCmp $BackupStarted "1" 0 go_claw_restore_done
  StrCpy $RestoreStatus "ok"

  ; 回滚期间也保证 updater cwd 位于 updates，绝不占用 binaries。
  SetOutPath "$INSTDIR\updates"

  IfFileExists "$INSTDIR\updates\backup-$OldVersion\GO-CLAW-Portable.exe" 0 go_claw_restore_binaries
  IfFileExists "$INSTDIR\GO-CLAW-Portable.exe" 0 go_claw_restore_exe_move
    ClearErrors
    Delete "$INSTDIR\GO-CLAW-Portable.exe"
    IfErrors go_claw_restore_exe_failed
  go_claw_restore_exe_move:
    ClearErrors
    Rename "$INSTDIR\updates\backup-$OldVersion\GO-CLAW-Portable.exe" "$INSTDIR\GO-CLAW-Portable.exe"
    IfErrors go_claw_restore_exe_failed
    Goto go_claw_restore_binaries
  go_claw_restore_exe_failed:
    StrCpy $RestoreFailed "1"

  go_claw_restore_binaries:
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\binaries\*.*" 0 go_claw_restore_license
  IfFileExists "$INSTDIR\binaries\*.*" 0 go_claw_restore_binaries_move
    ClearErrors
    RMDir /r "$INSTDIR\binaries"
    IfErrors go_claw_restore_binaries_failed
  go_claw_restore_binaries_move:
    ClearErrors
    Rename "$INSTDIR\updates\backup-$OldVersion\binaries" "$INSTDIR\binaries"
    IfErrors go_claw_restore_binaries_failed
    Goto go_claw_restore_license
  go_claw_restore_binaries_failed:
    StrCpy $RestoreFailed "1"

  go_claw_restore_license:
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\LICENSE" 0 go_claw_restore_readme
  IfFileExists "$INSTDIR\LICENSE" 0 go_claw_restore_license_move
    ClearErrors
    Delete "$INSTDIR\LICENSE"
    IfErrors go_claw_restore_license_failed
  go_claw_restore_license_move:
    ClearErrors
    Rename "$INSTDIR\updates\backup-$OldVersion\LICENSE" "$INSTDIR\LICENSE"
    IfErrors go_claw_restore_license_failed
    Goto go_claw_restore_readme
  go_claw_restore_license_failed:
    StrCpy $RestoreFailed "1"

  go_claw_restore_readme:
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\README-PORTABLE.zh-CN.txt" 0 go_claw_restore_done
  IfFileExists "$INSTDIR\README-PORTABLE.zh-CN.txt" 0 go_claw_restore_readme_move
    ClearErrors
    Delete "$INSTDIR\README-PORTABLE.zh-CN.txt"
    IfErrors go_claw_restore_readme_failed
  go_claw_restore_readme_move:
    ClearErrors
    Rename "$INSTDIR\updates\backup-$OldVersion\README-PORTABLE.zh-CN.txt" "$INSTDIR\README-PORTABLE.zh-CN.txt"
    IfErrors go_claw_restore_readme_failed
    Goto go_claw_restore_done
  go_claw_restore_readme_failed:
    StrCpy $RestoreFailed "1"

  go_claw_restore_done:
  StrCmp $RestoreFailed "0" 0 go_claw_restore_mark_failed
    Goto go_claw_restore_return
  go_claw_restore_mark_failed:
    StrCpy $RestoreStatus "failed"
  go_claw_restore_return:
FunctionEnd

Function .onInit
  StrCpy $BackupStarted "0"
  StrCpy $RestartOnFailure "0"
  StrCpy $FailureStage "initialization"
  StrCpy $RestoreFailed "0"
  StrCpy $RestoreStatus "not-needed"
  StrCpy $LockOwned "0"

  ; /D= 传入的 $INSTDIR 必须是有效便携根（防参数错配误伤其它目录）
  IfFileExists "$INSTDIR\portable.json" go_claw_root_valid
    MessageBox MB_ICONSTOP|MB_OK "GO CLAW 更新失败：目标目录不是有效的 GO CLAW 便携目录（未找到 portable.json）。$\r$\n$\r$\n$INSTDIR"
    Abort
  go_claw_root_valid:

  ; 标准 Win32 路径上限含结尾 NUL 为 260。构建时传入 payload 的
  ; 真实最长相对路径，在关闭程序前拒绝必然失败的过深便携根。
  StrLen $RootPathLength $INSTDIR
  IntOp $FullPathLength $RootPathLength + 1
  IntOp $FullPathLength $FullPathLength + ${GO_CLAW_MAX_RELATIVE_PATH}
  IntCmp $FullPathLength 259 go_claw_path_safe go_claw_path_safe go_claw_path_too_long
  go_claw_path_too_long:
    MessageBox MB_ICONSTOP|MB_OK "当前便携目录过深，更新后的最长路径将达到 $FullPathLength 字符。请先把整个 GO CLAW 文件夹移动到盘符根目录后重试；程序文件尚未修改。"
    Abort
  go_claw_path_safe:

  ; Python 后端位于 binaries\qwenpaw-backend，并以该目录为 cwd。
  ; Windows 会把 cwd 继承给本更新器；若不先切走，本更新器会锁住
  ; 自己稍后要 Rename 的 binaries 目录。
  CreateDirectory "$INSTDIR\updates"
  ClearErrors
  SetOutPath "$INSTDIR\updates"
  IfErrors 0 go_claw_safe_workdir_ready
    StrCpy $FailureStage "set-workdir"
    SetErrorLevel 1
    Abort "无法进入 updates 工作目录，更新尚未修改程序文件。"
  go_claw_safe_workdir_ready:
  StrCpy $UpdateLog "$INSTDIR\updates\install.log"

  ; 读取旧版本号（无则 unknown）
  StrCpy $OldVersion "unknown"
  IfFileExists "$INSTDIR\updates\version.txt" 0 +6
    FileOpen $0 "$INSTDIR\updates\version.txt" r
    IfErrors +4
    FileRead $0 $1
    StrCpy $OldVersion $1
    FileClose $0

  ; 安装锁：存在即拒绝并发安装
  IfFileExists "$INSTDIR\updates\installing.lock" 0 go_claw_create_lock
    MessageBox MB_ICONSTOP|MB_OK "检测到未完成或正在进行的更新（installing.lock）。请保留现场并联系支持。"
    Abort
  go_claw_create_lock:
  ClearErrors
  FileOpen $0 "$INSTDIR\updates\installing.lock" w
  IfErrors go_claw_create_lock_failed
  StrCpy $LockOwned "1"
  FileWrite $0 "${GO_CLAW_VERSION}"
  IfErrors go_claw_create_lock_close_failed
  FileClose $0
  !insertmacro GO_CLAW_LOG "version=${GO_CLAW_VERSION} stage=initialized"
  Goto go_claw_lock_ready
  go_claw_create_lock_close_failed:
    FileClose $0
  go_claw_create_lock_failed:
    StrCpy $FailureStage "create-lock"
    SetErrorLevel 1
    Abort "无法创建更新锁，程序文件尚未修改。"
  go_claw_lock_ready:
FunctionEnd

Section "StopRunningApp"
  ; 优先复用便携客户端自身的退出协议，让后端完整执行 shutdown hooks 并
  ; 释放 binaries 下的 exe/dll。最多等待 60 秒，失败才使用 taskkill 兜底。
  StrCpy $FailureStage "stop-running-app"
  StrCpy $RestartOnFailure "1"
  IfFileExists "$INSTDIR\GO-CLAW-Portable.exe" 0 go_claw_force_stop
    ExecWait '"$INSTDIR\GO-CLAW-Portable.exe" --portable-quit' $QuitExitCode
    !insertmacro GO_CLAW_LOG "stage=portable-quit exitCode=$QuitExitCode"
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
  IfFileExists "$INSTDIR\updates\backup-$OldVersion\*.*" 0 go_claw_old_backup_removed
  ClearErrors
  RMDir /r "$INSTDIR\updates\backup-$OldVersion"
  IfErrors 0 go_claw_old_backup_removed
    StrCpy $FailureStage "cleanup-old-backup"
    SetErrorLevel 1
    Abort "无法清理旧备份目录，程序文件尚未修改。"
  go_claw_old_backup_removed:
  StrCpy $BackupStarted "1"

  ; 备份旧程序文件（白名单项；不存在的项自动跳过）
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "GO-CLAW-Portable.exe" "exe"
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "binaries" "binaries"
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "LICENSE" "license"
  !insertmacro GO_CLAW_BACKUP_ITEM_RETRY "README-PORTABLE.zh-CN.txt" "readme"
SectionEnd

Section "InstallNewVersion"
  ; 直接释放到原根目录，保持与现有可运行路径相同的长度。先前增加
  ; updates\staging-<版本> 后，torch 的三个深层许可证路径达到 264-267
  ; 字符并触发 NSIS/Win32 MAX_PATH 写入失败。
  StrCpy $FailureStage "install-payload"
  SetOutPath "$INSTDIR"
  ClearErrors
  File /r "payload\*.*"
  IfErrors 0 go_claw_payload_installed
    SetErrorLevel 1
    Abort "更新文件释放失败，已自动恢复旧版本。"
  go_claw_payload_installed:

  ; 记录版本与更新历史；任一写入失败都进入事务回滚。
  StrCpy $FailureStage "write-version"
  ClearErrors
  FileOpen $0 "$INSTDIR\updates\version.txt" w
  IfErrors go_claw_metadata_failed
  FileWrite $0 "${GO_CLAW_VERSION}"
  IfErrors go_claw_metadata_close_failed
  FileClose $0

  StrCpy $FailureStage "write-history"
  ClearErrors
  FileOpen $0 "$INSTDIR\updates\last-update.json" w
  IfErrors go_claw_metadata_failed
  FileWrite $0 '{"version": "${GO_CLAW_VERSION}", "previous": "$OldVersion"}'
  IfErrors go_claw_metadata_close_failed
  FileClose $0
  Goto go_claw_metadata_done

  go_claw_metadata_close_failed:
    FileClose $0
  go_claw_metadata_failed:
    SetErrorLevel 1
    Abort "无法写入更新版本记录，已自动恢复旧版本。"
  go_claw_metadata_done:
SectionEnd

Function .onInstSuccess
  Delete "$INSTDIR\updates\last-update-error.txt"
  Delete "$INSTDIR\updates\installing.lock"
  ; 安装完成自动重启 GO CLAW
  ClearErrors
  Exec '"$INSTDIR\GO-CLAW-Portable.exe"'
  IfErrors 0 go_claw_restart_succeeded
    FileOpen $0 "$INSTDIR\updates\last-update-error.txt" w
    FileWrite $0 "version=${GO_CLAW_VERSION}$\r$\nstage=restart-new$\r$\nrestore=not-needed$\r$\n"
    FileClose $0
    !insertmacro GO_CLAW_LOG "version=${GO_CLAW_VERSION} stage=restart-new restore=not-needed"
  go_claw_restart_succeeded:
FunctionEnd

Function .onInstFailed
  ; 自动回滚已移动的旧程序，保证任何失败都至少能重新启动原版本。
  Call RestoreBackup

  FileOpen $0 "$INSTDIR\updates\last-update-error.txt" w
  FileWrite $0 "version=${GO_CLAW_VERSION}$\r$\nstage=$FailureStage$\r$\nrestore=$RestoreStatus$\r$\n"
  FileClose $0
  !insertmacro GO_CLAW_LOG "version=${GO_CLAW_VERSION} stage=$FailureStage restore=$RestoreStatus"

  StrCmp $RestoreFailed "0" go_claw_restore_ok go_claw_restore_failed
  go_claw_restore_ok:
    StrCmp $LockOwned "1" 0 go_claw_restart_after_restore
      Delete "$INSTDIR\updates\installing.lock"
    go_claw_restart_after_restore:
    StrCmp $RestartOnFailure "1" 0 go_claw_failed_done
    IfFileExists "$INSTDIR\GO-CLAW-Portable.exe" 0 go_claw_failed_done
      Exec '"$INSTDIR\GO-CLAW-Portable.exe"'
    Goto go_claw_failed_done

  go_claw_restore_failed:
    ; 保留 installing.lock；PortableState::prepare 会阻止混合版本启动。
    SetErrorLevel 2

  go_claw_failed_done:
FunctionEnd

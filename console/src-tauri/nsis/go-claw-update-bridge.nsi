; GO CLAW v2 legacy-to-A/B bridge.
; The old client verifies this executable with its existing updater key.  This
; wrapper embeds the independent Rust engine and never contains a full payload.

!ifndef GO_CLAW_VERSION
  !error "GO_CLAW_VERSION is required"
!endif
!ifndef GO_CLAW_INDEX_URL
  !error "GO_CLAW_INDEX_URL is required"
!endif
!ifndef GO_CLAW_TARGET_MANIFEST
  !error "GO_CLAW_TARGET_MANIFEST is required"
!endif
!ifndef GO_CLAW_ENGINE
  !error "GO_CLAW_ENGINE is required"
!endif

!include LogicLib.nsh
!include nsDialogs.nsh
!include WinMessages.nsh

Name "GO CLAW Update ${GO_CLAW_VERSION}"
OutFile "GO-CLAW-Update-${GO_CLAW_VERSION}-setup.exe"
Unicode true
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails hide
AutoCloseWindow true

Var BridgeDialog
Var BridgeLabel
Var BridgeProgress
Var BridgeEngine
Var BridgeResult
Var BridgeTimerActive

!ifdef GO_CLAW_BRIDGE_HEADLESS
  SilentInstall silent
!else
  SilentInstall normal
  Page custom BridgePage
!endif

Function ValidatePortableRoot
  IfFileExists "$INSTDIR\portable.json" root_valid
    MessageBox MB_ICONSTOP|MB_OK "GO CLAW 更新失败：目标目录不是有效的 GO CLAW 便携目录（未找到 portable.json）。"
    SetErrorLevel 1
    Abort
  root_valid:
  CreateDirectory "$INSTDIR\updates\bridge"
  StrCpy $BridgeResult "$INSTDIR\updates\bridge\result.txt"
  Delete "$BridgeResult"
FunctionEnd

Function .onInit
  !ifndef GO_CLAW_BRIDGE_HEADLESS
    ; Legacy Tauri invokes /S.  The bridge deliberately restores its one-page
    ; progress UI because the stopped web UI cannot report the A/B transaction.
    SetSilent normal
  !endif
  Call ValidatePortableRoot
  InitPluginsDir
  StrCpy $BridgeEngine "$PLUGINSDIR\go-claw-update-engine.exe"
  SetOutPath "$PLUGINSDIR"
  File /oname=go-claw-update-engine.exe "${GO_CLAW_ENGINE}"
FunctionEnd

!ifndef GO_CLAW_BRIDGE_HEADLESS
Function BridgePage
  nsDialogs::Create 1018
  Pop $BridgeDialog
  ${If} $BridgeDialog == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 8u 100% 24u "正在安全下载并安装 GO CLAW ${GO_CLAW_VERSION}…"
  Pop $BridgeLabel
  ${NSD_CreateProgressBar} 0 42u 100% 12u ""
  Pop $BridgeProgress
  SendMessage $BridgeProgress ${PBM_SETRANGE32} 0 100
  SendMessage $BridgeProgress ${PBM_SETPOS} 0 0
  GetDlgItem $0 $HWNDPARENT 1
  EnableWindow $0 0
  GetDlgItem $0 $HWNDPARENT 2
  EnableWindow $0 0
  StrCpy $BridgeTimerActive "1"
  ${NSD_CreateTimer} BridgePoll 500
  Exec '"$BridgeEngine" bridge --root "$INSTDIR" --index-url "${GO_CLAW_INDEX_URL}" --target-version "${GO_CLAW_VERSION}" --target-manifest "${GO_CLAW_TARGET_MANIFEST}"'
  nsDialogs::Show
FunctionEnd

Function BridgePoll
  nsExec::ExecToStack /TIMEOUT=10000 '"$BridgeEngine" bridge-progress --root "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    SendMessage $BridgeProgress ${PBM_SETPOS} $1 0
  ${EndIf}
  IfFileExists "$BridgeResult" bridge_finished bridge_poll_done
  bridge_finished:
    FileOpen $2 "$BridgeResult" r
    FileRead $2 $3
    FileRead $2 $4
    FileClose $2
    ${NSD_KillTimer} BridgePoll
    StrCpy $BridgeTimerActive "0"
    ${If} $3 == "0$\r$\n"
    ${OrIf} $3 == "0$\n"
      SendMessage $BridgeProgress ${PBM_SETPOS} 100 0
      ${NSD_SetText} $BridgeLabel "GO CLAW ${GO_CLAW_VERSION} 已安装完成，正在启动。"
      Sleep 400
      Quit
    ${Else}
      ${NSD_SetText} $BridgeLabel "更新失败（$4）。程序数据未被更新器覆盖，请保留 updates 日志。"
      MessageBox MB_ICONSTOP|MB_OK "GO CLAW 更新失败：$4$\r$\n请保留 updates 目录并联系支持。"
      SetErrorLevel 1
      GetDlgItem $5 $HWNDPARENT 2
      EnableWindow $5 1
    ${EndIf}
  bridge_poll_done:
FunctionEnd

Function .onGUIEnd
  ${If} $BridgeTimerActive == "1"
    ${NSD_KillTimer} BridgePoll
  ${EndIf}
FunctionEnd
!endif

Section "GO CLAW A/B Bridge"
  !ifdef GO_CLAW_BRIDGE_HEADLESS
    ExecWait '"$BridgeEngine" bridge --root "$INSTDIR" --index-url "${GO_CLAW_INDEX_URL}" --target-version "${GO_CLAW_VERSION}" --target-manifest "${GO_CLAW_TARGET_MANIFEST}"' $0
    SetErrorLevel $0
  !endif
SectionEnd

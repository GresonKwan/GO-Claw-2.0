@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0GO-CLAW-Portable.exe" (
  echo Put this file next to GO-CLAW-Portable.exe, then run it again.
  pause
  exit /b 1
)

rem A running portable single instance keeps its original environment. Stop it
rem before setting the staging endpoint so the new backend inherits this value.
taskkill /F /T /IM GO-CLAW-Portable.exe >nul 2>&1
taskkill /F /T /IM qwenpaw-backend.exe >nul 2>&1
timeout /t 2 /nobreak >nul

set "GO_CLAW_UPDATE_ENDPOINTS=https://goclaw.host:8443/updates-staging/2.1.1/latest.json"
start "" /D "%~dp0" "%~dp0GO-CLAW-Portable.exe"

timeout /t 10 /nobreak >nul
tasklist /FI "IMAGENAME eq GO-CLAW-Portable.exe" | find /I "GO-CLAW-Portable.exe" >nul
if errorlevel 1 (
  echo GO CLAW failed to start. Check the logs directory next to the EXE.
  pause
  exit /b 1
)

echo GO CLAW started with the v2.1.1 staging update endpoint.
exit /b 0

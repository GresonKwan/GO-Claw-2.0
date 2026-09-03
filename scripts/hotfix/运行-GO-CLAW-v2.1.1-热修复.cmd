@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GO-CLAW-v2.1.1-Hotfix.ps1" -RepairFailedEmployees
echo.
pause

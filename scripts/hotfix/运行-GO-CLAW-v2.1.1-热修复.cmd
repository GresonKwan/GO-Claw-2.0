@echo off
chcp 65001 >nul
set "PRODUCT_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GO-CLAW-v2.1.1-Hotfix.ps1" -ProductRoot "%PRODUCT_ROOT%" -RepairFailedEmployees
echo.
pause

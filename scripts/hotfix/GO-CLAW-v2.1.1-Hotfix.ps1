[CmdletBinding()]
param(
    [string]$ProductRoot = $PSScriptRoot,
    [switch]$RepairFailedEmployees,
    [switch]$RunCheckDisk,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$BuiltInEmployees = @(
    "marketing-growth",
    "content-production",
    "data-processing",
    "business-analysis"
)

function Write-Step([string]$Message) {
    Write-Host "[GO CLAW HOTFIX] $Message" -ForegroundColor Cyan
}

function Get-NormalizedPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Test-IsChildPath([string]$Path, [string]$Parent) {
    $child = (Get-NormalizedPath $Path) + '\'
    $root = (Get-NormalizedPath $Parent) + '\'
    return $child.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
}

function Get-AgentStates([string]$Root) {
    $portFile = Join-Path $Root "data\desktop_port"
    if (-not (Test-Path -LiteralPath $portFile)) {
        return @()
    }
    try {
        $port = [int](Get-Content -LiteralPath $portFile -Raw).Trim()
        $response = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$port/api/agents" `
            -TimeoutSec 10
        return @($response.agents)
    }
    catch {
        return @()
    }
}

function Stop-GoClaw([string]$Root, [string]$ExePath) {
    $running = @(
        Get-Process -Name "GO-CLAW-Portable", "qwenpaw-desktop", `
            "qwenpaw-backend" -ErrorAction SilentlyContinue |
            Where-Object {
                try {
                    $_.Path -and (Test-IsChildPath $_.Path $Root)
                }
                catch { $false }
            }
    )
    if ($running.Count -eq 0) {
        Write-Step "GO CLAW 当前未运行。"
        return
    }
    Write-Step "正在正常退出 GO CLAW..."
    Start-Process -FilePath $ExePath -ArgumentList "--portable-quit" `
        -WorkingDirectory $Root -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 500
        $running = @(
            Get-Process -Name "GO-CLAW-Portable", "qwenpaw-desktop", `
                "qwenpaw-backend" -ErrorAction SilentlyContinue |
                Where-Object {
                    try {
                        $_.Path -and (Test-IsChildPath $_.Path $Root)
                    }
                    catch { $false }
                }
        )
    } while ($running.Count -gt 0 -and (Get-Date) -lt $deadline)
    if ($running.Count -gt 0) {
        throw "GO CLAW 未能在 90 秒内正常退出，请关闭程序后重试。"
    }
}

function Invoke-DiskRepair([string]$Root) {
    $driveRoot = [IO.Path]::GetPathRoot((Get-NormalizedPath $Root))
    if (-not $driveRoot) {
        throw "无法确定产品盘盘符。"
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if (-not $isAdmin) {
        throw "磁盘修复需要管理员权限，请右键 PowerShell 选择[以管理员身份运行]后重试。"
    }
    Write-Step "正在对 $driveRoot 执行 CHKDSK /F；请勿拔出产品盘。"
    & "$env:SystemRoot\System32\chkdsk.exe" $driveRoot /F
    if ($LASTEXITCODE -gt 1) {
        throw "CHKDSK 失败，退出码：$LASTEXITCODE"
    }
}

function Install-MediaPluginHotfix(
    [string]$Root,
    [string]$BackupRoot
) {
    $bundleRoot = Join-Path $Root (
        "binaries\qwenpaw-backend\_internal\qwenpaw\bundled_plugins"
    )
    $pluginsRoot = Join-Path $Root "data\plugins"
    $backupPlugins = Join-Path $BackupRoot "plugins"
    $node = Join-Path $Root "binaries\node-runtime\node.exe"
    $helper = Join-Path $PSScriptRoot "GO-CLAW-v2.1.1-Hotfix.js"
    New-Item -ItemType Directory -Path $pluginsRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $backupPlugins -Force | Out-Null

    foreach ($directory in @("qwen-image", "wan27")) {
        $source = Join-Path $bundleRoot $directory
        $target = Join-Path $pluginsRoot $directory
        if (-not (Test-Path -LiteralPath (Join-Path $source "plugin.json"))) {
            throw "安装包内缺少媒体插件：$source"
        }
        if (Test-Path -LiteralPath $target) {
            Move-Item -LiteralPath $target -Destination $backupPlugins
        }
        Copy-Item -LiteralPath $source -Destination $target -Recurse

        $manifestPath = Join-Path $target "plugin.json"
        & $node $helper patch-manifest $manifestPath
        if ($LASTEXITCODE -ne 0) {
            throw "无法更新媒体插件兼容范围：$manifestPath"
        }
    }
}

function Repair-EmployeeProfiles(
    [string]$Root,
    [string]$BackupRoot,
    [string[]]$EmployeeIds
) {
    if ($EmployeeIds.Count -eq 0) {
        return
    }
    $node = Join-Path $Root "binaries\node-runtime\node.exe"
    $helper = Join-Path $PSScriptRoot "GO-CLAW-v2.1.1-Hotfix.js"
    if (-not (Test-Path -LiteralPath $node)) {
        throw "产品包缺少 Node runtime：$node"
    }
    if (-not (Test-Path -LiteralPath $helper)) {
        throw "热修复包缺少辅助文件：$helper"
    }
    & $node $helper repair $Root $BackupRoot ($EmployeeIds -join ",")
    if ($LASTEXITCODE -ne 0) {
        throw "数字员工配置修复失败，Node 退出码：$LASTEXITCODE"
    }
}

function Start-And-Verify(
    [string]$Root,
    [string]$ExePath,
    [string[]]$RepairedEmployees
) {
    Write-Step "正在启动并验证热修复..."
    $portFile = Join-Path $Root "data\desktop_port"
    Start-Process -FilePath $ExePath -WorkingDirectory $Root | Out-Null
    $deadline = (Get-Date).AddSeconds(300)
    $port = $null
    $version = $null
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $portFile) {
            try {
                $port = [int](Get-Content -LiteralPath $portFile -Raw).Trim()
                $version = Invoke-RestMethod `
                    -Uri "http://127.0.0.1:$port/api/version" `
                    -TimeoutSec 5
                if ($version.version -eq "2.1.1") { break }
            }
            catch { }
        }
        Start-Sleep -Milliseconds 500
    }
    if ($null -eq $version) {
        throw "热修复后 GO CLAW 未能在 300 秒内启动。"
    }
    Start-Sleep -Seconds 5
    $plugins = @(
        Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/plugins" `
            -TimeoutSec 15
    )
    foreach ($pluginId in @("qwen-image-tool", "wan27-tool")) {
        $plugin = $plugins | Where-Object { $_.id -eq $pluginId } |
            Select-Object -First 1
        if ($null -eq $plugin -or $plugin.loaded -ne $true -or
            $plugin.enabled -ne $true) {
            throw "媒体插件未正常启用：$pluginId"
        }
    }
    if ($RepairedEmployees.Count -gt 0) {
        $agents = (Invoke-RestMethod `
            -Uri "http://127.0.0.1:$port/api/agents" `
            -TimeoutSec 15).agents
        foreach ($employeeId in $RepairedEmployees) {
            $agent = $agents | Where-Object { $_.id -eq $employeeId } |
                Select-Object -First 1
            if ($null -eq $agent -or $agent.startup_status -ne "running") {
                throw "数字员工未恢复运行：$employeeId"
            }
        }
    }
}

$ProductRoot = Get-NormalizedPath $ProductRoot
$exe = Join-Path $ProductRoot "GO-CLAW-Portable.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "未找到 GO-CLAW-Portable.exe：$ProductRoot"
}
$fileVersion = (Get-Item -LiteralPath $exe).VersionInfo.FileVersion
if ($fileVersion -ne "2.1.1") {
    throw "此热修复仅适用于 v2.1.1，当前文件版本：$fileVersion"
}

$states = @(Get-AgentStates $ProductRoot)
$failedEmployees = @(
    $states |
        Where-Object {
            $BuiltInEmployees -contains $_.id -and
            $_.startup_status -eq "failed"
        } |
        ForEach-Object { $_.id }
)

Stop-GoClaw $ProductRoot $exe

$configPath = Join-Path $ProductRoot "data\config.json"
if ($RepairFailedEmployees -and (Test-Path -LiteralPath $configPath)) {
    $node = Join-Path $ProductRoot "binaries\node-runtime\node.exe"
    $helper = Join-Path $PSScriptRoot "GO-CLAW-v2.1.1-Hotfix.js"
    $probe = & $node $helper probe $ProductRoot
    if ($LASTEXITCODE -ne 0) {
        throw "无法检查数字员工 workspace。"
    }
    foreach ($probedId in @($probe)) {
        if ($BuiltInEmployees -contains $probedId) {
            $failedEmployees += $probedId
        }
    }
    $failedEmployees = @($failedEmployees | Select-Object -Unique)
}

if ($RunCheckDisk) {
    Invoke-DiskRepair $ProductRoot
}
elseif ($RepairFailedEmployees -and $failedEmployees.Count -gt 0) {
    Write-Warning (
        "检测到失败或不可读的内置数字员工：" +
        ($failedEmployees -join ", ") +
        "。如果下方修复因[文件或目录损坏]失败，请以管理员身份加 " +
        "-RunCheckDisk 参数重新运行。"
    )
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $ProductRoot "data\hotfix-backups\$timestamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

Install-MediaPluginHotfix $ProductRoot $backupRoot
if ($RepairFailedEmployees) {
    Repair-EmployeeProfiles $ProductRoot $backupRoot $failedEmployees
}

if (-not $NoRestart) {
    Start-And-Verify $ProductRoot $exe $failedEmployees
}

Write-Host ""
Write-Host "热修复成功。备份位于：$backupRoot" -ForegroundColor Green
Write-Host "媒体插件：qwen-image-tool / wan27-tool 已启用。" -ForegroundColor Green
if ($failedEmployees.Count -gt 0) {
    Write-Host (
        "已重建数字员工：" + ($failedEmployees -join ", ")
    ) -ForegroundColor Green
}

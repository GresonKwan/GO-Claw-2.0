[CmdletBinding()]
param(
    [string]$ProductRoot = $PSScriptRoot,
    [switch]$RepairFailedEmployees,
    [switch]$RunCheckDisk,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

# Windows PowerShell 5.1 can evaluate $PSScriptRoot as empty while binding a
# default parameter value. Resolve it again after parameter binding.
if ([string]::IsNullOrWhiteSpace($ProductRoot)) {
    $ProductRoot = $PSScriptRoot
}

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
    # Elevated CMD launchers can accidentally preserve quotes around a drive
    # root. Normalize them defensively before calling GetFullPath.
    $cleanPath = $Path.Trim().Trim('"')
    return [IO.Path]::GetFullPath($cleanPath).TrimEnd('\')
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
    $deadline = (Get-Date).AddSeconds(30)
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
        Write-Warning "正常退出超时，将仅强制结束当前产品目录内的 GO CLAW 进程。"
        $running | Stop-Process -Force -ErrorAction Stop
        Start-Sleep -Seconds 2
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
        if ($running.Count -gt 0) {
            throw "无法结束当前产品目录内的 GO CLAW 进程。"
        }
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
    $pluginDeadline = (Get-Date).AddSeconds(90)
    $pluginsReady = $false
    do {
        try {
            $plugins = @(
                Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/plugins" `
                    -TimeoutSec 15
            )
            $pluginsReady = $true
            foreach ($pluginId in @("qwen-image-tool", "wan27-tool")) {
                $plugin = $plugins | Where-Object { $_.id -eq $pluginId } |
                    Select-Object -First 1
                if ($null -eq $plugin -or $plugin.loaded -ne $true -or
                    $plugin.enabled -ne $true) {
                    $pluginsReady = $false
                    break
                }
            }
        }
        catch {
            $pluginsReady = $false
        }
        if (-not $pluginsReady) { Start-Sleep -Seconds 1 }
    } while (-not $pluginsReady -and (Get-Date) -lt $pluginDeadline)
    if (-not $pluginsReady) {
        throw "媒体插件未在 90 秒内正常启用。"
    }
    if ($RepairedEmployees.Count -gt 0) {
        $agentDeadline = (Get-Date).AddSeconds(120)
        $agentsReady = $false
        do {
            $agents = (Invoke-RestMethod `
                -Uri "http://127.0.0.1:$port/api/agents" `
                -TimeoutSec 15).agents
            $agentsReady = $true
            foreach ($employeeId in $RepairedEmployees) {
                $agent = $agents | Where-Object { $_.id -eq $employeeId } |
                    Select-Object -First 1
                if ($null -eq $agent -or $agent.startup_status -ne "running") {
                    $agentsReady = $false
                    break
                }
            }
            if (-not $agentsReady) { Start-Sleep -Seconds 1 }
        } while (-not $agentsReady -and (Get-Date) -lt $agentDeadline)
        if (-not $agentsReady) {
            throw "数字员工未在 120 秒内恢复运行。"
        }
    }
    return $port
}

function Repair-EmployeesViaApi(
    [string]$Root,
    [string]$ExePath,
    [string]$BackupRoot,
    [int]$Port
) {
    $agents = @(
        (Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/agents" `
            -TimeoutSec 15).agents
    )
    $failedAgents = @(
        $agents | Where-Object {
            $BuiltInEmployees -contains $_.id -and
            $_.startup_status -eq "failed"
        }
    )
    if ($failedAgents.Count -eq 0) {
        Write-Step "应用已容错读取配置，未发现失败的内置数字员工。"
        return
    }

    $workspacesRoot = Join-Path $Root "data\workspaces"
    $backupWorkspaces = Join-Path $BackupRoot "workspaces"
    New-Item -ItemType Directory -Path $backupWorkspaces -Force | Out-Null
    $targets = @()
    foreach ($agent in $failedAgents) {
        $workspace = Get-NormalizedPath ([string]$agent.workspace_dir)
        if (-not (Test-IsChildPath $workspace $workspacesRoot)) {
            throw "拒绝移动产品 data 目录外的 workspace：$workspace"
        }
        $targets += [PSCustomObject]@{
            Id = [string]$agent.id
            Source = $workspace
            Backup = Join-Path $backupWorkspaces ([string]$agent.id)
        }
    }

    Stop-GoClaw $Root $ExePath
    $moved = @()
    try {
        foreach ($target in $targets) {
            if (Test-Path -LiteralPath $target.Source) {
                Move-Item -LiteralPath $target.Source `
                    -Destination $target.Backup -ErrorAction Stop
                $moved += $target
            }
        }
    }
    catch {
        foreach ($target in @($moved)) {
            if (Test-Path -LiteralPath $target.Backup) {
                Move-Item -LiteralPath $target.Backup `
                    -Destination $target.Source -ErrorAction SilentlyContinue
            }
        }
        Start-Process -FilePath $ExePath -WorkingDirectory $Root | Out-Null
        throw "移动损坏 workspace 失败；已尝试回滚并重启。请先运行 CHKDSK。"
    }

    $repairPort = Start-And-Verify $Root $ExePath @()
    $configPath = Join-Path $Root "data\config.json"
    Copy-Item -LiteralPath $configPath `
        -Destination (Join-Path $BackupRoot "config.json.before-api-repair") `
        -Force
    foreach ($target in $targets) {
        Invoke-RestMethod -Method Delete `
            -Uri "http://127.0.0.1:$repairPort/api/agents/$($target.Id)" `
            -TimeoutSec 30 | Out-Null
    }
    Stop-GoClaw $Root $ExePath

    $marker = Join-Path $Root "data\.migrations\go-claw-presets-v1.json"
    if (Test-Path -LiteralPath $marker) {
        Move-Item -LiteralPath $marker `
            -Destination (Join-Path $BackupRoot "go-claw-presets-v1.json")
    }
    $ids = @($targets | ForEach-Object { $_.Id })
    Start-And-Verify $Root $ExePath $ids | Out-Null
    $ids
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

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $ProductRoot "data\hotfix-backups\$timestamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$configPath = Join-Path $ProductRoot "data\config.json"
$deferredEmployeeRepair = $false
if ($RepairFailedEmployees -and (Test-Path -LiteralPath $configPath)) {
    $node = Join-Path $ProductRoot "binaries\node-runtime\node.exe"
    $helper = Join-Path $PSScriptRoot "GO-CLAW-v2.1.1-Hotfix.js"
    $probeError = Join-Path $backupRoot "workspace-probe-error.txt"
    $previousErrorAction = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 promotes native stderr to a terminating
        # NativeCommandError when the script-wide preference is Stop.
        $ErrorActionPreference = "Continue"
        $probe = & $node $helper probe $ProductRoot 2> $probeError
        $probeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($probeExitCode -ne 0) {
        $deferredEmployeeRepair = $true
        Write-Warning (
            "根配置无法由严格探测器解析；将先启动 GO CLAW，" +
            "再通过本机 API 安全识别并重建失败员工。"
        )
    }
    else {
        foreach ($probedId in @($probe)) {
            if ($BuiltInEmployees -contains $probedId) {
                $failedEmployees += $probedId
            }
        }
        $failedEmployees = @($failedEmployees | Select-Object -Unique)
    }
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

Install-MediaPluginHotfix $ProductRoot $backupRoot
if ($RepairFailedEmployees -and -not $deferredEmployeeRepair) {
    Repair-EmployeeProfiles $ProductRoot $backupRoot $failedEmployees
}

if (-not $NoRestart) {
    if ($deferredEmployeeRepair) {
        $port = Start-And-Verify $ProductRoot $exe @()
        $failedEmployees = @(
            Repair-EmployeesViaApi $ProductRoot $exe $backupRoot $port
        )
    }
    else {
        Start-And-Verify $ProductRoot $exe $failedEmployees | Out-Null
    }
}

Write-Host ""
Write-Host "热修复成功。备份位于：$backupRoot" -ForegroundColor Green
Write-Host "媒体插件：qwen-image-tool / wan27-tool 已启用。" -ForegroundColor Green
if ($failedEmployees.Count -gt 0) {
    Write-Host (
        "已重建数字员工：" + ($failedEmployees -join ", ")
    ) -ForegroundColor Green
}

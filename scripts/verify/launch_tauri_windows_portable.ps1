# Verify the staged ZIP as a user would: extract, launch, relocate, relaunch.
# Exports BASE_URL and PORTABLE_ROOT for the following API contract step.
$ErrorActionPreference = "Stop"

function Wait-DesktopReady {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][int]$ExpectedPort,
        [int]$TimeoutSeconds = 120
    )
    $expectedUrl = "http://127.0.0.1:$ExpectedPort/console"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $Path) {
            try {
                $probe = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
                if ($probe.schemaVersion -eq 1 -and
                    $probe.phase -eq "desktopActive" -and
                    [int]$probe.backendPort -eq $ExpectedPort -and
                    $probe.consoleUrl -eq $expectedUrl) {
                    Write-Host "Native desktop readiness confirmed: $expectedUrl"
                    return
                }
            } catch {}
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Portable React content did not report native desktop readiness: $Path"
}

function Save-DesktopScreenshot {
    param([Parameter(Mandatory = $true)][string]$Name)
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $screenshotDir = Join-Path $env:RUNNER_TEMP "verify-screenshots"
    New-Item -ItemType Directory -Force -Path $screenshotDir | Out-Null
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $screenshot = Join-Path $screenshotDir $Name
        $bitmap.Save($screenshot, [System.Drawing.Imaging.ImageFormat]::Png)
        Write-Host "Captured $screenshot"
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Export-PortableLogs {
    param([Parameter(Mandatory = $true)][string]$Root)
    $destination = Join-Path $env:RUNNER_TEMP "portable-verify-logs"
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    $sourceLogs = Join-Path $Root "logs"
    if (Test-Path -LiteralPath $sourceLogs) {
        Copy-Item -LiteralPath $sourceLogs -Destination $destination -Recurse -Force `
            -ErrorAction SilentlyContinue
    }
    $desktopLog = Join-Path $Root "data\desktop.log"
    if (Test-Path -LiteralPath $desktopLog) {
        Copy-Item -LiteralPath $desktopLog -Destination $destination -Force `
            -ErrorAction SilentlyContinue
    }
}

function Wait-NewWebView2ProcessesExit {
    param(
        [int[]]$BaselinePids = @(),
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $remaining = @(Get-Process -Name "msedgewebview2" `
            -ErrorAction SilentlyContinue | Where-Object {
                $BaselinePids -notcontains $_.Id
            })
        if ($remaining.Count -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }
    $remainingPids = @(Get-Process -Name "msedgewebview2" `
        -ErrorAction SilentlyContinue | Where-Object {
            $BaselinePids -notcontains $_.Id
        } | ForEach-Object { $_.Id })
    throw "Portable WebView2 processes did not exit after shell shutdown: $($remainingPids -join ',')"
}

function Wait-PortableReady {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [int]$TimeoutSeconds = 120
    )
    $portFile = Join-Path $Root "data\desktop_port"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $portFile) {
            $port = (Get-Content $portFile -Raw -ErrorAction SilentlyContinue).Trim()
            if ($port -match '^\d+$') {
                try {
                    $response = Invoke-WebRequest `
                        -Uri "http://127.0.0.1:$port/api/healthz" `
                        -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
                    if ($response.StatusCode -eq 200) {
                        return [int]$port
                    }
                } catch {}
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "Portable backend did not become healthy within $TimeoutSeconds seconds: $Root"
}

function Get-BackendProcess {
    $processes = @(Get-Process -Name "qwenpaw-backend" -ErrorAction SilentlyContinue)
    if ($processes.Count -ne 1) {
        throw "Expected exactly one qwenpaw-backend process, found $($processes.Count)"
    }
    return $processes[0]
}

function Stop-PortableGracefully {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [int]$TimeoutSeconds = 70
    )
    $control = Start-Process -FilePath $Exe -ArgumentList "--portable-quit" -PassThru
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $shell = Get-Process -Name "GO-CLAW-Portable", "qwenpaw-desktop" `
            -ErrorAction SilentlyContinue
        $backend = Get-Process -Name "qwenpaw-backend" -ErrorAction SilentlyContinue
        if (-not $shell -and -not $backend) {
            if (-not $control.HasExited) { $control.WaitForExit(5000) | Out-Null }
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Portable shell/backend did not exit gracefully within $TimeoutSeconds seconds"
}

function Assert-PortableOutputs {
    param([Parameter(Mandatory = $true)][string]$Root)
    @(
        "data\config.json",
        "data\desktop_port",
        "data\desktop.log",
        "data\.portable-location.json"
    ) | ForEach-Object {
        $path = Join-Path $Root $_
        if (-not (Test-Path $path)) { throw "Portable output missing: $path" }
    }
    $desktopLog = Get-ChildItem (Join-Path $Root "logs") `
        -Filter "qwenpaw-desktop*.log" -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $desktopLog) { throw "Portable shell log missing under $Root\logs" }
    if (-not (Test-Path (Join-Path $Root "secrets"))) {
        throw "Portable secrets directory missing"
    }
}

function Get-DriveLetter {
    param([string[]]$Preferred)
    $used = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Name })
    foreach ($letter in $Preferred) {
        if ($used -notcontains $letter) { return $letter }
    }
    throw "No free drive letter available from: $($Preferred -join ', ')"
}

$archive = Get-ChildItem "dist\GO-CLAW-Portable-*-Windows-x64.zip" |
    Select-Object -First 1
if (-not $archive) { throw "Portable ZIP not found in dist/" }
$checksum = "$($archive.FullName).sha256"
if (-not (Test-Path $checksum)) { throw "Portable SHA-256 file missing: $checksum" }
$expectedHash = ((Get-Content $checksum -Raw).Trim() -split '\s+')[0]
$actualHash = (Get-FileHash $archive.FullName -Algorithm SHA256).Hash
if ($expectedHash -ne $actualHash) { throw "Portable ZIP SHA-256 mismatch" }

$profileData = Join-Path $env:USERPROFILE ".qwenpaw"
$portableLocalData = Join-Path $env:LOCALAPPDATA "io.agentscope.qwenpaw.portable"
$installedLocalData = Join-Path $env:LOCALAPPDATA "io.agentscope.qwenpaw.desktop"
$profileExistedBefore = Test-Path $profileData
$portableLocalExistedBefore = Test-Path $portableLocalData
$installedLocalExistedBefore = Test-Path $installedLocalData
$baselineWebViewPids = @(Get-Process -Name "msedgewebview2" `
    -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })

$testBase = Join-Path $env:RUNNER_TEMP "qwenpaw-portable-verify"
if (Test-Path $testBase) { Remove-Item -Recurse -Force $testBase }
New-Item -ItemType Directory -Force -Path $testBase | Out-Null
Expand-Archive -Path $archive.FullName -DestinationPath $testBase -Force
$extracted = Get-ChildItem $testBase -Directory | Select-Object -First 1
if (-not $extracted) { throw "Portable archive did not contain a root directory" }

$firstBacking = Join-Path $env:RUNNER_TEMP "GO CLAW 首次盘"
$secondBacking = Join-Path $env:RUNNER_TEMP "GO CLAW 中文移动盘"
foreach ($path in @($firstBacking, $secondBacking)) {
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}
Move-Item $extracted.FullName $firstBacking

$firstLetter = Get-DriveLetter @("P", "Q", "S")
$secondLetter = Get-DriveLetter @("R", "T", "U")
subst "${firstLetter}:" $firstBacking
try {
    $firstRoot = "${firstLetter}:\"
    $firstExe = Join-Path $firstRoot "GO-CLAW-Portable.exe"
    $firstReadyFile = Join-Path $env:RUNNER_TEMP "go-claw-portable-first-ready.json"
    Remove-Item -LiteralPath $firstReadyFile -Force -ErrorAction SilentlyContinue
    $env:CI = "true"
    $env:GO_CLAW_E2E_DESKTOP_READY_FILE = $firstReadyFile
    Start-Process -FilePath $firstExe
    $firstPort = Wait-PortableReady $firstRoot
    Wait-DesktopReady -Path $firstReadyFile -ExpectedPort $firstPort
    $firstBackend = Get-BackendProcess

    # Second double-click must be forwarded to the first shell.
    $secondLaunch = Start-Process -FilePath $firstExe -PassThru
    if (-not $secondLaunch.WaitForExit(15000)) {
        throw "Second portable launch did not exit after single-instance forwarding"
    }
    Start-Sleep -Seconds 3
    $afterDoubleClick = Get-BackendProcess
    if ($afterDoubleClick.Id -ne $firstBackend.Id) {
        throw "Second double-click replaced backend PID $($firstBackend.Id) with $($afterDoubleClick.Id)"
    }
    $portAfterDoubleClick = (Get-Content (Join-Path $firstRoot "data\desktop_port") -Raw).Trim()
    if ([int]$portAfterDoubleClick -ne $firstPort) {
        throw "Second double-click changed backend port"
    }
    Assert-PortableOutputs $firstRoot

    Stop-PortableGracefully $firstExe
    # Microsoft documents that WebView2 browser processes can outlive the host
    # briefly. Do not copy its user-data folder until that session has ended.
    Wait-NewWebView2ProcessesExit -BaselinePids $baselineWebViewPids

    # Pin an external project path into agent.json; relocation must preserve it.
    $externalProject = Join-Path $env:RUNNER_TEMP "external-project-keep"
    New-Item -ItemType Directory -Force -Path $externalProject | Out-Null
    $agentPath = Join-Path $firstRoot "data\workspaces\default\agent.json"
    $agent = Get-Content $agentPath -Raw | ConvertFrom-Json
    if (-not $agent.coding_mode) {
        $agent | Add-Member -NotePropertyName coding_mode -NotePropertyValue ([pscustomobject]@{})
    }
    $agent.coding_mode | Add-Member -Force -NotePropertyName project_dir -NotePropertyValue $externalProject
    $agent | ConvertTo-Json -Depth 100 | Set-Content $agentPath -Encoding utf8

    Copy-Item $firstBacking $secondBacking -Recurse
} finally {
    Export-PortableLogs -Root $firstRoot
    subst "${firstLetter}:" /D 2>$null
}
Remove-Item $firstBacking -Recurse -Force

subst "${secondLetter}:" $secondBacking
try {
    $secondRoot = "${secondLetter}:\"
    $secondExe = Join-Path $secondRoot "GO-CLAW-Portable.exe"
    $secondReadyFile = Join-Path $env:RUNNER_TEMP "go-claw-portable-second-ready.json"
    Remove-Item -LiteralPath $secondReadyFile -Force -ErrorAction SilentlyContinue
    $env:CI = "true"
    $env:GO_CLAW_E2E_DESKTOP_READY_FILE = $secondReadyFile
    Start-Process -FilePath $secondExe
    $secondPort = Wait-PortableReady $secondRoot
    Wait-DesktopReady -Path $secondReadyFile -ExpectedPort $secondPort
    Save-DesktopScreenshot -Name "desktop-content-ready.png"
    Assert-PortableOutputs $secondRoot

    $agents = Invoke-RestMethod -Uri "http://127.0.0.1:$secondPort/api/agents" -TimeoutSec 10
    $defaultAgent = $agents.agents | Where-Object { $_.id -eq "default" } | Select-Object -First 1
    if (-not $defaultAgent) { throw "Default agent missing after relocation" }
    # subst may be resolved by Python/Windows APIs to its backing directory.
    # Both forms identify the relocated USB root; the old backing path was
    # deleted above, so accepting it here would still fail.
    $actualWorkspace = [IO.Path]::GetFullPath($defaultAgent.workspace_dir).TrimEnd('\')
    $expectedWorkspaces = @(
        [IO.Path]::GetFullPath((Join-Path $secondRoot "data\workspaces\default")).TrimEnd('\'),
        [IO.Path]::GetFullPath((Join-Path $secondBacking "data\workspaces\default")).TrimEnd('\')
    )
    $workspaceRebound = $expectedWorkspaces | Where-Object {
        $_.Equals($actualWorkspace, [System.StringComparison]::OrdinalIgnoreCase)
    }
    if (-not $workspaceRebound) {
        throw "Workspace was not rebound to relocated root: $($defaultAgent.workspace_dir)"
    }
    # The customer agent API intentionally omits private configuration such as
    # coding_mode. Verify relocation against the copied local profile instead.
    $relocatedAgentPath = Join-Path $secondRoot "data\workspaces\default\agent.json"
    $relocatedAgent = Get-Content $relocatedAgentPath -Raw | ConvertFrom-Json
    if ($relocatedAgent.coding_mode.project_dir -ne $externalProject) {
        throw "External project_dir was incorrectly rebased: $($relocatedAgent.coding_mode.project_dir)"
    }

    if (-not $profileExistedBefore -and (Test-Path $profileData)) {
        throw "Portable run wrote to $profileData"
    }
    if (-not $portableLocalExistedBefore -and (Test-Path $portableLocalData)) {
        throw "Portable run wrote to $portableLocalData"
    }
    if (-not $installedLocalExistedBefore -and (Test-Path $installedLocalData)) {
        throw "Portable run wrote to $installedLocalData"
    }

    $baseUrl = "http://127.0.0.1:$secondPort"
    $env:BASE_URL = $baseUrl
    $env:PORTABLE_ROOT = $secondRoot
    $env:PORTABLE_EXE = $secondExe
    "BASE_URL=$baseUrl" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
    "PORTABLE_ROOT=$secondRoot" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
    "PORTABLE_EXE=$secondExe" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
    Write-Host "Portable relocation verified at $secondRoot"
    Write-Host "BASE_URL=$baseUrl"
} catch {
    Export-PortableLogs -Root $secondRoot
    subst "${secondLetter}:" /D 2>$null
    throw
}

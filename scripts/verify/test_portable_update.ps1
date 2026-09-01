param(
  [Parameter(Mandatory = $true)]
  [string]$NsisScript
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$work = Join-Path $env:RUNNER_TEMP "go-claw-update-e2e"
if (Test-Path -LiteralPath $work) {
  Remove-Item -LiteralPath $work -Recurse -Force
}
New-Item -ItemType Directory -Path $work | Out-Null
Copy-Item -LiteralPath $NsisScript -Destination (Join-Path $work "update.nsi")

$probeSource = @'
using System;
using System.IO;

public static class Program {
    public static int Main(string[] args) {
        string root = AppContext.BaseDirectory;
        string updates = Path.Combine(root, "updates");
        Directory.CreateDirectory(updates);
        string file = args.Length == 1 && args[0] == "--portable-quit"
            ? "quit-probe.txt"
            : "restart-probe.txt";
        File.AppendAllText(
            Path.Combine(updates, file),
            DateTime.UtcNow.ToString("O") + Environment.NewLine
        );
        return 0;
    }
}
'@

$probeExe = Join-Path $work "GO-CLAW-Portable-probe.exe"
$probeSourceFile = Join-Path $work "GO-CLAW-Portable-probe.cs"
[IO.File]::WriteAllText($probeSourceFile, $probeSource)
$csc = @(
  (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
  (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $csc) {
  throw "Windows .NET Framework C# compiler not found"
}
& $csc `
  /nologo `
  /target:winexe `
  "/out:$probeExe" `
  $probeSourceFile
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $probeExe)) {
  throw "restart probe compilation failed: $LASTEXITCODE"
}

function New-PortableRoot([string]$Name) {
  $root = Join-Path $work $Name
  New-Item -ItemType Directory -Path $root | Out-Null
  New-Item `
    -ItemType Directory `
    -Path (Join-Path $root "binaries\qwenpaw-backend") | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $root "updates") | Out-Null
  [IO.File]::WriteAllText(
    (Join-Path $root "portable.json"),
    '{"schemaVersion":1}'
  )
  [IO.File]::WriteAllText(
    (Join-Path $root "updates\version.txt"),
    "2.0.1"
  )
  [IO.File]::WriteAllText(
    (Join-Path $root "binaries\qwenpaw-backend\old-marker.txt"),
    "old"
  )
  [IO.File]::WriteAllText((Join-Path $root "LICENSE"), "old-license")
  [IO.File]::WriteAllText(
    (Join-Path $root "README-PORTABLE.zh-CN.txt"),
    "old-readme"
  )
  Copy-Item `
    -LiteralPath $probeExe `
    -Destination (Join-Path $root "GO-CLAW-Portable.exe")
  return $root
}

$payload = Join-Path $work "payload"
New-Item `
  -ItemType Directory `
  -Path (Join-Path $payload "binaries\qwenpaw-backend") | Out-Null
[IO.File]::WriteAllText(
  (Join-Path $payload "binaries\qwenpaw-backend\new-marker.txt"),
  "new"
)
[IO.File]::WriteAllText((Join-Path $payload "LICENSE"), "new-license")
[IO.File]::WriteAllText(
  (Join-Path $payload "README-PORTABLE.zh-CN.txt"),
  "new-readme"
)
Copy-Item `
  -LiteralPath $probeExe `
  -Destination (Join-Path $payload "GO-CLAW-Portable.exe")

Push-Location $work
try {
  & makensis `
    "/DGO_CLAW_VERSION=2.1.1" `
    "/DGO_CLAW_BACKUP_RETRIES=2" `
    "/DGO_CLAW_MAX_RELATIVE_PATH=80" `
    "update.nsi"
  if ($LASTEXITCODE -ne 0) {
    throw "makensis probe build failed: $LASTEXITCODE"
  }
} finally {
  Pop-Location
}

$update = Join-Path $work "GO-CLAW-Update-2.1.1-setup.exe"

# Success: reproduce the deployed v2.0.1 launch context exactly. The updater
# must move its own cwd out of binaries before attempting the directory rename.
$successRoot = New-PortableRoot "success-root"
$success = Start-Process `
  -FilePath $update `
  -WorkingDirectory (Join-Path $successRoot "binaries\qwenpaw-backend") `
  -ArgumentList @("/S", "/D=$successRoot") `
  -Wait `
  -PassThru
if ($success.ExitCode -ne 0) {
  throw "success scenario exited $($success.ExitCode)"
}
if (-not (Test-Path (Join-Path $successRoot "binaries\qwenpaw-backend\new-marker.txt"))) {
  throw "new payload missing"
}
if (-not (Test-Path (Join-Path $successRoot "updates\backup-2.0.1\binaries\qwenpaw-backend\old-marker.txt"))) {
  throw "old backup missing"
}
if ((Get-Content (Join-Path $successRoot "updates\version.txt") -Raw).Trim() -ne "2.1.1") {
  throw "version marker not updated"
}
if (Test-Path (Join-Path $successRoot "updates\installing.lock")) {
  throw "success left installing.lock"
}
if (Test-Path (Join-Path $successRoot "updates\last-update-error.txt")) {
  throw "success left error marker"
}
$restartProbe = Join-Path $successRoot "updates\restart-probe.txt"
$restartDeadline = [DateTime]::UtcNow.AddSeconds(10)
while (
  -not (Test-Path -LiteralPath $restartProbe) -and
  [DateTime]::UtcNow -lt $restartDeadline
) {
  Start-Sleep -Milliseconds 200
}
if (-not (Test-Path -LiteralPath $restartProbe)) {
  throw "updated executable was not restarted"
}

# Failure: an unrelated process deliberately owns binaries as cwd. The update
# must fail with a precise stage and restore the complete old program tree.
$rollbackRoot = New-PortableRoot "rollback-root"
$holder = Start-Process `
  -FilePath "powershell.exe" `
  -WorkingDirectory (Join-Path $rollbackRoot "binaries") `
  -ArgumentList @(
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    "Start-Sleep -Seconds 20"
  ) `
  -PassThru
try {
  $failed = Start-Process `
    -FilePath $update `
    -WorkingDirectory (Join-Path $rollbackRoot "updates") `
    -ArgumentList @("/S", "/D=$rollbackRoot") `
    -Wait `
    -PassThru
  if ($failed.ExitCode -eq 0) {
    throw "locked rollback scenario unexpectedly succeeded"
  }
} finally {
  Stop-Process -Id $holder.Id -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path (Join-Path $rollbackRoot "GO-CLAW-Portable.exe"))) {
  throw "old executable was not restored"
}
if (-not (Test-Path (Join-Path $rollbackRoot "binaries\qwenpaw-backend\old-marker.txt"))) {
  throw "old binaries were not preserved"
}
if (Test-Path (Join-Path $rollbackRoot "binaries\qwenpaw-backend\new-marker.txt")) {
  throw "mixed new payload found after rollback"
}
$errorText = Get-Content `
  (Join-Path $rollbackRoot "updates\last-update-error.txt") `
  -Raw
if ($errorText -notmatch "stage=backup:binaries") {
  throw "missing backup:binaries diagnosis"
}
if ($errorText -notmatch "restore=ok") {
  throw "rollback was not verified"
}
if (Test-Path (Join-Path $rollbackRoot "updates\installing.lock")) {
  throw "verified rollback left installing.lock"
}

Write-Host "Portable updater executable contract passed."

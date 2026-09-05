param(
  [Parameter(Mandatory = $true)]
  [string]$NsisScript
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$makensis = Get-Command makensis -ErrorAction SilentlyContinue
if (-not $makensis) {
  throw "makensis is required for the Bridge executable contract"
}
$runnerTemp = [IO.Path]::GetFullPath($env:RUNNER_TEMP)
$work = [IO.Path]::GetFullPath((Join-Path $runnerTemp "go-claw-update-bridge-e2e"))
$tempPrefix = $runnerTemp.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $work.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Bridge test work directory escaped RUNNER_TEMP"
}
if (Test-Path -LiteralPath $work) {
  Remove-Item -LiteralPath $work -Recurse -Force
}
New-Item -ItemType Directory -Path $work | Out-Null
Copy-Item -LiteralPath $NsisScript -Destination (Join-Path $work "bridge.nsi")

$fakeSource = @'
using System;
using System.IO;
using System.Linq;

public static class Program {
    public static int Main(string[] args) {
        if (args.Length == 0) return 9;
        int rootIndex = Array.IndexOf(args, "--root");
        if (rootIndex < 0 || rootIndex + 1 >= args.Length) return 8;
        string root = args[rootIndex + 1];
        if (args[0] == "bridge-progress") {
            Console.WriteLine("50");
            return 0;
        }
        if (args[0] != "bridge") return 9;
        Directory.CreateDirectory(Path.Combine(root, "updates", "bridge"));
        File.WriteAllLines(Path.Combine(root, "updates", "bridge", "probe.txt"), args);
        File.WriteAllText(Path.Combine(root, "updates", "bridge", "result.txt"), "0\nCOMMITTED\n");
        return 0;
    }
}
'@
$source = Join-Path $work "fake-engine.cs"
$engine = Join-Path $work "fake-engine.exe"
[IO.File]::WriteAllText($source, $fakeSource)
$csc = @(
  (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
  (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $csc) { throw "Windows .NET Framework C# compiler not found" }
& $csc /nologo /target:exe "/out:$engine" $source
if ($LASTEXITCODE -ne 0) { throw "fake Bridge engine compilation failed" }

$root = Join-Path $work "portable root 中文"
New-Item -ItemType Directory -Path (Join-Path $root "data") -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $root "portable.json"), '{"schemaVersion":1}')
[IO.File]::WriteAllText((Join-Path $root "data\chats.json"), '保留的聊天')
$before = (Get-FileHash -LiteralPath (Join-Path $root "data\chats.json") -Algorithm SHA256).Hash

Push-Location $work
try {
  & $makensis.Source `
    "/INPUTCHARSET" "UTF8" `
    "/DGO_CLAW_VERSION=2.1.2" `
    "/DGO_CLAW_INDEX_URL=https://staging.invalid/release-index-v2.json" `
    "/DGO_CLAW_TARGET_MANIFEST=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" `
    "/DGO_CLAW_ENGINE=$engine" `
    "/DGO_CLAW_BRIDGE_HEADLESS=1" `
    "bridge.nsi"
  if ($LASTEXITCODE -ne 0) { throw "Bridge NSIS compilation failed" }
} finally {
  Pop-Location
}

$bridge = Join-Path $work "GO-CLAW-Update-2.1.2-setup.exe"
$run = Start-Process -FilePath $bridge -ArgumentList @("/S", "/D=$root") -Wait -PassThru
if ($run.ExitCode -ne 0) { throw "Bridge exited $($run.ExitCode)" }
$probe = Get-Content -LiteralPath (Join-Path $root "updates\bridge\probe.txt")
if ($probe[0] -ne "bridge" -or $probe -notcontains $root) {
  throw "Bridge did not preserve the portable root argument"
}
foreach ($required in @(
  "--index-url",
  "https://staging.invalid/release-index-v2.json",
  "--target-version",
  "2.1.2",
  "--target-manifest",
  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)) {
  if ($probe -notcontains $required) { throw "Bridge missing argument: $required" }
}
$after = (Get-FileHash -LiteralPath (Join-Path $root "data\chats.json") -Algorithm SHA256).Hash
if ($before -ne $after) { throw "Bridge wrapper modified customer data" }

# Compile the interactive page too. Headless mode intentionally excludes its
# timer callback, so compiling only the executable test would miss linker
# removal or nsDialogs macro regressions in the customer-facing UI.
Push-Location $work
try {
  $uiOutput = & $makensis.Source `
    "/INPUTCHARSET" "UTF8" `
    "/DGO_CLAW_VERSION=2.1.2" `
    "/DGO_CLAW_INDEX_URL=https://staging.invalid/release-index-v2.json" `
    "/DGO_CLAW_TARGET_MANIFEST=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" `
    "/DGO_CLAW_ENGINE=$engine" `
    "bridge.nsi" 2>&1 | Out-String
  $uiExitCode = $LASTEXITCODE
} finally {
  Pop-Location
}
if ($uiExitCode -ne 0) { throw "Interactive Bridge NSIS compilation failed" }
if ($uiOutput -match 'function "BridgePoll" not referenced') {
  throw "Interactive Bridge timer callback was removed by the NSIS linker"
}

# The customer-facing wrapper must close itself after the engine publishes a
# committed result. A successful transaction with a lingering update.exe still
# locks removable media and is therefore a failed Bridge contract.
$uiRoot = Join-Path $work "interactive portable root 中文"
New-Item -ItemType Directory -Path (Join-Path $uiRoot "data") -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $uiRoot "portable.json"), '{"schemaVersion":1}')
[IO.File]::WriteAllText((Join-Path $uiRoot "data\chats.json"), '交互更新保留的聊天')
$uiBefore = (Get-FileHash -LiteralPath (Join-Path $uiRoot "data\chats.json") -Algorithm SHA256).Hash
$uiRun = Start-Process -FilePath $bridge -ArgumentList @("/S", "/D=$uiRoot") -PassThru
$uiDeadline = [DateTime]::UtcNow.AddSeconds(15)
while (-not $uiRun.HasExited -and [DateTime]::UtcNow -lt $uiDeadline) {
  Start-Sleep -Milliseconds 100
  $uiRun.Refresh()
}
if (-not $uiRun.HasExited) {
  Stop-Process -Id $uiRun.Id -Force -ErrorAction SilentlyContinue
  throw "Interactive Bridge did not exit after COMMITTED result"
}
if ($uiRun.ExitCode -ne 0) { throw "Interactive Bridge exited $($uiRun.ExitCode)" }
$uiAfter = (Get-FileHash -LiteralPath (Join-Path $uiRoot "data\chats.json") -Algorithm SHA256).Hash
if ($uiBefore -ne $uiAfter) { throw "Interactive Bridge wrapper modified customer data" }
Write-Host "Portable A/B Bridge executable contract passed."

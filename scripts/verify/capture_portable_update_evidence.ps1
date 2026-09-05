param(
    [Parameter(Mandatory = $true)][string]$ProductRoot,
    [Parameter(Mandatory = $true)][string]$EvidenceDirectory,
    [switch]$IncludeDataDigests
)

# Read-only against the product. Evidence must go to a fresh, external directory.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$product = (Resolve-Path -LiteralPath $ProductRoot).Path.TrimEnd('\')
$evidence = [IO.Path]::GetFullPath($EvidenceDirectory).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $product 'portable.json'))) {
    throw 'Portable root marker missing'
}
if ($evidence.Equals($product, [StringComparison]::OrdinalIgnoreCase) -or
    $evidence.StartsWith($product + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Evidence directory must be outside the product'
}
if (Test-Path -LiteralPath $evidence) { throw 'Evidence directory already exists' }
New-Item -ItemType Directory -Path $evidence | Out-Null

# Never capture command lines: plugin process arguments may contain credentials.
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.StartsWith(
        $product + '\', [StringComparison]::OrdinalIgnoreCase
    )
} | Select-Object Name, ProcessId, ParentProcessId, ExecutablePath)
$processes | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'processes.json') -Encoding UTF8

# A desktop_port file is not process identity: another product can reuse it.
$portFile = Join-Path $product 'data\desktop_port'
if (Test-Path -LiteralPath $portFile -PathType Leaf) {
    $port = 0
    if ([int]::TryParse((Get-Content -LiteralPath $portFile -Raw).Trim(), [ref]$port) -and $port -gt 0 -and $port -le 65535) {
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        $bindings = @(foreach ($listener in $listeners) {
            $owner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess)
            [pscustomobject]@{
                port=$port
                pid=$listener.OwningProcess
                executablePath=$owner.ExecutablePath
                matchesProduct=($owner.ExecutablePath -eq (Join-Path $product 'binaries\qwenpaw-backend\qwenpaw-backend.exe'))
            }
        })
        ConvertTo-Json -InputObject $bindings -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'port-bindings.json') -Encoding UTF8
    }
}

$updateFiles = @('install.log', 'last-update-error.txt', 'last-update.json', 'version.txt', 'installing.lock')
foreach ($name in $updateFiles) {
    $source = Join-Path $product ('updates\' + $name)
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $evidence $name)
    }
}
$updates = Join-Path $product 'updates'
if (Test-Path -LiteralPath $updates) {
    @(Get-ChildItem -LiteralPath $updates -Force -Recurse |
        Select-Object FullName, Length, LastWriteTimeUtc, Attributes) |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'updates-tree.json') -Encoding UTF8
}
$programs = @('GO-CLAW-Portable.exe', 'binaries\qwenpaw-backend\qwenpaw-backend.exe', 'updates\cached-update\update.exe')
$hashes = @(foreach ($relative in $programs) {
    $file = Join-Path $product $relative
    if (Test-Path -LiteralPath $file -PathType Leaf) {
        $item = Get-Item -LiteralPath $file
        [pscustomobject]@{path=$relative; size=$item.Length; sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash}
    }
})
$hashes | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'program-hashes.json') -Encoding UTF8

# Only explicit acceptance captures scan data. No content, keys, quota or token values are emitted.
if ($IncludeDataDigests) {
    $records = @(foreach ($relative in @('data', 'secrets', 'GO-CLAW-Config', 'portable.json')) {
        $path = Join-Path $product $relative
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $files = if (Test-Path -LiteralPath $path -PathType Leaf) { @(Get-Item -LiteralPath $path) }
            else { @(Get-ChildItem -LiteralPath $path -File -Recurse -Force) }
        foreach ($file in $files) {
            if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Data digest encountered a reparse point' }
            $digest = $null
            $readStatus = 'ok'
            try { $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
            catch { $readStatus = 'unreadable' }
            [pscustomobject]@{
                path=$file.FullName.Substring($product.Length + 1)
                size=$file.Length
                sha256=$digest
                readStatus=$readStatus
            }
        }
    })
    $records | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'data-digests.json') -Encoding UTF8
}
Write-Output ('Evidence captured: ' + $evidence)

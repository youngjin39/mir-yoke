[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$MirArgs)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ReceiptPath = Join-Path $ProjectRoot ".mir/bootstrap-receipt.json"
if (-not (Test-Path $ReceiptPath -PathType Leaf)) {
    throw "bootstrap receipt is missing; run setup.sh inside WSL"
}
$Receipt = Get-Content -Raw $ReceiptPath | ConvertFrom-Json
$MirCli = [string]$Receipt.cli.executable
if (-not $MirCli -or -not (Test-Path $MirCli -PathType Leaf)) {
    throw "external Mir CLI is unavailable; rerun setup.sh inside WSL"
}
$ActualHash = (Get-FileHash -Algorithm SHA256 $MirCli).Hash.ToLowerInvariant()
if (-not $Receipt.cli.sha256 -or $ActualHash -ne [string]$Receipt.cli.sha256) {
    throw "external Mir CLI hash changed; rerun setup.sh inside WSL"
}
if ([string]$Receipt.cli.runtime_manifest) {
    $RuntimeRoot = Split-Path -Parent (Split-Path -Parent $MirCli)
    $RuntimeManifest = [string]$Receipt.cli.runtime_manifest
    $ExpectedManifest = Join-Path $RuntimeRoot "runtime-manifest.json"
    if (-not $RuntimeManifest -or $RuntimeManifest -ne $ExpectedManifest -or
        -not (Test-Path $RuntimeManifest -PathType Leaf)) {
        throw "external Mir CLI runtime manifest is invalid; rerun setup.sh inside WSL"
    }
    $ActualManifestHash = (Get-FileHash -Algorithm SHA256 $RuntimeManifest).Hash.ToLowerInvariant()
    if (-not $Receipt.cli.runtime_manifest_sha256 -or
        $ActualManifestHash -ne [string]$Receipt.cli.runtime_manifest_sha256) {
        throw "external Mir CLI runtime changed; rerun setup.sh inside WSL"
    }
    & $MirCli runtime-manifest verify --runtime-root $RuntimeRoot --manifest $RuntimeManifest `
        --source-url ([string]$Receipt.cli.source_url) `
        --source-commit ([string]$Receipt.cli.source_commit) `
        --constraints-sha256 ([string]$Receipt.cli.constraints_sha256)
    if ($LASTEXITCODE -ne 0) {
        throw "external Mir CLI runtime changed; rerun setup.sh inside WSL"
    }
}
& $MirCli @MirArgs
exit $LASTEXITCODE

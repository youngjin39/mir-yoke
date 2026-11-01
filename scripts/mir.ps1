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
    $VerifyArgs = @(
        "--runtime-root", $RuntimeRoot, "--manifest", $RuntimeManifest,
        "--source-url", ([string]$Receipt.cli.source_url),
        "--source-commit", ([string]$Receipt.cli.source_commit),
        "--constraints-sha256", ([string]$Receipt.cli.constraints_sha256)
    )
    $VerifierExit = 64
    $VerifierOutput = @()
    $Verifier = [string]$Receipt.cli.runtime_verifier.path
    $VerifierHash = [string]$Receipt.cli.runtime_verifier.sha256
    if ($env:MIR_NATIVE_HOOKS -ne "0" -and $Verifier -and $VerifierHash) {
        if (-not [System.IO.Path]::IsPathRooted($Verifier)) {
            $Verifier = Join-Path $ProjectRoot $Verifier
        }
        try {
            $VerifierFile = Get-Item -LiteralPath $Verifier -ErrorAction Stop
            if (-not $VerifierFile.PSIsContainer -and
                -not ($VerifierFile.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -and
                (Get-FileHash -Algorithm SHA256 -LiteralPath $Verifier).Hash.ToLowerInvariant() -eq $VerifierHash) {
                $VerifierOutput = @(& $Verifier @VerifyArgs 2>&1)
                $VerifierExit = $LASTEXITCODE
            }
        } catch {
            $VerifierExit = 64
        }
    }
    if ($VerifierExit -eq 2) {
        foreach ($Line in $VerifierOutput) { [Console]::Error.WriteLine([string]$Line) }
    }
    if ($VerifierExit -ne 0 -and $VerifierExit -ne 2) {
        & $MirCli runtime-manifest verify @VerifyArgs
        $VerifierExit = $LASTEXITCODE
    }
    if ($VerifierExit -ne 0) {
        throw "external Mir CLI runtime changed; rerun setup.sh inside WSL"
    }
}
& $MirCli @MirArgs
exit $LASTEXITCODE

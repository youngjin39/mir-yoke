# Thin native PowerShell wrapper. Hooks still require Git Bash or WSL Bash on PATH.
[CmdletBinding()]
param(
    [string]$Slug,
    [ValidateSet("code_app", "hybrid_pipeline", "infra_runtime", "content_workspace", "infra", "hybrid")]
    [string]$Profile = "code_app",
    [switch]$Json,
    [switch]$Finalize,
    [switch]$ArchitectureInitialized,
    [switch]$SkipCapabilityActivation,
    [switch]$AllowIncomplete
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required: https://docs.astral.sh/uv/"
}

Write-Host "mir-yoke setup > root=$ProjectRoot"
& uv sync --project $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed with exit code $LASTEXITCODE"
}

$BootstrapArgs = @(
    "run", "--project", $ProjectRoot,
    "mir", "bootstrap", "--project-root", $ProjectRoot,
    "--profile", $Profile
)
if ($Slug) { $BootstrapArgs += @("--slug", $Slug) }
if ($Json) { $BootstrapArgs += "--json" }
if ($Finalize) { $BootstrapArgs += "--finalize" }
if ($ArchitectureInitialized) { $BootstrapArgs += "--architecture-initialized" }
if ($SkipCapabilityActivation) { $BootstrapArgs += "--skip-capability-activation" }
if ($AllowIncomplete) { $BootstrapArgs += "--allow-incomplete" }

& uv @BootstrapArgs
if ($LASTEXITCODE -ne 0) {
    throw "mir bootstrap failed with exit code $LASTEXITCODE"
}

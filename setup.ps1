# Thin native PowerShell wrapper. Hooks still require Git Bash or WSL Bash on PATH.
[CmdletBinding()]
param(
    [string]$Slug,
    [ValidateSet("code_app", "hybrid_pipeline", "infra_runtime", "content_workspace", "infra", "hybrid")]
    [Parameter(Mandatory = $true)]
    [string]$Profile,
    [string]$Purpose,
    [string[]]$Stack,
    [string[]]$Archive,
    [switch]$Json,
    [switch]$Finalize,
    [switch]$ArchitectureInitialized,
    [switch]$SkipCapabilityActivation,
    [switch]$AllowIncomplete,
    [string]$StorageRoot
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required: https://docs.astral.sh/uv/"
}

if ($StorageRoot) {
    $StorageRoot = [System.IO.Path]::GetFullPath($StorageRoot)
    $StoragePaths = @{
        "UV_CACHE_DIR" = Join-Path $StorageRoot "uv/cache"
        "UV_PYTHON_INSTALL_DIR" = Join-Path $StorageRoot "uv/python"
        "UV_TOOL_DIR" = Join-Path $StorageRoot "uv/tools"
        "MIR_CAPABILITY_HOME" = Join-Path $StorageRoot "mir/capabilities"
    }
    foreach ($Path in $StoragePaths.Values) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
    $env:UV_CACHE_DIR = $StoragePaths["UV_CACHE_DIR"]
    $env:UV_PYTHON_INSTALL_DIR = $StoragePaths["UV_PYTHON_INSTALL_DIR"]
    $env:UV_TOOL_DIR = $StoragePaths["UV_TOOL_DIR"]
    $env:MIR_CAPABILITY_HOME = $StoragePaths["MIR_CAPABILITY_HOME"]
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $ProjectRoot ".venv"
    Write-Host "external-first storage > root=$StorageRoot"
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
if ($Purpose) { $BootstrapArgs += @("--purpose", $Purpose) }
foreach ($Item in $Stack) { $BootstrapArgs += @("--stack", $Item) }
foreach ($Item in $Archive) { $BootstrapArgs += @("--archive", $Item) }
if ($Json) { $BootstrapArgs += "--json" }
if ($Finalize) { $BootstrapArgs += "--finalize" }
if ($ArchitectureInitialized) { $BootstrapArgs += "--architecture-initialized" }
if ($SkipCapabilityActivation) { $BootstrapArgs += "--skip-capability-activation" }
if ($AllowIncomplete) { $BootstrapArgs += "--allow-incomplete" }
if ($StorageRoot) { $BootstrapArgs += @("--storage-root", $StorageRoot) }

& uv @BootstrapArgs
if ($LASTEXITCODE -ne 0) {
    throw "mir bootstrap failed with exit code $LASTEXITCODE"
}

# Native Windows guidance entrypoint. Automated bootstrap runs on macOS, Linux, or WSL.
[CmdletBinding()]
param(
    [string]$Slug,
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

[Console]::Error.WriteLine(
    "Native Windows automated bootstrap is unsupported. " +
    "Run setup.sh inside WSL, or use agent-guided existing-repository/reference adaptation."
)
exit 1

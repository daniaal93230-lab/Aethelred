<#
 DEPRECATED: this legacy launcher used the old bot/ stack and does not attach to the API engine.
 It can interfere with the new runtime and Visor. Use scripts/run_api_paper.ps1 instead.
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Warning "DEPRECATED: scripts/run_paper_loop.ps1 is legacy and disabled."
Write-Host  "Forwarding to scripts/run_api_paper.ps1..." -ForegroundColor Yellow
& "$PSScriptRoot\run_api_paper.ps1"

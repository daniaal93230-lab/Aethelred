param(
  [string]$HostUrl = "http://localhost:8080",
  [string]$OutDir = "exports_download"
)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Write-Host "Downloading exports from $HostUrl"
Invoke-RestMethod -Uri "$HostUrl/export/trades.csv" -OutFile (Join-Path $OutDir "trades.csv")
Invoke-RestMethod -Uri "$HostUrl/export/decisions.csv" -OutFile (Join-Path $OutDir "decisions.csv")
Invoke-RestMethod -Uri "$HostUrl/export/trades.jsonl" -OutFile (Join-Path $OutDir "trades.jsonl")
Invoke-RestMethod -Uri "$HostUrl/export/decisions.jsonl" -OutFile (Join-Path $OutDir "decisions.jsonl")
Write-Host "Saved to $OutDir"

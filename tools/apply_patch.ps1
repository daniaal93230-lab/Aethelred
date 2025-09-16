param(
  [string]$PatchName = $(Get-Date -Format "yyyyMMdd_HHmm")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path .git)) {
  Write-Error "Run this from the Git repository root."
}

$patchPath = Join-Path (Get-Location) "$PatchName.patch"

$clip = Get-Clipboard
if (-not $clip) {
  Write-Error "Clipboard is empty. Copy the patch text first."
}

Set-Content -Path $patchPath -Value $clip -NoNewline -Encoding UTF8

$branch = "feat/$PatchName"
git checkout -b $branch

git apply --whitespace=fix "$patchPath" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "git apply failed, trying 'git am'..."
  git am --signoff < "$patchPath"
}

git add -A
git commit -m "Apply $PatchName from ChatGPT"
Write-Host "Patch applied on $branch."

param([string] = 20250916_1827)
Continue = "Stop"
if (-not (Test-Path .git)) { Write-Error "Run this from the Git repository root." }
 = Join-Path (Get-Location) ".patch"
 = Get-Clipboard
if (-not ) { Write-Error "Clipboard is empty. Copy the patch text first." }
Set-Content -Path  -Value  -NoNewline -Encoding UTF8
 = "feat/"
git checkout -b 
git apply --whitespace=fix "" 2>
if (0 -ne 0) {
  Write-Host "git apply failed, trying 'git am'..."
  git am --signoff < ""
}
git add -A
git commit -m "Apply  from ChatGPT"
Write-Host "Patch applied on ."

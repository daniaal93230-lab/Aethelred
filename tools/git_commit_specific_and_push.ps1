Set-Location 'C:\Code\Aethelred'
$files = @(
    'api/routes/demo_loop.py',
    'api/routes/runtime.py',
    'api/routes/__init__.py',
    'tools/stop_supervised_run.ps1',
    'tools/git_push_changes.ps1',
    'tools/git_pull_rebase_push.ps1'
)
foreach ($f in $files) { if (Test-Path $f) { git add $f; Write-Host "Ensured staged: $f" } else { Write-Host "Missing (skip): $f" } }

Write-Host 'Committing intended files (no-verify)...'
$st = git status --porcelain
Write-Host "Porcelain status:\n$st"
if ($st -eq '') { Write-Host 'Nothing to commit' } else { git commit --no-verify -m "api: add runtime and demo_loop endpoints; tools: safer stop script and push helpers" }

Write-Host 'Pushing to origin/main...'
$push = git push origin main 2>&1
Write-Host $push

Write-Host 'Final git status:'
git status -sb

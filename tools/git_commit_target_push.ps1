Set-Location 'C:\Code\Aethelred'
Write-Host 'Staging intended files...'
$files = @(
    'api/routes/demo_loop.py',
    'api/routes/runtime.py',
    'api/routes/__init__.py',
    'tools/stop_supervised_run.ps1',
    'tools/git_push_changes.ps1',
    'tools/git_pull_rebase_push.ps1'
)
foreach ($f in $files) {
    if (Test-Path $f) {
        git add $f
        Write-Host "Staged: $f"
    } else {
        Write-Host "Not found (skipping): $f"
    }
}

Write-Host 'Committing staged changes (if any)...'
$st = git status --porcelain
if ($st -eq '') {
    Write-Host 'No changes staged to commit.'
} else {
    git commit -m "tools: add safer stop script and push helpers; add runtime/demo_loop endpoints"
}

# Now attempt pull --rebase and push
Write-Host 'Rebasing onto origin/main...'
$pull = git pull --rebase origin main 2>&1
Write-Host $pull
if ($LASTEXITCODE -ne 0) {
    Write-Host 'git pull --rebase failed. Aborting rebase if necessary.'
    git rebase --abort 2>$null
    Write-Host 'Please resolve conflicts locally and retry.'
    exit 1
}

Write-Host 'Pushing to origin/main...'
$push = git push origin main 2>&1
Write-Host $push
if ($LASTEXITCODE -ne 0) {
    Write-Host 'git push failed. Inspect output above.'
    exit 1
}
Write-Host 'Push successful.'

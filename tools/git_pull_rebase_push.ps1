Set-Location 'C:\Code\Aethelred'
Write-Host 'Fetching and rebasing from origin/main...'
$pull = git pull --rebase origin main 2>&1
Write-Host $pull
if ($LASTEXITCODE -ne 0) {
    Write-Host 'git pull --rebase failed. Attempting to abort any in-progress rebase.'
    git rebase --abort 2>$null
    Write-Host 'Please resolve conflicts locally and retry the push.'
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

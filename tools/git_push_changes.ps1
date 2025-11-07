Set-Location 'C:\Code\Aethelred'
Write-Host 'Git status (porcelain):'
git status --porcelain

# Stage all changes
git add -A

# Check staged/unstaged
$st = git status --porcelain
if ($st -eq '') {
    Write-Host 'No changes to commit'
} else {
    Write-Host 'Committing changes...'
    git commit -m "tools: make stop_supervised_run.ps1 conservative (do not kill all python processes)"
}

Write-Host 'Current branch:'
git rev-parse --abbrev-ref HEAD

Write-Host 'Pushing to origin/main...'
git push origin main

$script = "python runner_paper.py"
while ($true) {
  try {
    Write-Host "[watchdog] starting runner"
    & $script
    Write-Host "[watchdog] runner exited code $LASTEXITCODE"
  } catch {
    Write-Host "[watchdog] exception: $_"
  }
  Start-Sleep -Seconds 5
}

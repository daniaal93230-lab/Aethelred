Set-Location 'C:\Code\Aethelred'

# Stop processes owning port 8080 (uvicorn)
$pids = @(Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
if ($pids.Count -gt 0) {
    foreach ($killPid in $pids) {
        try { Stop-Process -Id $killPid -Force -ErrorAction Stop; Write-Host "Stopped port PID: $killPid" } catch { }
    }
} else {
    Write-Host 'No port 8080 owners'
}

# Stop known matching processes by commandline
$matches = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn|watchdog.py|streamlit|bot.brain' } | Select-Object -ExpandProperty ProcessId -Unique
if ($matches) {
    foreach ($killPid in $matches) {
        try { Stop-Process -Id $killPid -Force -ErrorAction Stop; Write-Host "Stopped matching PID: $killPid" } catch { }
    }
} else {
    Write-Host 'No matching processes found'
}

# NOTE: Do NOT stop all python processes here. That is too aggressive and may
# interfere with unrelated work.
# Instead, only list python processes so the operator can inspect them and
# stop specific ones manually if desired.
$py = Get-Process -Name python -ErrorAction SilentlyContinue
if ($py) {
    Write-Host 'Python processes found (not stopping):'
    foreach ($p in $py) {
        Write-Host " PID: $($p.Id)  Started: $($p.StartTime)  Cmd: (use Get-CimInstance Win32_Process to inspect)"
    }
} else {
    Write-Host 'No python processes found'
}

Write-Host 'Remaining matching processes (uvicorn/watchdog/streamlit/bot.brain):'
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn|watchdog.py|streamlit|bot.brain' } | Select-Object ProcessId, CommandLine | Format-Table -AutoSize

# Check healthz
try {
    $h = Invoke-RestMethod http://127.0.0.1:8080/healthz -ErrorAction Stop
    Write-Host 'healthz: ' (ConvertTo-Json $h -Depth 5)
} catch {
    Write-Host 'healthz unreachable: ' $_.Exception.Message
}

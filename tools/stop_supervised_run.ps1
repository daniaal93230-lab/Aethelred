param(
  [switch]$Quiet,
  [int]$Port = 8080,
  [string]$ApiHost = "127.0.0.1"
)

Set-Location 'C:\Code\Aethelred'

# Stop processes owning the chosen port (uvicorn)
$pids = @(Get-NetTCPConnection -LocalAddress $ApiHost -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
if ($pids.Count -gt 0) {
    foreach ($p in $pids) {
        try { Stop-Process -Id $p -Force -ErrorAction Stop; if (-not $Quiet) { Write-Host "Stopped port PID: $p" } } catch { if (-not $Quiet) { Write-Warning "Could not stop PID $p" } }
    }
} else {
    if (-not $Quiet) { Write-Host "No port $Port owners" }
}

# Stop known matching processes by commandline
$matches = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn|watchdog.py|streamlit|bot.brain' } | Select-Object -ExpandProperty ProcessId -Unique
if ($matches) {
    foreach ($m in $matches) {
        try { Stop-Process -Id $m -Force -ErrorAction Stop; if (-not $Quiet) { Write-Host "Stopped matching PID: $m" } } catch { if (-not $Quiet) { Write-Warning "Could not stop matching PID $m" } }
    }
} else {
    if (-not $Quiet) { Write-Host 'No matching processes found' }
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
    if (-not $Quiet) { Write-Host 'No python processes found' }
}

Write-Host 'Remaining matching processes (uvicorn/watchdog/streamlit/bot.brain):'
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn|watchdog.py|streamlit|bot.brain' } | Select-Object ProcessId, CommandLine | Format-Table -AutoSize

# Check healthz
try {
    $url = ("http://{0}:{1}/healthz" -f $ApiHost, $Port)
    $h = Invoke-RestMethod $url -ErrorAction Stop
    Write-Host 'healthz: ' (ConvertTo-Json $h -Depth 5)
} catch {
    Write-Host "healthz unreachable: $($_.Exception.Message)"
}

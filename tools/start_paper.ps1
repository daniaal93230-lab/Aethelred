Param(
  [switch]$Watchdog,
  [switch]$Visor,
  [string]$ApiHost = "127.0.0.1",
  [int]$Port = 8080,
  [switch]$ForceKillPort
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot\..
try {
  # prefer venv python if present
  $py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe" | Resolve-Path -ErrorAction SilentlyContinue
  if (-not $py) { $py = "python" }
  # ensure QA env flags propagate to uvicorn (must be set before spawn)
  if (-not $env:MODE) { $env:MODE = "paper" }
  if (-not $env:SAFE_FLATTEN_ON_START) { $env:SAFE_FLATTEN_ON_START = "1" }
  if (-not $env:QA_DEV_ENGINE) { $env:QA_DEV_ENGINE = "1" }

  if ($ForceKillPort) {
    function Test-IsAdmin {
      $wid = [Security.Principal.WindowsIdentity]::GetCurrent()
      $prn = New-Object Security.Principal.WindowsPrincipal($wid)
      return $prn.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }

    if (-not (Test-IsAdmin)) {
      Write-Warning "Not elevated. ForceKillPort may fail. Run PowerShell as Administrator if PIDs do not stop."
    }

    Write-Host ("ForceKillPort set - evicting any listeners on {0}:{1}..." -f $ApiHost, $Port)
    $conns = Get-NetTCPConnection -LocalAddress $ApiHost -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    $pids = @()
    if ($conns) { $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique }
    foreach ($ownPid in $pids) {
      try {
        $proc = Get-Process -Id $ownPid -ErrorAction Stop
        Write-Host ("Stopping PID {0} ({1}) that is holding {2}:{3}..." -f $ownPid, $proc.ProcessName, $ApiHost, $Port)
        Stop-Process -Id $ownPid -Force
      } catch {
        Write-Warning ("Could not stop PID {0}. You may need to run in an elevated shell." -f $ownPid)
      }
    }
  }
  $apiUrl = ("http://{0}:{1}" -f $ApiHost, $Port)
  Write-Host ("Starting API on {0} with MODE={1}, QA_DEV_ENGINE={2}..." -f $apiUrl, $env:MODE, $env:QA_DEV_ENGINE)

  Start-Process -FilePath $py -ArgumentList @('-m','uvicorn','api.main:app','--host',"$ApiHost",'--port',"$Port") -WindowStyle Minimized
  Start-Sleep -Seconds 2

  if ($Watchdog) {
    Write-Host "Starting watchdog..."
  Start-Process -FilePath $py -ArgumentList @('scripts/watchdog.py','--base',$apiUrl,'--interval','2','--failures','2') -WindowStyle Minimized
  }

  if ($Visor) {
    Write-Host "Starting Visor..."
  $env:VISOR_API_BASE = $apiUrl
    $streamlit = Join-Path $PSScriptRoot "..\.venv\Scripts\streamlit.exe" | Resolve-Path -ErrorAction SilentlyContinue
    if (-not $streamlit) { $streamlit = "streamlit" }
    Start-Process -FilePath $streamlit -ArgumentList @('run','apps/visor/streamlit_app.py') -WindowStyle Minimized
  }

  # Health check
  try { $h = Invoke-RestMethod ("{0}/healthz" -f $apiUrl) -TimeoutSec 5; Write-Host "healthz: $(($h | ConvertTo-Json -Depth 5))" } catch { Write-Warning "healthz unreachable yet" }
  Write-Host "Done."
} finally {
  Pop-Location
}

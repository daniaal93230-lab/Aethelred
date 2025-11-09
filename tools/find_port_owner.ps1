param(
  [int]$Port = 8080,
  [string]$ApiHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$conns = Get-NetTCPConnection -LocalAddress $ApiHost -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
  Write-Host ("No listeners on {0}:{1}" -f $ApiHost, $Port)
  exit 0
}
$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($ownPid in $pids) {
  Write-Host ("PID owning {0}:{1}: {2}" -f $ApiHost, $Port, $ownPid)
  try {
    Get-CimInstance Win32_Process -Filter "ProcessId=$ownPid" |
      Select-Object ProcessId, Name, ExecutablePath, CommandLine |
      Format-List
  } catch {
    Write-Warning ("Could not inspect PID {0}" -f $ownPid)
  }
}

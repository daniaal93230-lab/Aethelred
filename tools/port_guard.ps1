<#
tools/port_guard.ps1

Non-destructive diagnostics helper for dev machines. Run as Admin when you suspect
a kernel/service-owned listener (like HTTP.SYS) is blocking a port (e.g. 8080).

This script will:
- capture netstat -abno
- show Get-NetTCPConnection rows
- capture netsh http servicestate and urlacl
- optionally (interactive) download Sysinternals TcpView and Handle to inspect
  kernel handles. It will not delete anything.

Usage (Admin recommended):
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\port_guard.ps1 -Port 8080

#>
param(
  [int]$Port = 8080,
  [string]$Host = '127.0.0.1',
  [switch]$IncludeSysinternals
)

$ErrorActionPreference = 'Continue'
$td = Join-Path $env:TEMP ('port_guard_{0}' -f $Port)
New-Item -Path $td -ItemType Directory -Force | Out-Null
$out = Join-Path $td 'report.txt'

"Port guard report for $Host:$Port - $(Get-Date)" | Out-File -FilePath $out -Encoding utf8

"--- netstat -abno (full) ---" | Out-File -Append -FilePath $out
netstat -abno | Out-File -Append -FilePath $out

"--- netstat lines for :$Port (context) ---" | Out-File -Append -FilePath $out
Select-String -InputObject (Get-Content $out) -Pattern ":$Port" -Context 5,2 | Out-File -Append -FilePath $out

"--- Get-NetTCPConnection (listen rows) ---" | Out-File -Append -FilePath $out
Get-NetTCPConnection -LocalAddress $Host -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Format-List * | Out-File -Append -FilePath $out

"--- Owning PIDs ---" | Out-File -Append -FilePath $out
$owners = @(Get-NetTCPConnection -LocalAddress $Host -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
if ($owners -and $owners.Count -gt 0) {
  $owners | Out-File -Append -FilePath $out
  foreach ($o in $owners) {
    "=== PID $o ===" | Out-File -Append -FilePath $out
    try { Get-Process -Id $o | Format-List * | Out-File -Append -FilePath $out } catch { "Get-Process: no result for $o" | Out-File -Append -FilePath $out }
    try { Get-CimInstance Win32_Process -Filter "ProcessId=$o" | Select ProcessId,Name,ExecutablePath,CommandLine,ParentProcessId | Format-List | Out-File -Append -FilePath $out } catch { "Win32_Process: none" | Out-File -Append -FilePath $out }
    try { Get-CimInstance Win32_Service | Where-Object { $_.ProcessId -eq $o } | Select Name,DisplayName,State,StartName,ProcessId,PathName | Format-List | Out-File -Append -FilePath $out } catch { "Win32_Service: none" | Out-File -Append -FilePath $out }
    try { cmd /c "tasklist /FI \"PID eq $o\" /FO LIST" | Out-File -Append -FilePath $out } catch { "tasklist: failed" | Out-File -Append -FilePath $out }
  }
} else {
  "No owners found (Get-NetTCPConnection returned nothing)" | Out-File -Append -FilePath $out
}

"--- netsh http show servicestate ---" | Out-File -Append -FilePath $out
try { netsh http show servicestate | Out-File -Append -FilePath $out } catch { "netsh servicestate: failed" | Out-File -Append -FilePath $out }

"--- netsh http show urlacl ---" | Out-File -Append -FilePath $out
try { netsh http show urlacl | Out-File -Append -FilePath $out } catch { "netsh urlacl: failed" | Out-File -Append -FilePath $out }

"--- netsh http show iplisten ---" | Out-File -Append -FilePath $out
try { netsh http show iplisten | Out-File -Append -FilePath $out } catch { "netsh iplisten: failed" | Out-File -Append -FilePath $out }

"--- excluded port ranges ipv4 ---" | Out-File -Append -FilePath $out
try { netsh interface ipv4 show excludedportrange protocol=tcp | Out-File -Append -FilePath $out } catch { "excludedportrange ipv4: failed" | Out-File -Append -FilePath $out }

"--- excluded port ranges ipv6 ---" | Out-File -Append -FilePath $out
try { netsh interface ipv6 show excludedportrange protocol=tcp | Out-File -Append -FilePath $out } catch { "excludedportrange ipv6: failed" | Out-File -Append -FilePath $out }

if ($IncludeSysinternals) {
  "--- Sysinternals: downloading TcpView & Handle ---" | Out-File -Append -FilePath $out
  $zipDir = Join-Path $env:TEMP 'sysinternals'
  New-Item -Path $zipDir -ItemType Directory -Force | Out-Null
  try {
    Invoke-WebRequest -Uri 'https://download.sysinternals.com/files/TcpView.zip' -OutFile (Join-Path $zipDir 'TcpView.zip') -UseBasicParsing
    Expand-Archive -Path (Join-Path $zipDir 'TcpView.zip') -DestinationPath $zipDir -Force
    "TcpView downloaded to: $zipDir" | Out-File -Append -FilePath $out
  } catch { "Sysinternals TcpView download failed: $_" | Out-File -Append -FilePath $out }
  try {
    Invoke-WebRequest -Uri 'https://download.sysinternals.com/files/Handle.zip' -OutFile (Join-Path $zipDir 'Handle.zip') -UseBasicParsing
    Expand-Archive -Path (Join-Path $zipDir 'Handle.zip') -DestinationPath $zipDir -Force
    "Handle extracted to: $zipDir" | Out-File -Append -FilePath $out
    # run handle for each owner if present
    foreach ($o in $owners) {
      try { & (Join-Path $zipDir 'handle.exe') -p $o | Out-File -Append -FilePath $out } catch { "handle.exe run failed for $o" | Out-File -Append -FilePath $out }
    }
  } catch { "Sysinternals Handle download or run failed: $_" | Out-File -Append -FilePath $out }
}

"Report saved to: $out" | Out-Host
Start-Process notepad.exe -ArgumentList $out

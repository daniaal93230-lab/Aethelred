# One-shot diagnostics for 127.0.0.1:8080
# Save outputs to %TEMP% and open notepad for review.
$ErrorActionPreference = 'Continue'
$fn = Join-Path $env:TEMP 'diagnose_8080.txt'
"=== START DIAGNOSTICS: $(Get-Date) ===" | Out-File -FilePath $fn -Encoding utf8
"=== NETSTAT (full) ===" | Out-File -Append -FilePath $fn
netstat -abno | Out-File -Append -FilePath $fn
"" | Out-File -Append -FilePath $fn
"=== NETSTAT LINES FOR :8080 (context 3) ===" | Out-File -Append -FilePath $fn
Select-String -InputObject (Get-Content $fn) -Pattern ':8080' -Context 3,3 | Out-File -Append -FilePath $fn
"" | Out-File -Append -FilePath $fn
"=== Get-NetTCPConnection ===" | Out-File -Append -FilePath $fn
Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Format-List * | Out-File -Append -FilePath $fn
"" | Out-File -Append -FilePath $fn
# owners
$owners = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
"Owners: $owners" | Out-File -Append -FilePath $fn
foreach ($o in $owners) {
  "=== PID $o ===" | Out-File -Append -FilePath $fn
  try { Get-Process -Id $o -ErrorAction Stop | Format-List * | Out-File -Append -FilePath $fn } catch { "Get-Process: no result for $o" | Out-File -Append -FilePath $fn }
  try { Get-CimInstance Win32_Process -Filter "ProcessId=$o" -ErrorAction Stop | Select-Object ProcessId, Name, ExecutablePath, CommandLine, ParentProcessId | Format-List | Out-File -Append -FilePath $fn } catch { "Win32_Process: no result for $o" | Out-File -Append -FilePath $fn }
  try { Get-CimInstance Win32_Service | Where-Object { $_.ProcessId -eq $o } | Select-Object Name,DisplayName,State,StartName,ProcessId,PathName | Format-List | Out-File -Append -FilePath $fn } catch { "Win32_Service: none for $o" | Out-File -Append -FilePath $fn }
  try { cmd /c "tasklist /svc /FI \"PID eq $o\"" | Out-File -Append -FilePath $fn } catch { "tasklist: failed for $o" | Out-File -Append -FilePath $fn }
}
"" | Out-File -Append -FilePath $fn
"=== netsh http show servicestate (grep 8080/127.0.0.1) ===" | Out-File -Append -FilePath $fn
try { netsh http show servicestate | Select-String '8080','127.0.0.1' -Context 2,2 | Out-File -Append -FilePath $fn } catch { "netsh servicestate: failed or empty" | Out-File -Append -FilePath $fn }
"" | Out-File -Append -FilePath $fn
"=== netsh http show urlacl ===" | Out-File -Append -FilePath $fn
try { netsh http show urlacl | Out-File -Append -FilePath $fn } catch { "netsh urlacl: failed" | Out-File -Append -FilePath $fn }
"" | Out-File -Append -FilePath $fn
"=== netsh http show iplisten ===" | Out-File -Append -FilePath $fn
try { netsh http show iplisten | Out-File -Append -FilePath $fn } catch { "netsh iplisten: failed" | Out-File -Append -FilePath $fn }
"" | Out-File -Append -FilePath $fn
"=== excluded port ranges IPv4 ===" | Out-File -Append -FilePath $fn
try { netsh interface ipv4 show excludedportrange protocol=tcp | Out-File -Append -FilePath $fn } catch { "excludedportrange ipv4: failed" | Out-File -Append -FilePath $fn }
"" | Out-File -Append -FilePath $fn
"=== excluded port ranges IPv6 ===" | Out-File -Append -FilePath $fn
try { netsh interface ipv6 show excludedportrange protocol=tcp | Out-File -Append -FilePath $fn } catch { "excludedportrange ipv6: failed" | Out-File -Append -FilePath $fn }
"" | Out-File -Append -FilePath $fn
Write-Host "Diagnostics saved to: $fn"
Start-Process notepad.exe -ArgumentList $fn

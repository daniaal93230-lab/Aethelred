# Post-reboot diagnostic for port 8080
$ErrorActionPreference = 'Continue'
Write-Host "=== Post-reboot diagnostics: $(Get-Date) ==="
$fn = Join-Path $env:TEMP 'post_reboot_8080.txt'
Write-Host "Saving netstat lines for :8080 to $fn"
netstat -abno | Select-String ':8080' | Out-File -FilePath $fn -Encoding utf8
Write-Host '--- NETSTAT LINES FOR :8080 ---'
Get-Content $fn | ForEach-Object { Write-Host $_ }
Write-Host '--- Get-NetTCPConnection for 127.0.0.1:8080 ---'
Try { Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8080 -State Listen -ErrorAction Stop | Format-List * } Catch { Write-Host 'No Get-NetTCPConnection rows or insufficient privileges' }

$owners = @()
Try { $owners = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8080 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique } Catch { }
if ($owners -and $owners.Count -gt 0) {
  Write-Host "Owners: $($owners -join ',')"
  foreach ($owner in $owners) {
    Write-Host "=== PID $owner ==="
    Try { Get-Process -Id $owner -ErrorAction Stop | Format-List Id, ProcessName, Path, StartTime, CPU, WorkingSet } Catch { Write-Host "Get-Process: no result for $owner" }
    Try { Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction Stop | Select-Object ProcessId, Name, ExecutablePath, CommandLine, ParentProcessId | Format-List } Catch { Write-Host "Win32_Process: no result for $owner" }
    Try { Get-CimInstance Win32_Service | Where-Object { $_.ProcessId -eq $owner } | Select-Object Name,DisplayName,State,StartName,ProcessId,PathName | Format-List } Catch { Write-Host "Win32_Service: none for $owner" }
    Try { cmd /c "tasklist /FI \"PID eq $owner\" /FO LIST" } Catch { Write-Host "tasklist: failed for $owner" }
  }
} else {
  Write-Host 'No owners found for 127.0.0.1:8080 (Get-NetTCPConnection returned nothing)'
}

Write-Host '--- netsh urlacl grep 8080 ---'
Try { netsh http show urlacl | Select-String '8080' -Context 2,2 | ForEach-Object { Write-Host $_ } } Catch { Write-Host 'netsh urlacl: failed or none for 8080' }

Write-Host '--- netsh servicestate grep 8080/127.0.0.1 ---'
Try { netsh http show servicestate | Select-String '8080','127.0.0.1' -Context 2,2 | ForEach-Object { Write-Host $_ } } Catch { Write-Host 'netsh servicestate: failed or none for 8080' }

Write-Host '--- netsh iplisten ---'
Try { netsh http show iplisten | ForEach-Object { Write-Host $_ } } Catch { Write-Host 'netsh iplisten: failed or empty' }

Write-Host '--- excluded port ranges (ipv4) ---'
Try { netsh interface ipv4 show excludedportrange protocol=tcp | ForEach-Object { Write-Host $_ } } Catch { Write-Host 'excludedportrange ipv4: failed or empty' }

Write-Host '--- excluded port ranges (ipv6) ---'
Try { netsh interface ipv6 show excludedportrange protocol=tcp | ForEach-Object { Write-Host $_ } } Catch { Write-Host 'excludedportrange ipv6: failed or empty' }

Write-Host "Diagnostics saved to $fn"
Start-Process notepad.exe -ArgumentList $fn

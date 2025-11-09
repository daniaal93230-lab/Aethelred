Set-Location 'C:\Code\Aethelred'
Start-Sleep -Seconds 3
try {
    $r = Invoke-RestMethod 'http://127.0.0.1:8080/runtime/account_runtime.json' -TimeoutSec 5
    $r | ConvertTo-Json -Depth 6 | Write-Host
} catch {
    Write-Host 'runtime fetch failed:' $_.Exception.Message
}

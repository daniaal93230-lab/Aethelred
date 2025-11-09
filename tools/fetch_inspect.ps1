Set-Location 'C:\Code\Aethelred'
Start-Sleep -Seconds 1
try {
    $i = Invoke-RestMethod 'http://127.0.0.1:8080/runtime/inspect_engine.json' -TimeoutSec 5
    $i | ConvertTo-Json -Depth 4 | Write-Host
} catch {
    Write-Host 'inspect failed:' $_.Exception.Message
}

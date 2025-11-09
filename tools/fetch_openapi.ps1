Set-Location 'C:\Code\Aethelred'
try {
    $api = Invoke-RestMethod 'http://127.0.0.1:8080/openapi.json' -TimeoutSec 5
    $api.paths.Keys | ConvertTo-Json | Write-Host
} catch {
    Write-Host 'openapi fetch failed:' $_.Exception.Message
}

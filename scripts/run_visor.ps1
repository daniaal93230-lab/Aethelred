param(
  [string]$ApiBase = "http://127.0.0.1:8080",
  [int]$RefreshSecs = 2
)

$env:VISOR_API_BASE = $ApiBase
$env:VISOR_REFRESH_SECS = "$RefreshSecs"

Write-Host "Starting Visor against $($env:VISOR_API_BASE) with refresh $($env:VISOR_REFRESH_SECS)s"
python -m streamlit run apps/visor/streamlit_app.py

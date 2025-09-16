param(
  [switch]$Install
)

$ErrorActionPreference = "Stop"

Write-Host "Using Python:" (python --version)

if ($Install) {
  if (Test-Path ".\requirements.txt") {
    Write-Host "Installing requirements.txt..."
    pip install -r requirements.txt
  } else {
    Write-Host "requirements.txt not found, skipping..."
  }
  Write-Host "Installing dev tools..."
  pip install ruff mypy pytest
}

Write-Host "`nRunning Ruff lint..."
ruff check api

Write-Host "`nRunning Ruff format check..."
ruff format --check api

Write-Host "`nRunning MyPy..."
mypy api

Write-Host "`nRunning pytest..."
pytest -q .\tests_api

Write-Host "`nAll checks finished."

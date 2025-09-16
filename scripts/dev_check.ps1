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
ruff check .

Write-Host "`nRunning Ruff format check..."
ruff format --check .

Write-Host "`nRunning MyPy..."
mypy .

Write-Host "`nRunning pytest..."
pytest -q

Write-Host "`nAll checks finished."

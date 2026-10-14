# Run the API Doc Intelligence Engine
# Usage: .\run.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Set-Location $root

# Install dependencies if needed
Write-Host "Checking dependencies..." -ForegroundColor Cyan
python -m pip install -r requirements.txt --quiet

# Install Playwright browser if not already installed
Write-Host "Checking Playwright Chromium..." -ForegroundColor Cyan
python -m playwright install chromium

# Force UTF-8 I/O on Windows to prevent CP1252 encoding errors
$env:PYTHONUTF8 = "1"

# Start the server
Write-Host "Starting API Doc Intelligence Engine on http://localhost:8000" -ForegroundColor Green
Write-Host "Swagger UI: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    py -m venv .venv
}

. ".\.venv\Scripts\Activate.ps1"

Write-Host "Installing requirements..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = "postgresql://postgres:password@localhost:5432/placement_prep"
}

Write-Host "Starting Placement Prep Agent..."
python app.py

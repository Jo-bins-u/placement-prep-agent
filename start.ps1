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

# The app refuses to start without a strong SECRET_KEY (it signs login sessions).
# Generate one the first time and keep it in .env (never commit .env).
$envText = Get-Content ".env" -Raw
if ($envText -notmatch "(?m)^\s*SECRET_KEY\s*=\s*\S{32,}") {
    $key = python -c "import secrets; print(secrets.token_urlsafe(64))"
    Add-Content ".env" "`r`nSECRET_KEY=$key"
    Write-Host "Generated a new SECRET_KEY in .env"
}

# DSA code only runs inside Docker unless PREPWISE_SANDBOX=local is set.
$dockerOk = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker info *> $null
    $dockerOk = ($LASTEXITCODE -eq 0)
}
# Pin the sandbox image to an exact digest the first time, so a changed or tampered
# "python:3.13-slim" tag can never silently replace the image user code runs in.
if ($dockerOk -and ($envText -notmatch "(?m)^\s*PREPWISE_SANDBOX_IMAGE\s*=")) {
    Write-Host "Pulling the code sandbox image (first run only)..."
    & docker pull python:3.13-slim | Out-Null
    $digest = & docker image inspect --format "{{index .RepoDigests 0}}" python:3.13-slim
    if ($LASTEXITCODE -eq 0 -and $digest -match "@sha256:") {
        Add-Content ".env" "`r`nPREPWISE_SANDBOX_IMAGE=$digest"
        Write-Host "Pinned sandbox image: $digest"
    }
}
if (-not $dockerOk -and ($envText -notmatch "(?m)^\s*PREPWISE_SANDBOX\s*=\s*local")) {
    Write-Host "NOTE: Docker isn't running, so running DSA code is disabled. Start Docker Desktop to enable it." -ForegroundColor Yellow
}

# DATABASE_URL comes from .env (see .env.example). No default credentials are set here.

Write-Host "Starting Placement Prep Agent..."
python app.py

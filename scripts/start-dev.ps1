$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Venv = Join-Path $Backend ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "`nPC Doctor AI - v3.1" -ForegroundColor Cyan
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher 'py' not found. Install Python 3.11+." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm not found. Install Node.js 20+." }
if (-not (Test-Path $Venv)) {
    py -3.12 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment. Confirm Python 3.12 is installed with 'py --list'." }
}
if (-not (Test-Path $Python)) { throw "Virtual environment Python was not created: $Python" }
& $Python -m pip install -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Push-Location $Frontend
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Frontend dependency installation failed." }
    Pop-Location
}
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    Start-Process -FilePath $Python -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000") -WorkingDirectory $Backend
    Start-Sleep -Seconds 2
} else {
    Write-Host "Backend already listening on port 8000; reusing it." -ForegroundColor Yellow
}
Write-Host "Backend:  http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Dashboard: http://localhost:5173" -ForegroundColor Green
Push-Location $Frontend
npm run dev
Pop-Location

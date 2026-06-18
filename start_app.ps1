# PowerShell script to start both backend and frontend servers
# Usage: .\start_app.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Effector Discovery Pipeline" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

function Get-PreferredPython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py -3.12"
    }
    return "python"
}

$pythonCmd = Get-PreferredPython

# Check if backend exists
if (-not (Test-Path "backend\main.py")) {
    Write-Host "ERROR: backend\main.py not found!" -ForegroundColor Red
    Write-Host "Please run this script from the project root directory." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if frontend exists
if (-not (Test-Path "frontend\package.json")) {
    Write-Host "ERROR: frontend\package.json not found!" -ForegroundColor Red
    Write-Host "Please run this script from the project root directory." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[0/3] Stopping any existing servers..." -ForegroundColor Yellow
# Stop any existing Node processes (frontend)
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
# Stop any existing Python processes that might be backend
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like "*Effector Pipeline*" -or $_.CommandLine -like "*main.py*"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "Done." -ForegroundColor Green
Write-Host ""

Write-Host "[0.5/2] Checking backend dependencies..." -ForegroundColor Yellow
Push-Location "$scriptDir\backend"
try {
    Invoke-Expression "$pythonCmd -c `"import fastapi`"" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
        Invoke-Expression "$pythonCmd -m pip install -q -r requirements.txt"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Failed to install backend dependencies!" -ForegroundColor Red
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
} catch {
    Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
    Invoke-Expression "$pythonCmd -m pip install -q -r requirements.txt"
}
Pop-Location
Write-Host ""

Write-Host "[1/4] Starting Demo Backend (port 8000)..." -ForegroundColor Green
Write-Host "  Demo API: http://localhost:8000" -ForegroundColor Gray
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\backend'; $pythonCmd main.py"
Start-Sleep -Seconds 3

Write-Host "[2/4] Starting Hosted API (port 8001)..." -ForegroundColor Green
Write-Host "  Hosted API: http://localhost:8001" -ForegroundColor Gray
Write-Host "  API Docs:   http://localhost:8001/docs" -ForegroundColor Gray
Write-Host ""

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir'; $pythonCmd -m uvicorn backend.hosted_api.main:app --port 8001 --reload"
Start-Sleep -Seconds 3

Write-Host "[3/4] Starting Job Worker..." -ForegroundColor Green
Write-Host "  Worker polls for queued jobs every 5s" -ForegroundColor Gray
Write-Host ""

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir'; $pythonCmd -m backend.hosted_api.worker"
Start-Sleep -Seconds 2

Write-Host "[4/4] Starting Frontend (port 3000)..." -ForegroundColor Green
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Gray
Write-Host ""

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\frontend'; npm run dev"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "All 4 processes are starting!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Demo UI:    http://localhost:3000       (mock demo)" -ForegroundColor White
Write-Host "Hosted UI:  http://localhost:3000/hosted (real jobs)" -ForegroundColor White
Write-Host "Demo API:   http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "Hosted API: http://localhost:8001/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "Four PowerShell windows have opened. Close them to stop." -ForegroundColor Yellow
Write-Host ""
Write-Host "Waiting for servers to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 12

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Servers should be ready now!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Open your browser and go to:" -ForegroundColor Yellow
Write-Host "  http://localhost:3000" -ForegroundColor Cyan -BackgroundColor DarkBlue
Write-Host ""
Write-Host "Press any key to exit this window (servers will keep running)..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")


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

Write-Host "[1/2] Starting Backend Server..." -ForegroundColor Green
Write-Host "Backend will be available at: http://localhost:8000" -ForegroundColor Gray
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""

# Start backend in new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\backend'; $pythonCmd main.py"

# Wait for backend to start
Start-Sleep -Seconds 3

Write-Host "[2/2] Starting Frontend Server..." -ForegroundColor Green
Write-Host "Frontend will be available at: http://localhost:3000" -ForegroundColor Gray
Write-Host ""

# Start frontend in new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\frontend'; npm run dev"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Both servers are starting!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "Frontend: http://localhost:3000" -ForegroundColor White
Write-Host ""
Write-Host "Two PowerShell windows have opened:" -ForegroundColor Yellow
Write-Host "  - One for backend (Python)" -ForegroundColor Gray
Write-Host "  - One for frontend (Node.js)" -ForegroundColor Gray
Write-Host ""
Write-Host "Close those windows to stop the servers." -ForegroundColor Yellow
Write-Host ""
Write-Host "Waiting for servers to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 8

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


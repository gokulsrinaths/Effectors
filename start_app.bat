@echo off
REM Start both backend and frontend servers for Effector Discovery Pipeline

echo ========================================
echo Starting Effector Discovery Pipeline
echo ========================================
echo.

REM Get the directory where this script is located
cd /d "%~dp0"

REM Check if backend directory exists
if not exist "backend\main.py" (
    echo ERROR: backend\main.py not found!
    echo Please run this script from the project root directory.
    pause
    exit /b 1
)

REM Check if frontend directory exists
if not exist "frontend\package.json" (
    echo ERROR: frontend\package.json not found!
    echo Please run this script from the project root directory.
    pause
    exit /b 1
)

echo [0/3] Stopping any existing servers...
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Effector Pipeline*" >nul 2>&1
timeout /t 2 /nobreak >nul
echo Done.
echo.

echo [0.5/2] Checking backend dependencies...
cd backend
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Installing backend dependencies...
    python -m pip install -q -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install backend dependencies!
        pause
        exit /b 1
    )
)
cd ..
echo.

echo [1/2] Starting Backend Server...
echo Backend will be available at: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.
start "Effector Pipeline - Backend" cmd /k "cd /d %~dp0backend && python main.py"

REM Wait a moment for backend to start
timeout /t 3 /nobreak >nul

echo [2/2] Starting Frontend Server...
echo Frontend will be available at: http://localhost:3000
echo.
start "Effector Pipeline - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo Both servers are starting!
echo ========================================
echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Two windows have opened - one for backend, one for frontend.
echo Close those windows to stop the servers.
echo.
echo Waiting for servers to initialize...
timeout /t 5 /nobreak >nul

echo.
echo Servers should be ready now!
echo Open your browser and go to: http://localhost:3000
echo.
pause


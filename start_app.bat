@echo off
REM Start both backend and frontend servers for Effector Discovery Pipeline

echo ========================================
echo Starting Effector Discovery Pipeline
echo ========================================
echo.

REM Get the directory where this script is located
cd /d "%~dp0"

set "PYTHON_CMD=py -3.12"
where py >nul 2>&1
if errorlevel 1 set "PYTHON_CMD=python"

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

echo [0.5/4] Checking backend dependencies...
cd backend
%PYTHON_CMD% -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Installing demo backend dependencies...
    %PYTHON_CMD% -m pip install --user -q -r requirements.txt
)
%PYTHON_CMD% -c "import sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo Installing hosted API dependencies...
    %PYTHON_CMD% -m pip install --user -q -r requirements-hosted.txt
    if errorlevel 1 (
        echo ERROR: Failed to install hosted API dependencies!
        pause
        exit /b 1
    )
)
cd ..
echo.

echo [1/4] Starting Demo Backend (port 8000)...
echo   Demo API: http://localhost:8000
echo.
start "Effector Pipeline - Demo Backend" cmd /k "cd /d %~dp0backend && %PYTHON_CMD% main.py"
timeout /t 3 /nobreak >nul

echo [2/4] Starting Hosted API (port 8001)...
echo   Hosted API: http://localhost:8001
echo.
start "Effector Pipeline - Hosted API" cmd /k "cd /d %~dp0 && %PYTHON_CMD% -m uvicorn backend.hosted_api.main:app --port 8001 --reload"
timeout /t 3 /nobreak >nul

echo [3/4] Starting Job Worker...
echo   Worker polls for queued jobs every 5s
echo.
start "Effector Pipeline - Worker" cmd /k "cd /d %~dp0 && %PYTHON_CMD% -m backend.hosted_api.worker"
timeout /t 2 /nobreak >nul

echo [4/4] Starting Frontend (port 3000)...
echo   Frontend: http://localhost:3000
echo.
start "Effector Pipeline - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo All 4 processes are starting!
echo ========================================
echo.
echo Demo UI:    http://localhost:3000        (mock demo)
echo Hosted UI:  http://localhost:3000/hosted (real jobs)
echo Demo API:   http://localhost:8000/docs
echo Hosted API: http://localhost:8001/docs
echo.
echo Four windows opened. Close them to stop the servers.
echo.
echo Waiting for servers to initialize...
timeout /t 12 /nobreak >nul

echo.
echo Servers should be ready. Open: http://localhost:3000
echo.
pause


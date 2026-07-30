@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

REM --- Check .env ---
if not exist ".env" (
    echo [Xi] .env not found, copying from .env.example...
    copy .env.example .env >nul
    echo [Xi] Please edit .env and add your API Key, then run again.
    pause
    exit /b 1
)

REM --- Check venv ---
if not exist ".venv\Scripts\python.exe" (
    echo [Xi] Creating virtual environment...
    python -m venv .venv
    echo [Xi] Installing backend dependencies...
    .venv\Scripts\pip install -e ".[dev]" -q
)

REM --- Check frontend build ---
if not exist "web\dist\index.html" (
    echo [Xi] Building frontend...
    cd web
    if not exist "node_modules" (
        echo [Xi] Installing frontend dependencies...
        call npm install --silent
    )
    call npm run build
    cd ..
)

REM --- Start server ---
echo.
echo   ====================================
echo     Agent Xi Server
echo     Open:  http://localhost:9731
echo   ====================================
echo.

.venv\Scripts\python.exe -m agent_xi.server --host 0.0.0.0 --port 9731

pause

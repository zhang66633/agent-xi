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

REM --- First-time setup ---
if not exist ".venv\Scripts\python.exe" (
    echo [Xi] Creating venv + installing backend deps...
    python -m venv .venv
    .venv\Scripts\pip install -e ".[dev]" -q
)
if not exist "web\node_modules" (
    echo [Xi] Installing frontend dependencies...
    cd web
    call npm install --silent
    cd ..
)

echo.
echo   ===========================================
echo     Agent Xi - Dev Mode
echo     Backend:  http://localhost:9731
echo     Frontend: http://localhost:5180 (HMR)
echo   ===========================================
echo.

REM --- Start backend in new window ---
start "Xi-Backend" cmd /c ".venv\Scripts\python.exe -m agent_xi.server --host 0.0.0.0 --port 9731"

REM --- Wait for backend ---
echo [Xi] Waiting for backend to start...
timeout /t 3 /nobreak >nul

REM --- Start frontend dev server in new window ---
start "Xi-Frontend" cmd /c "cd /d %PROJECT_DIR%web && npm run dev"

echo [Xi] Two windows opened. Close them to stop.
echo.
pause

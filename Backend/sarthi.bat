@echo off
setlocal
title Sarthi Backend
cd /d "%~dp0"

:: Server bind settings — keep in sync with Backend/config.py (API_HOST/API_PORT).
set "API_HOST=127.0.0.1"
set "API_PORT=8000"

:: ──────────────────────────────────────────────────────────────────
:: Sarthi Backend launcher.
::
:: Works from ANY working directory: all paths are resolved relative to
:: this script's location (%~dp0), never the caller's cwd and never a
:: hardcoded machine path.
::
::   Backend\sarthi.bat             dev mode — visible server window
::   Backend\sarthi.bat background  windowless API (pythonw, no console)
::
:: The backend binds to 127.0.0.1:8000 by default and serves:
::   /command      the client-facing command API (Desktop, Flutter, ...)
::   /ui           the local dashboard
::
:: Local access:
::   http://127.0.0.1:8000
::
:: Remote/LAN access is disabled by default. Do not expose this unauthenticated
:: API until authentication and protected transport have been configured.
:: ──────────────────────────────────────────────────────────────────

:: Locate the virtualenv: project root (.venv next to Backend/) first,
:: then a Backend-local .venv. Neither is required if Python is on PATH.
set "VENV=%~dp0..\.venv"
if not exist "%VENV%\Scripts\activate.bat" set "VENV=%~dp0.venv"

if /i "%~1"=="background" goto background

:: ── Dev mode: activate venv, launch a visible server window so you
::    can watch logs and close Sarthi by closing the window. ─────────
if exist "%VENV%\Scripts\activate.bat" (
    call "%VENV%\Scripts\activate.bat" >nul
)

python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Activate the project venv or install Python.
    pause
    exit /b 1
)

:: Start the local Ollama service when configured and not already running.
:: Missing model weights are reported by the helper; they are never
:: downloaded automatically.
python scripts\ensure_ollama.py
if errorlevel 1 (
    echo [Sarthi] Ollama could not be started. The backend will still launch.
)

:: Start backend.
:: api.py starts Uvicorn on the loopback interface by default.
start "Sarthi Backend" cmd /k python api.py

goto wait

:: ── Background mode: pythonw never opens a console, so no terminal
::    window appears when the backend launches windowless. ──────────
:background
set "PYW=pythonw"
set "PY=python"
if exist "%VENV%\Scripts\python.exe" set "PY=%VENV%\Scripts\python.exe"
"%PY%" scripts\ensure_ollama.py
if errorlevel 1 (
    echo [Sarthi] Ollama could not be started. The backend will still launch.
)
if exist "%VENV%\Scripts\pythonw.exe" set "PYW=%VENV%\Scripts\pythonw.exe"

start "" "%PYW%" -m uvicorn api:app --host %API_HOST% --port %API_PORT%

:wait
:: Wait until the backend is ready.
:: The health check intentionally uses 127.0.0.1 because this tests
:: the backend locally without depending on the LAN interface.
ping -n 2 127.0.0.1 >nul
curl -s http://127.0.0.1:%API_PORT%/health >nul 2>&1
if errorlevel 1 goto wait

call :PrintURLs
exit /b 0

:PrintURLs
echo.
echo ========================================
echo          SARTHI BACKEND
echo ========================================
echo.
echo Local:
echo   http://127.0.0.1:%API_PORT%
echo.

echo.
echo API:
echo   POST /command
echo.
echo Health:
echo   GET /health
echo.
echo Network access is disabled by default because the API has no authentication.
echo.
echo ========================================
echo.

goto :eof

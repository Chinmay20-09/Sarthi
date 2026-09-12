@echo off
setlocal
title Sarthi Backend
cd /d "%~dp0"

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
:: The backend binds to 127.0.0.1:8000 and serves:
::   /command      the client-facing command API (Desktop, Flutter, ...)
::   /ui           the local dashboard
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

:: Start backend (FastAPI on port 8000). No uvicorn reload: a single
:: process dies cleanly with this window, freeing port 8000. For
:: hot-reload while editing use: python api.py --reload
start "Sarthi Backend" cmd /k python api.py

goto wait

:: ── Background mode: pythonw never opens a console, so no terminal
::    window appears when the backend launches windowless. Logging is
::    safe under pythonw because api.py redirects None'd stdio to
::    devnull at import. ─────────────────────────────────────────────
:background
set "PYW=pythonw"
if exist "%VENV%\Scripts\pythonw.exe" set "PYW=%VENV%\Scripts\pythonw.exe"

start "" "%PYW%" -m uvicorn api:app --host 127.0.0.1 --port 8000

:wait
:: Wait until the backend is ready. ping is used instead of `timeout`
:: because `timeout` refuses to run when stdin is not a console.
ping -n 2 127.0.0.1 >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait

echo Sarthi Backend is running at http://127.0.0.1:8000
exit /b 0

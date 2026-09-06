@echo off
setlocal

title Sarthi Launcher
cd /d "%~dp0"

:: ──────────────────────────────────────────────────────────────────
:: MODES
::   start.bat            dev/debug — visible server window
::   start.bat background windowless API (pythonw, no console)
:: ──────────────────────────────────────────────────────────────────

if /i "%~1"=="background" goto background

:: ── Dev mode: activate venv, launch a visible server window so you
::    can watch logs and close Sarthi by closing the window. ─────────
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat" >nul
)

:: Verify Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found.
    pause
    exit /b 1
)

:: Start backend (FastAPI on port 8000). No uvicorn reload: a single
:: process dies cleanly with this window, freeing port 8000. For
:: hot-reload while editing use: python api.py --reload
start "Sarthi API" cmd /k python api.py

goto wait

:: ── Background mode: pythonw never opens a console, so no terminal
::    window appears when Sarthi launches windowless. Logging is safe
::    under pythonw because api.py redirects None'd stdio to devnull
::    at import. ─────────────────────────────────────────────────────
:background
set "PYW=pythonw"
if exist ".venv\Scripts\pythonw.exe" set "PYW=.venv\Scripts\pythonw.exe"

:: Backend — uvicorn directly (no reload, single windowless process)
start "" "%PYW%" -m uvicorn api:app --host 127.0.0.1 --port 8000

:wait
:: Wait until backend is ready. ping is used instead of `timeout` because
:: `timeout` refuses to run when stdin is not a console (e.g. when this
:: batch runs under CREATE_NO_WINDOW in background mode).
ping -n 2 127.0.0.1 >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait

:: Open UI (served by the backend on port 8000)
start "" http://127.0.0.1:8000

exit

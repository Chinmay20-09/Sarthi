@echo off
setlocal

title Sarthi Launcher
cd /d "%~dp0"

:: ──────────────────────────────────────────────────────────────────
:: MODES
::   start.bat            dev/debug — visible server windows (unchanged)
::   start.bat background windowless API/UI for the wake-word flow
::                         (launched by wakeword.py with CREATE_NO_WINDOW)
:: ──────────────────────────────────────────────────────────────────

if /i "%~1"=="background" goto background

:: ── Dev mode: activate venv, launch visible windows so you can watch
::    logs and close Sarthi by closing the windows. ──────────────────
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

:: Start backend (FastAPI on port 8000)
start "Sarthi API" cmd /k python api.py

:: Start frontend (static UI server on port 5500)
start "Sarthi UI" cmd /k python -m http.server 5500 --directory UI

goto wait

:: ── Background mode: pythonw never opens a console, so no terminal
::    windows appear when the wake word launches Sarthi. Logging is safe
::    under pythonw because api.py / utils\run_ui_server.py redirect
::    None'd stdio to devnull at import. ─────────────────────────────
:background
set "PYW=pythonw"
if exist ".venv\Scripts\pythonw.exe" set "PYW=.venv\Scripts\pythonw.exe"

:: Backend — uvicorn directly (no reload, single windowless process)
start "" "%PYW%" -m uvicorn api:app --host 127.0.0.1 --port 8000

:: Frontend — windowless static UI server on port 5500
start "" "%PYW%" "%~dp0utils\run_ui_server.py"

:wait
:: Wait until backend is ready. ping is used instead of `timeout` because
:: `timeout` refuses to run when stdin is not a console (e.g. when this
:: batch runs under CREATE_NO_WINDOW from the wake-word flow).
ping -n 2 127.0.0.1 >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait

:: Open UI (served by the backend on port 8000)
start "" http://127.0.0.1:8000

exit

@echo off
setlocal
title Sarthi Backend
cd /d "%~dp0"

:: Server bind settings — keep in sync with Backend/config.py (API_HOST/API_PORT).
set "API_HOST=0.0.0.0"
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
:: The backend binds to 0.0.0.0:8000 and serves:
::   /command      the client-facing command API (Desktop, Flutter, ...)
::   /ui           the local dashboard
::
:: Local access:
::   http://127.0.0.1:8000
::
:: LAN access:
::   http://<YOUR-LAN-IP>:8000
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

:: Start backend.
:: api.py should start Uvicorn using host 0.0.0.0 and port 8000.
start "Sarthi Backend" cmd /k python api.py

goto wait

:: ── Background mode: pythonw never opens a console, so no terminal
::    window appears when the backend launches windowless. ──────────
:background
set "PYW=pythonw"
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
:: ── Detect the local LAN IPv4 address ─────────────────────────────
set "LAN_IP="

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$ip = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | Select-Object -First 1 -ExpandProperty IPAddress; if ($ip) { $ip }"`) do (
    set "LAN_IP=%%A"
)

if not defined LAN_IP (
    for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | Select-Object -First 1 -ExpandProperty IPAddress; if ($ip) { $ip }"`) do (
        set "LAN_IP=%%A"
    )
)

echo.
echo ========================================
echo          SARTHI BACKEND
echo ========================================
echo.
echo Local:
echo   http://127.0.0.1:%API_PORT%
echo.

if defined LAN_IP (
    echo Network:
    echo   http://%LAN_IP%:%API_PORT%
) else (
    echo Network:
    echo   LAN IP could not be detected.
)

echo.
echo API:
echo   POST /command
echo.
echo Health:
echo   GET /health
echo.
echo If a phone/other device can't connect, allow this port once
:: Run the rule command from an ADMIN terminal (UAC blocks it here):
echo   netsh advfirewall firewall add rule name="Sarthi API" dir=in action=allow protocol=TCP localport=%API_PORT%
echo.
echo ========================================
echo.

goto :eof
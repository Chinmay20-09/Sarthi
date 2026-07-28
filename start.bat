@echo off
setlocal

title Sarthi Launcher
cd /d "%~dp0"

:: Activate virtual environment
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

:: Start backend
start "Sarthi API" cmd /k python api.py

:: Wait until backend is ready
:wait
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait

:: Open UI
start "" http://127.0.0.1:8000/dashboard.html

exit

@echo off
setlocal
title Sarthi Desktop

:: Resolve paths from this script so a Windows shortcut can use any
:: "Start in" directory. Start the backend separately with root start.bat.
set "DESKTOP_DIR=%~dp0"
for %%I in ("%DESKTOP_DIR%..") do set "PROJECT_ROOT=%%~fI"
set "VENV_PYTHONW=%PROJECT_ROOT%\.venv\Scripts\pythonw.exe"
set "VENV_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if exist "%VENV_PYTHONW%" (
    start "" "%VENV_PYTHONW%" "%DESKTOP_DIR%run.py"
    exit /b 0
)

if exist "%VENV_PYTHON%" (
    start "Sarthi Desktop" "%VENV_PYTHON%" "%DESKTOP_DIR%run.py"
    exit /b 0
)

where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%DESKTOP_DIR%run.py"
    exit /b 0
)

:: Keep a console visible in the fallback case so Python startup errors show.
start "Sarthi Desktop" cmd /k python "%DESKTOP_DIR%run.py"

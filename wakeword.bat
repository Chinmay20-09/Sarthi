@echo off
setlocal
title Sarthi Wake Word

cd /d "%~dp0"

:: Prefer the project's virtual environment (absolute paths, so the
:: install/autostart registry entry and the detacher never depend on
:: the caller's working directory — at logon the cwd is System32).
set "PY=python"
set "PYW=pythonw"
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if exist ".venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"

:: HKCU Run key (where the autostart entry lives)
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"

:: Debug mode — run in a visible window so you can watch what it hears
if /i "%~1"=="debug" (
    start "Sarthi Wake Word (debug)" cmd /k ""%PY%" wakeword.py"
    exit /b 0
)

:: Autostart — add/remove a HKCU Run key entry (no admin needed).
:: NOTE: %PYW% is already absolute (set above), so no in-block
:: conversion is needed — cmd expands all %vars% in a parenthesized
:: block at parse time, so a `set` inside the block would not be
:: visible to the reg add on the next line.
if /i "%~1"=="install" (
    reg add "%RUNKEY%" /v "Sarthi Wake Word" /t REG_SZ /d "\"%PYW%\" \"%~dp0wakeword.py\" --supervise" /f >nul
    if errorlevel 1 (
        echo ERROR: could not write the autostart registry entry.
        exit /b 1
    )
    echo Autostart installed - the listener will start windowless at logon.
    echo Remove it anytime with:  wakeword.bat uninstall
    exit /b 0
)

if /i "%~1"=="uninstall" (
    reg delete "%RUNKEY%" /v "Sarthi Wake Word" /f >nul 2>&1
    if errorlevel 1 (
        echo Autostart was not installed.
    ) else (
        echo Autostart removed.
    )
    exit /b 0
)

if /i "%~1"=="status" (
    reg query "%RUNKEY%" /v "Sarthi Wake Word" >nul 2>&1
    if errorlevel 1 (
        echo Autostart is NOT installed.
    ) else (
        echo Autostart IS installed.
    )
    exit /b 0
)

:: Background mode (default) — launch the windowless supervisor and exit.
start "" /b "%PY%" -c "import subprocess,sys; subprocess.Popen([r'%PYW%', r'%~dp0wakeword.py', '--supervise', '--log-file', r'%~dp0logs\wakeword.log'], creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); sys.exit(0)"
exit /b 0

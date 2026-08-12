@echo off
setlocal
title Sarthi Wake Word

cd /d "%~dp0"

:: Prefer the project's virtual environment
set "PY=python"
set "PYW=pythonw"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist ".venv\Scripts\pythonw.exe" set "PYW=.venv\Scripts\pythonw.exe"

:: HKCU Run key (where the autostart entry lives)
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"

:: Debug mode — run in a visible window so you can watch what it hears
if /i "%~1"=="debug" (
    start "Sarthi Wake Word (debug)" cmd /k ""%PY%" wakeword.py"
    exit /b 0
)

:: Autostart — add/remove a HKCU Run key entry (no admin needed).
:: The entry launches pythonw DIRECTLY (fully windowless — no console
:: flash at logon) with --supervise, which runs the tray listener as a
:: child and restarts it if it ever crashes.
if /i "%~1"=="install" (
    if "%PYW:~0,1%"=="." set "PYW=%~dp0%PYW%"
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
:: A tiny intermediate python.exe "double-detaches" the real supervisor:
::   - `start "" /b` returns immediately (a bare `"%PYW%" wakeword.py ...`
::     would block, because cmd.exe WAITS for pythonw.exe, and `start ""`
::     without the detacher would let pythonw inherit the caller's stdio
::     pipe, blocking scripted `cmd /c wakeword.bat` callers forever).
::   - the intermediate respawns the supervisor with DEVNULL stdio and
::     CREATE_NO_WINDOW, so it holds no console and no caller pipe, then
::     exits in ~0.2s.
:: The supervisor (wakeword.py --supervise) owns the restart watchdog;
:: the tray listener runs as its child and shows the tray icon. A
:: deliberate stop (tray Exit) or a duplicate-listener exit (codes 2/3)
:: stop the supervisor — no endless restart loop.
start "" /b "%PY%" -c "import subprocess,sys; subprocess.Popen([r'%PYW%', r'%~dp0wakeword.py', '--supervise', '--log-file', r'%~dp0logs\wakeword.log'], creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); sys.exit(0)"
exit /b 0

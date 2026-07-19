@echo off
title Sarthi — AI Desktop Assistant
cd /d "%~dp0"

echo  ╔══════════════════════════════════════╗
echo  ║        🧠  Sarthi Hyperion           ║
echo  ║    AI Desktop Assistant Launcher     ║
echo  ╚══════════════════════════════════════╝
echo.

:: ── Activate virtual environment if available ──────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo   [✓] Virtual environment activated
) else (
    echo   [!] No .venv found — using system Python
)
echo.

:: ── Install dependencies if missing ────────────────────────────────────────
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo   [~] Installing dependencies...
    pip install fastapi uvicorn
    echo.
)

:: ── Start API server ──────────────────────────────────────────────────────
echo   [~] Starting API server on http://127.0.0.1:8000
echo.
start "Sarthi API" /B python api.py

:: ── Wait for server to be ready ────────────────────────────────────────────
echo   [~] Waiting for server to respond...
set retries=0
:waitloop
set /a retries+=1
if %retries% gtr 15 (
    echo   [!] Server did not start within 30 seconds.
    echo   [!] Try running "python api.py" manually to see errors.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8000 >nul 2>&1
if errorlevel 1 goto waitloop

echo   [✓] API server is ready!
echo.

:: ── Open UI in browser ────────────────────────────────────────────────────
echo   [~] Opening dashboard in browser...
start "" "UI\dashboard.html"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   ✅  Sarthi is running              ║
echo  ║                                      ║
echo  ║   API:  http://127.0.0.1:8000        ║
echo  ║   Docs: http://127.0.0.1:8000/docs   ║
echo  ║   UI:   UI/dashboard.html            ║
echo  ║                                      ║
echo  ║   Close this window to stop          ║
echo  ╚══════════════════════════════════════╝
echo.
echo   Press Ctrl+C to stop the server.
echo.

:: ── Keep window open ──────────────────────────────────────────────────────
echo.
echo   Press any key to stop Sarthi and close this window.
pause >nul

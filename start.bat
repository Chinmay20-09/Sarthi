@echo off
setlocal
title Sarthi Launcher
cd /d "%~dp0"

:: ──────────────────────────────────────────────────────────────────
:: Root convenience launcher.
::
:: The real launcher is Backend\sarthi.bat (see it for modes). This file
:: just delegates to it so starting Sarthi from the repository root
:: keeps working exactly as before.
::
::   start.bat            dev/debug — visible server window
::   start.bat background windowless API (pythonw, no console)
:: ──────────────────────────────────────────────────────────────────

call "%~dp0Backend\sarthi.bat" %*

:: Open the UI (served by the backend on port 8000)
start "" http://127.0.0.1:8000
exit

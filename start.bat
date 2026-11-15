@echo off
setlocal
title Sarthi Launcher
cd /d "%~dp0"

:: ──────────────────────────────────────────────────────────────────
:: Root convenience launcher.
::
:: The real launcher is Backend\sarthi.bat (see it for modes). This file
:: starts the backend from the repository root. Start the desktop GUI
:: separately with: python Desktop\run.py
::
::   start.bat            dev/debug — visible server window
::   start.bat background windowless API (pythonw, no console)
:: ──────────────────────────────────────────────────────────────────

call "%~dp0Backend\sarthi.bat" %*
exit

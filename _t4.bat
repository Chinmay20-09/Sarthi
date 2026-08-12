@echo off
echo BEFORE4
start "" pythonw -c "import time; time.sleep(60)" >nul 2>&1
echo AFTER4
exit /b 0

@echo off
echo BEFORE_START2
start "" ".venv\Scripts\pythonw.exe" -c "import time; time.sleep(3)"
echo AFTER_START2

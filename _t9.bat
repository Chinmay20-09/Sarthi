@echo off
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
set "PYW=.venv\Scripts\pythonw.exe"
start "" /b "%PY%" -c "import subprocess,sys; subprocess.Popen([r'%PYW%', r'C:\Sarthi\_t9_child.py'], creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); sys.exit(0)"
echo DONE9

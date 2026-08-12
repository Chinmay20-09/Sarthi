@echo off
start "" pythonw -c "import sys; sys.stdout.write('PIPEOUT\n'); sys.stdout.flush(); import time; time.sleep(2)" > _t5_out.txt 2>&1
echo DONE
exit /b 0

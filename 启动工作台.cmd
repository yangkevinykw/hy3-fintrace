@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
echo FinTrace: http://127.0.0.1:8765
python scripts/serve_batch_workbench.py
pause

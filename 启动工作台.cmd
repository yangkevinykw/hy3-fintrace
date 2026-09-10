@echo off
cd /d "%~dp0"
echo FinTrace: http://127.0.0.1:8765
python scripts/serve_batch_workbench.py
pause

@echo off
setlocal
cd /d "%~dp0"
if not exist "instance-demo\credentials.json" (
  echo No existing demo instance. Read docs/local-demo.md first.
  pause
  exit /b 1
)
set "MCSA_INSTANCE=%~dp0instance-demo"
".venv\Scripts\python.exe" start.py --reset-password
pause

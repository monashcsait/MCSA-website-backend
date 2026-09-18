@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "MCSA_PY=python") else (set "MCSA_PY=py")
if not exist ".venv\Scripts\python.exe" (
  %MCSA_PY% -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import flask,waitress,PIL,opencc" >nul 2>nul
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe start.py
pause
exit /b
:failed
echo Setup failed. Install Python 3.10 or newer and check your internet connection.
pause

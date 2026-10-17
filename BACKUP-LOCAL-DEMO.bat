@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" local_demo.py backup
if errorlevel 1 (
  echo Backup failed. Keep the existing data and inspect the message above.
) else (
  echo Full private backup saved in demo-backups. Do not upload this folder.
)
pause

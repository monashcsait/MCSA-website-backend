@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. Follow docs/local-demo.md to prepare it.
  pause
  exit /b 1
)
echo Keep this window open during the demonstration. Ctrl+C stops it.
echo CMS: http://127.0.0.1:18091/admin.html
echo Website: http://127.0.0.1:18091/site/
".venv\Scripts\python.exe" local_demo.py serve
pause

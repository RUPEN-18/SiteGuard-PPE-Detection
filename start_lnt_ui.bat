@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create the environment using README.md or setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X faulthandler -u "app_lnt.py"
if errorlevel 1 pause

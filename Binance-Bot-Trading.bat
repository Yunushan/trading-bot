@echo off
setlocal
pushd %~dp0
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  pause
  exit /b 1
)
python "%~dp0main.py"
popd

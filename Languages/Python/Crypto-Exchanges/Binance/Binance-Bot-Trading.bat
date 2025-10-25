@echo off
setlocal ENABLEEXTENSIONS
set "BASE_DIR=%~dp0"
pushd "%BASE_DIR%"

set "VENV_PY=.venv\Scripts\python.exe"
set "PYTHON_CMD="
set "RUN_PY="

if exist "%VENV_PY%" (
    set "RUN_PY=%VENV_PY%"
    goto ENSURE_DEPS
)

call :DETECT_PYTHON
if not defined PYTHON_CMD (
    call :INSTALL_PYTHON
)
if not defined PYTHON_CMD (
    echo Failed to locate or install Python. Please install Python 3.11 or newer and run this launcher again.
    pause
    goto END
)

"%PYTHON_CMD%" -m venv .venv >nul 2>&1
if errorlevel 1 (
    echo Virtual environment creation failed.
    pause
    goto END
)
set "RUN_PY=%VENV_PY%"

:ENSURE_DEPS
if not defined RUN_PY (
    if exist "%VENV_PY%" (
        set "RUN_PY=%VENV_PY%"
    ) else (
        set "RUN_PY=%PYTHON_CMD%"
    )
)
"%RUN_PY%" -m pip install --upgrade pip >nul
if exist requirements.txt (
    echo Installing required Python packages...
    "%RUN_PY%" -m pip install -r requirements.txt
)

echo Starting Binance Trading Bot...
"%RUN_PY%" "%BASE_DIR%main.py"

:END
popd
endlocal
exit /b 0

:DETECT_PYTHON
where python >nul 2>&1
if %errorlevel%==0 (
    for /f "delims=" %%P in ('where python') do (
        set "PYTHON_CMD=%%P"
        goto DETECT_DONE
    )
)
py -3 -c "import sys; print(sys.executable)" >"%TEMP%\_py_path.txt" 2>nul
if exist "%TEMP%\_py_path.txt" (
    set /p PYTHON_CMD=<"%TEMP%\_py_path.txt"
    del "%TEMP%\_py_path.txt" >nul 2>&1
)
:DETECT_DONE
exit /b 0

:INSTALL_PYTHON
echo Python not detected. Attempting to download Python 3.12...
set "PY_SETUP=%TEMP%\python-installer.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.5/python-3.12.5-amd64.exe' -OutFile '%PY_SETUP%'" >nul 2>&1
if not exist "%PY_SETUP%" (
    echo Download failed. Please install Python manually.
    exit /b 0
)
"%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 SimpleInstall=1 SimpleInstallShortcuts=0 >nul 2>&1
if errorlevel 1 (
    echo Python installer reported an error. Please install Python manually.
    del "%PY_SETUP%" >nul 2>&1
    exit /b 0
)
del "%PY_SETUP%" >nul 2>&1
where python >nul 2>&1
if %errorlevel%==0 (
    for /f "delims=" %%P in ('where python') do (
        set "PYTHON_CMD=%%P"
        goto INSTALL_DONE
    )
)
:INSTALL_DONE
exit /b 0

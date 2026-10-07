@echo off
setlocal
cd /d "%~dp0"
if exist "%USERPROFILE%\miniconda3\envs\pyqt\pythonw.exe" (
    start "" "%USERPROFILE%\miniconda3\envs\pyqt\pythonw.exe" "%~dp0main.py" %*
    exit /b
)
call conda run --no-capture-output -n pyqt python main.py %*
if errorlevel 1 pause

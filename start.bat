@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    py -3 bootstrap.py %*
    if errorlevel 1 pause
    exit /b
)
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    python bootstrap.py %*
    if errorlevel 1 pause
    exit /b
)
echo Python 3.10+ was not found.
echo Install Python from https://www.python.org/downloads/ and enable Add Python to PATH.
echo Or use the portable Windows package, which needs no Python or Conda.
pause
exit /b 1

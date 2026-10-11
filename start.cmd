@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
if not exist "frontend\dist\index.html" goto missing
".venv\Scripts\python.exe" scripts\launch.py %*
exit /b %errorlevel%
:missing
echo Run setup.cmd first to install dependencies and build the frontend.
exit /b 1

@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python_missing
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.lock
if errorlevel 1 goto failed
pushd frontend
call npm.cmd ci
if errorlevel 1 goto frontend_failed
popd
".venv\Scripts\python.exe" scripts\generate_contracts.py
if errorlevel 1 goto failed
pushd frontend
call npm.cmd run build
if errorlevel 1 goto frontend_failed
popd
if not exist .env copy /y .env.example .env >nul
echo.
echo Setup complete. Run start.cmd. Optional: add OPENAI_API_KEY to .env.
exit /b 0
:frontend_failed
popd
:failed
echo Setup failed. Review the error above. Python 3.12 and Node 24 are required.
exit /b 1
:python_missing
echo Install Python 3.12 with the Windows Python launcher, then retry.
exit /b 1

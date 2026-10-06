@echo off
rem Shared first-run setup for the run*.bat launchers: Python check, .venv and
rem dependencies - the minimum needed to open the app. The app itself then
rem downloads the engine and the model, showing progress in its own window.
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ from https://python.org and re-run this file.
    exit /b 1
)

if not exist ".venv\.deps-ok" (
    echo Preparing EchoNote for the first time - about a minute, only once.
    echo The app opens by itself when this finishes.
    if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
    if errorlevel 1 exit /b 1
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 exit /b 1
    echo ok> ".venv\.deps-ok"
)

exit /b 0

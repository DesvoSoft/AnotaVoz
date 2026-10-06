@echo off
rem Shared first-run setup for the run*.bat launchers: Python check, .venv,
rem dependencies and the pinned whisper binaries (tools\setup_binaries.py).
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ from https://python.org and re-run this file.
    exit /b 1
)

if not exist ".venv\.deps-ok" (
    echo Setting up EchoNote for the first time, this only happens once...
    if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
    if errorlevel 1 exit /b 1
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 exit /b 1
    echo ok> ".venv\.deps-ok"
)

if not exist "core\whisper\whisper-cli.exe" (
    echo Fetching the transcription engine...
    ".venv\Scripts\python.exe" tools\setup_binaries.py
    if errorlevel 1 exit /b 1
)
exit /b 0

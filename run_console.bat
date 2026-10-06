@echo off
setlocal
cd /d "%~dp0"

call "%~dp0_bootstrap.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 pause

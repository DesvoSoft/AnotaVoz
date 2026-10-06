@echo off
setlocal
cd /d "%~dp0"

call "%~dp0_bootstrap.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

rem pythonw = no console window; this one closes as soon as the app is launched.
rem Output goes to %APPDATA%\AnotaVoz\anotavoz.log. Use run_console.bat to debug.
start "" ".venv\Scripts\pythonw.exe" -m app.webgui

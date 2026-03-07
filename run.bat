@echo off
set "SCRIPT_DIR=%~dp0"
start "" /min /D "%SCRIPT_DIR%" cmd /c "set PYTHONIOENCODING=utf-8 && "%SCRIPT_DIR%.venv\Scripts\pythonw.exe" "%SCRIPT_DIR%main.py" > "%SCRIPT_DIR%error.log" 2>&1"


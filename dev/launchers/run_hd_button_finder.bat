@echo off
REM Button finder: finds where the game keeps the controller buttons (for the L1 item box). READ-ONLY.
REM Hold L1 + press Home (3 times)   Nothing held + Page Up (3 times)   End = finish
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_button_finder.py
echo.
pause

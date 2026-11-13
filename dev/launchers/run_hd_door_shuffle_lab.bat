@echo off
REM Door shuffle lab (WRITES game memory, doors only): tests ladder / lift / cross-area redirects for the door randomiser. Use a spare save.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_door_shuffle_lab.py
echo.
pause

@echo off
REM Steam version: identify the game and show Jill's inventory live.
REM Start Resident Evil HD Remaster and load a save first.
REM Output is also saved to hd_inventory_output.txt. Close this window to stop.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_inventory.py --watch
echo.
pause

@echo off
REM Steam version: show Jill's inventory AND the item box live.
REM Load a save first. Output is also saved to hd_inventory_output.txt. Close this window to stop.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_inventory.py --watch --box
echo.
pause

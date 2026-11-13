@echo off
REM Stack test: Ctrl+1..7 each put one pickup-sized stack of an ammo type (or ink ribbons) in the item box.
REM Ctrl+0 = 250 handgun bullets in one slot. Close the window to stop.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_stack_test.py
echo.
pause

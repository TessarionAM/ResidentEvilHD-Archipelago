@echo off
REM Jill position finder (READ-ONLY): finds where the game keeps Jill's x/y/z, for the Key Map.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_jill_position_finder.py
echo.
pause

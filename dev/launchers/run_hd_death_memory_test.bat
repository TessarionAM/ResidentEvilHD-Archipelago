@echo off
REM Death and reload memory test (read-only): what the game changes on death and load; door unlock flags.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_death_memory_test.py
echo.
pause

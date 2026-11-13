@echo off
REM Lock lab (testing helper for the door lock randomiser). Type commands in this window. WRITES door locks / inventory (memory only).
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_lock_lab.py
echo.
pause

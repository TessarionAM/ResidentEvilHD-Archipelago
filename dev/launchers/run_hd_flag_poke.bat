@echo off
REM Flag poke (testing helper): sets a candidate "Chris scene seen" flag. WRITES to the game (memory only).
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_flag_poke.py
echo.
pause

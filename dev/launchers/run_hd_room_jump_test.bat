@echo off
REM Room jump test (WRITES): F10 moves Jill straight to the next room in your list, without a door.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_room_jump_test.py
echo.
pause

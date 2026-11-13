@echo off
REM Door teleport (testing helper): F10 makes every door in your room lead to the room you pick (default 50b = Lab B3 Cell Entrance).
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_door_teleport.py
echo.
pause

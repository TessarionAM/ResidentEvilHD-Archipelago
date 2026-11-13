@echo off
REM Wrong Door test v5: F9 = every door in your room leads to the Dark Corridor (far away),
REM F10 = to the Lab B3 Cell. From there every door leads back. WRITES to the game's door data (in memory only).
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_wrong_door_test.py
echo.
pause

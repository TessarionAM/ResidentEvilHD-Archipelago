@echo off
REM Event recorder (read-only except F8). While playing, press right after doing something:
REM Insert = enemy killed  Home = typewriter  Page Up = file
REM Delete = puzzle  End = story / boss  Page Down = health change
REM F8 = put 6 shotgun shells in the item box
REM Close the window to stop.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_event_recorder.py
echo.
pause

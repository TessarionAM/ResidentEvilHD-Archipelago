@echo off
REM Door scanner tour (testing helper): F9 sends you to the closest room the door scanner still needs. Run the door scanner at the same time.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_scanner_tour.py
echo.
pause

@echo off
REM Scene flag finder (READ-ONLY): finds the "Chris cutscene seen" flag for the Wrong Door trap.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_scene_flag_finder.py
echo.
pause

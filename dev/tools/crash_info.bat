@echo off
REM If the game crashes or closes: saves Windows' own records of what went wrong in the last
REM 2 hours (errors from any program, plus Windows Error Reporting) to crash_info.txt. READ-ONLY.
REM Attach crash_info.txt to your bug report.
cd /d "%~dp0.."
powershell -NoProfile -Command "$since=(Get-Date).AddHours(-2); $e=Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$since} -ErrorAction SilentlyContinue | Where-Object { $_.LevelDisplayName -in 'Error','Critical' -or $_.ProviderName -like '*Error Reporting*' -or $_.Message -like '*bhd*' }; if ($e) { $e | Format-List TimeCreated, ProviderName, Id, Message | Out-File -Encoding utf8 -Width 300 crash_info.txt } else { 'No error records in the last 2 hours. The game closed without Windows logging a crash.' | Out-File -Encoding utf8 crash_info.txt }"
type crash_info.txt
echo.
echo Saved to crash_info.txt
pause

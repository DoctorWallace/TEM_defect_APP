@echo off
setlocal
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0select_target.ps1" -Mode restore
set "restore_exit=%ERRORLEVEL%"
echo.
pause
exit /b %restore_exit%

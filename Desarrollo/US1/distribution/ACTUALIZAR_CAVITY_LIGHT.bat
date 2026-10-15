@echo off
setlocal
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0select_target.ps1" -Mode apply
set "update_exit=%ERRORLEVEL%"
echo.
pause
exit /b %update_exit%

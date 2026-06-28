@echo off
setlocal
cd /d "%~dp0.."
if "%~1"=="" goto usage
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git_push.ps1" -Message "%*"
goto end
:usage
powershell -NoProfile -Command "Write-Host ''; Write-Host 'Usage: git_daily_push.bat \"commit message\"'; Write-Host 'Example: git_daily_push.bat \"fix: description\"'; Write-Host ''"
pause
exit /b 1
:end
pause

@echo off
rem Double-cliquer pour arreter SmartCampus AI. Options : arreter.bat -Supprimer | -Docker
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0arreter.ps1" %*
echo.
pause

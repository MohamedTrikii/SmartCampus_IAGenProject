@echo off
rem Double-cliquer pour lancer SmartCampus AI. Options : demarrer.bat -Fake | -Modele gemma2:2b | -Gpu | -Synchro | -Arreter
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0demarrer.ps1" %*
echo.
pause

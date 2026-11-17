@echo off
rem Startet Backend + Frontend (Doppelklick). Optional: start_pdvm.bat backend|frontend
set TARGET=%1
if "%TARGET%"=="" set TARGET=all
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_pdvm.ps1" -Target %TARGET%
echo.
pause

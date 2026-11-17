@echo off
rem Beendet Backend + Frontend. Optional: stop_pdvm.bat backend|frontend
set TARGET=%1
if "%TARGET%"=="" set TARGET=all
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_pdvm.ps1" -Target %TARGET%
echo.
pause

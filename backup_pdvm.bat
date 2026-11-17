@echo off
rem Sichert alle Datenbanken nach database\backups\stand_<Commit>_<Zeit>. Optional: backup_pdvm.bat <Name>
if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0database\scripts\backup_all_databases.ps1"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0database\scripts\backup_all_databases.ps1" -Label %1
)
echo.
pause

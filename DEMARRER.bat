@echo off
cd /d "%~dp0"
title LEAKSOURCE INVESTIGATOR 3.1
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 app.py
) else (
    python app.py
)
if errorlevel 1 (
  echo.
  echo Impossible de demarrer. Lance d'abord INSTALLER.bat puis reessaie.
  pause
)

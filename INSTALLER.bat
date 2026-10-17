@echo off
cd /d "%~dp0"
title LEAKSOURCE - Installation dependances
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 -m pip install -r requirements.txt
) else (
    python -m pip install -r requirements.txt
)
echo.
echo Installation terminee, sauf erreur ci-dessus.
pause

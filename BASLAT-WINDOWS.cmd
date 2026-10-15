@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js 22 veya ustunu https://nodejs.org adresinden kurun.
  pause
  exit /b 1
)
echo Tarayicida http://localhost:3000 adresini acin.
node server.js
pause

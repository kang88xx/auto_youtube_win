@echo off
rem Render only: jobs\<id> (script.json + audio + assets) -> jobs\<id>\render\final.mp4.  render.bat jobs\_sample
if "%~1"=="" set "JOB=jobs\_sample"
if not "%~1"=="" set "JOB=%~1"
wsl.exe --cd "%~dp0" -e pipeline/wsl.sh pipeline/render.sh "%JOB%"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" echo [render.bat] failed with code %RC%
echo "%cmdcmdline%" | findstr /i /c:"%~nx0" >nul && pause
exit /b %RC%

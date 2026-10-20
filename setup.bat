@echo off
rem Environment setup inside WSL2.  setup.bat (full)  /  setup.bat --check (verify only)
wsl.exe --cd "%~dp0" -e pipeline/wsl.sh bash setup.sh %*
set RC=%ERRORLEVEL%
echo "%cmdcmdline%" | findstr /i /c:"%~nx0" >nul && pause
exit /b %RC%

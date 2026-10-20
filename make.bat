@echo off
rem Topic -> video, run from Windows (uses WSL2 Ubuntu).  make.bat "<topic>" [job-id]
if "%~1"=="" (
  echo usage: make.bat "<topic>" [job-id]
  echo        set SCRIPT_ARGS=--no-web   ^(skip web search, test mode^)
  echo        set TTS_ENGINE=voicebox    ^(default: edge^)
  goto :end
)
wsl.exe --cd "%~dp0" -e pipeline/wsl.sh env SCRIPT_ARGS="%SCRIPT_ARGS%" TTS_ENGINE="%TTS_ENGINE%" QA_RETRY="%QA_RETRY%" pipeline/make.sh %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" echo [make.bat] failed with code %RC%
:end
echo "%cmdcmdline%" | findstr /i /c:"%~nx0" >nul && pause
exit /b %RC%

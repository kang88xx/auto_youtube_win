@echo off
rem Remotion preview studio. Opens http://localhost:3000 in the Windows browser. Ctrl+C to stop.
start "" /min cmd /c "timeout /t 8 /nobreak >nul && start "" http://localhost:3000"
wsl.exe --cd "%~dp0" -e pipeline/wsl.sh bash -c "cd render && npm run dev -- --no-open"

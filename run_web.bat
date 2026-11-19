@echo off
REM Solara in the browser, from this folder's code, on the desktop app's own data: the same customers, files and
REM settings. For confirming a change without building the installer.
REM One Solara at a time: close the desktop app first. When the change is confirmed, build the installer and go back.
setlocal
cd /d "%~dp0"
set "SOLARA_DATA=%APPDATA%\solara-desktop\data"
set SOLARA_MODE=live
set SOLARA_SINGLE_OWNER=1

echo.
echo   Solara (web) - this folder's code on the desktop app's data
echo   ------------------------------------------------------------
echo.

python -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1',8900)) else 1)"
if errorlevel 1 (
  echo   Solara is already running on this computer ^(the desktop app?^). Close it, then run this again.
  pause & exit /b 1
)

python tools\helper_sync.py
echo.
echo   Starting on http://127.0.0.1:8900   data: %SOLARA_DATA%
echo   Leave this window open. Close it to stop Solara.
echo.
start "" /b cmd /c "ping -n 4 127.0.0.1 >nul & start http://127.0.0.1:8900"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
if errorlevel 1 (
  echo.
  echo   Solara stopped with an error. The lines above say why.
  pause
)
endlocal

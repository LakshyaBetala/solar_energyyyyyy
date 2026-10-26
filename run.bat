@echo off
REM Solara - one click start. Installs what is missing, then opens the console.
setlocal
cd /d "%~dp0"

echo.
echo   Solara - solar back office
echo   --------------------------
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo   Python was not found on PATH. Install Python 3.11 or newer and run this again.
  pause & exit /b 1
)

echo   Checking dependencies...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo   Dependency install failed. Run: python -m pip install -r requirements.txt
  pause & exit /b 1
)

python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()" >nul 2>nul
if errorlevel 1 (
  echo   Downloading the browser Playwright drives, this happens once...
  python -m playwright install chromium
)

echo   Starting on http://127.0.0.1:8900
start "" http://127.0.0.1:8900
python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
endlocal

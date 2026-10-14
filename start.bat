@echo off
setlocal
cd /d "%~dp0"
if not defined PORT set "PORT=8787"

if not exist "backend\.venv\Scripts\python.exe" (echo Not set up yet - run setup.bat first. & goto :fail)
if not exist "frontend\dist\index.html" (echo The frontend has not been built - run setup.bat first. & goto :fail)
if not exist ".env" (echo .env is missing - run setup.bat first. & goto :fail)

rem The key can come from .env or from a real environment variable.
if not defined OPENROUTER_MANAGEMENT_KEY (
    findstr /r /b /c:"OPENROUTER_MANAGEMENT_KEY=." ".env" >nul 2>&1
    if errorlevel 1 (echo OPENROUTER_MANAGEMENT_KEY is not set in .env & goto :fail)
)
findstr /r /b /c:"DASHBOARD_PASSWORD_HASH=." ".env" >nul 2>&1
if errorlevel 1 (echo No dashboard login in .env - run setup.bat to create one. & goto :fail)

echo Starting the dashboard on http://127.0.0.1:%PORT%  (press Ctrl+C to stop)
echo.
cd backend
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
if errorlevel 1 (
    echo.
    echo The server stopped with an error. If the port is in use, run:  set "PORT=8788" ^&^& start.bat
    goto :fail
)
exit /b 0

:fail
echo.
pause
exit /b 1

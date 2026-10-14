@echo off
setlocal
cd /d "%~dp0"
echo === OpenRouter Usage Dashboard - setup ===
echo.

where python >nul 2>&1 || (echo [ERROR] Python was not found. Install Python 3.10 or newer and tick "Add python.exe to PATH". & goto :fail)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" || (echo [ERROR] Python 3.10 or newer is required. & goto :fail)
where npm >nul 2>&1 || (echo [ERROR] Node.js / npm was not found. Install Node.js 20 or newer. & goto :fail)

echo [1/4] Python environment and packages
if not exist "backend\.venv\Scripts\python.exe" (
    python -m venv "backend\.venv" || goto :fail
)
"backend\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "backend\requirements.txt" || goto :fail

echo [2/4] Frontend packages
pushd frontend
call npm install --no-fund --no-audit || (popd & goto :fail)

echo [3/4] Building the frontend
call npm run build || (popd & goto :fail)
popd

echo [4/4] Checking .env
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo     Created .env from .env.example
)
set "MISSING="
findstr /r /b /c:"OPENROUTER_MANAGEMENT_KEY=." ".env" >nul 2>&1 || (set "MISSING=1" & echo     - OPENROUTER_MANAGEMENT_KEY is not set)

findstr /r /b /c:"DASHBOARD_PASSWORD_HASH=." ".env" >nul 2>&1
if errorlevel 1 (
    echo.
    echo No dashboard login yet - create one now:
    pushd backend
    ".venv\Scripts\python.exe" -m app.set_login || (popd & goto :fail)
    popd
)

echo.
if defined MISSING (
    echo Setup finished, but .env still needs the value listed above.
    echo Edit .env, then run start.bat.
) else (
    echo Setup finished. Run start.bat to launch the dashboard.
    echo To change the login later:  cd backend ^&^& .venv\Scripts\python -m app.set_login
)
echo.
pause
exit /b 0

:fail
echo.
echo Setup failed - see the messages above.
pause
exit /b 1

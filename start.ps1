# Starts the dashboard on http://127.0.0.1:8787 (builds the frontend first if needed).
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

if (-not (Test-Path "$root\backend\.venv")) {
    python -m venv "$root\backend\.venv"
    & "$root\backend\.venv\Scripts\python.exe" -m pip install -r "$root\backend\requirements.txt"
}
if (-not (Test-Path "$root\frontend\dist\index.html")) {
    Push-Location "$root\frontend"
    try {
        if (-not (Test-Path node_modules)) { npm install }
        npm run build
    } finally { Pop-Location }
}

Push-Location "$root\backend"
try {
    & "$root\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8787
} finally { Pop-Location }

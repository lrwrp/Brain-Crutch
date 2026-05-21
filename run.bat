@echo off
REM Bootstrap + launch the ADHD assistant on Windows.
REM First run creates .venv\, installs deps, then starts the server and
REM opens the browser. Subsequent runs skip setup.

setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is required. Install with:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo Then re-run this script.
    exit /b 1
)

if not exist .venv (
    echo Setting up virtualenv (one-time)...
    uv venv --python 3.11 || exit /b 1
)

uv pip install --quiet -r requirements.txt || exit /b 1

echo Starting on http://localhost:1440 - Ctrl-C to stop.
start "" "http://localhost:1440"
.venv\Scripts\python.exe server.py

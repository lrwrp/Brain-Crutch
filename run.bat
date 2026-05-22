@echo off
REM Bootstrap + launch the ADHD assistant on Windows.
REM `uv run` reads pyproject.toml + uv.lock, materializes .venv on
REM first launch, then starts the server. No separate install step.

setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is required. Install with:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo Then re-run this script.
    exit /b 1
)

echo Starting on http://localhost:1440 - Ctrl-C to stop.
start "" "http://localhost:1440"
uv run --no-dev python server.py

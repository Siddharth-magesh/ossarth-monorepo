@echo off
REM OSSARTH - Windows Launch Script
REM Run from the REPO ROOT: os_customization\launch.bat

setlocal

REM Switch terminal to UTF-8 code page
chcp 65001 >nul 2>&1

REM Tell Python to use UTF-8 for all I/O
set PYTHONUTF8=1

REM Resolve the repo root (parent of the directory this .bat lives in)
set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."
cd /d "%REPO_ROOT%"

REM Check .env exists in repo root
if not exist ".env" (
    echo [ERROR] .env file not found in %REPO_ROOT%
    echo Copy .env.example to .env and fill in your GROQ_API_KEY.
    exit /b 1
)

REM Check Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [OSSARTH] Virtual environment activated.
) else (
    echo [OSSARTH] No venv found - using system Python.
    echo           Run: python -m venv venv
    echo           Then: venv\Scripts\activate
    echo           Then: pip install -r requirements.txt
)

REM Create logs directory
if not exist "logs" mkdir logs

REM Check if Ollama is running (non-blocking)
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [OSSARTH] WARNING: Ollama not detected on localhost:11434
    echo           Start Ollama: ollama serve
    echo           Or set OSSARTH_LLM_PROVIDER=groq in .env to use Groq instead.
    echo.
) else (
    echo [OSSARTH] Ollama detected.
)

REM Start dashboard server in background
echo [OSSARTH] Starting dashboard server on port 8000...
start "OSSARTH Dashboard" /B python -X utf8 -m uvicorn dashboard.server:app --host 0.0.0.0 --port 8000 --log-level warning > logs\dashboard.log 2>&1

REM Wait for dashboard to be ready
timeout /t 3 /nobreak >nul

REM Open browser
start http://localhost:8000

echo [OSSARTH] Dashboard available at http://localhost:8000
echo [OSSARTH] Starting OSSARTH daemon (REPL)...
echo.

REM Start the REPL in foreground
python -X utf8 -m mas_core.agent_runner %*

REM Cleanup dashboard on exit
echo.
echo [OSSARTH] Shutting down dashboard...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1

echo [OSSARTH] Shutdown complete.
endlocal

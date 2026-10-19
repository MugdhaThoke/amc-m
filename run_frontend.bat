@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo ============================================================
echo   AMC Context Engineering -- React Frontend Launcher
echo ============================================================
echo.

cd /d "%ROOT%\mf-context-engine"

if not exist "node_modules" (
    echo [INFO] node_modules not found. Running npm install...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

echo [INFO] Starting Vite development server...
echo [INFO] Frontend: http://localhost:5173
echo.
call npm run dev
endlocal

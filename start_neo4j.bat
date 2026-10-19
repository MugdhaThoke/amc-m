@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   Starting Neo4j Graph Database
echo ============================================================

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

:: Check if Neo4j is already running and listening on port 7687
netstat -ano 2>nul | findstr /C:":7687 " | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Neo4j is already running and listening on port 7687 (bolt://localhost:7687)
    pause
    exit /b 0
)

:: Auto-locate Neo4j binary
set "NEO4J_BAT="

:: Check standard Neo4jDesktop2 path
if exist "%USERPROFILE%\.Neo4jDesktop2\Data\dbmss" (
    for /d %%d in ("%USERPROFILE%\.Neo4jDesktop2\Data\dbmss\*") do (
        if exist "%%d\bin\neo4j.bat" set "NEO4J_BAT=%%d\bin\neo4j.bat"
    )
)

if "%NEO4J_BAT%"=="" if exist "%USERPROFILE%\.Neo4jDesktop2\Cache\dbmss" (
    for /d %%d in ("%USERPROFILE%\.Neo4jDesktop2\Cache\dbmss\*") do (
        if exist "%%d\bin\neo4j.bat" set "NEO4J_BAT=%%d\bin\neo4j.bat"
    )
)

if "%NEO4J_BAT%"=="" if exist "%ROOT%\neo4j\bin\neo4j.bat"          set "NEO4J_BAT=%ROOT%\neo4j\bin\neo4j.bat"
if "%NEO4J_BAT%"=="" if exist "%ROOT%\neo4j_local\bin\neo4j.bat"    set "NEO4J_BAT=%ROOT%\neo4j_local\bin\neo4j.bat"
if "%NEO4J_BAT%"=="" if exist "C:\neo4j\bin\neo4j.bat"             set "NEO4J_BAT=C:\neo4j\bin\neo4j.bat"
if "%NEO4J_BAT%"=="" if exist "C:\Program Files\Neo4j\bin\neo4j.bat" set "NEO4J_BAT=C:\Program Files\Neo4j\bin\neo4j.bat"

if "%NEO4J_BAT%"=="" (
    echo [ERROR] Could not automatically locate Neo4j binary.
    echo Please install Neo4j or ensure it is running in Docker: docker compose up -d neo4j
    pause
    exit /b 1
)

echo [OK] Found Neo4j at: %NEO4J_BAT%
echo Starting Neo4j console...
call "%NEO4J_BAT%" console
endlocal

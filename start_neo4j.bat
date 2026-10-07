@echo off
setlocal

echo ============================================================
echo   Starting Neo4j Graph Database
echo ============================================================

set "NEO4J_HOME=%USERPROFILE%\.Neo4jDesktop2\Data\dbmss\dbms-49637bb0-9857-4a15-80ce-c71aa9f2ed6b"
set "NEO4J_BIN=%NEO4J_HOME%\bin\neo4j.bat"

if not exist "%NEO4J_BIN%" (
    echo [ERROR] Neo4j binary not found at: %NEO4J_BIN%
    pause
    exit /b 1
)

netstat -ano 2>nul | findstr /C:":7687 " | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Neo4j is already running and listening on port 7687 (bolt://localhost:7687)
    pause
    exit /b 0
)

echo Starting Neo4j console...
call "%NEO4J_BIN%" console
endlocal

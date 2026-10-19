@echo off
setlocal EnableDelayedExpansion

set "ROOT=%~dp0.."
set "LOG_DIR=%ROOT%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "NEO4J_BAT="
if exist "%USERPROFILE%\.Neo4jDesktop2\Data\dbmss" (
    for /d %%d in ("%USERPROFILE%\.Neo4jDesktop2\Data\dbmss\*") do (
        if exist "%%d\bin\neo4j.bat" set "NEO4J_BAT=%%d\bin\neo4j.bat"
    )
)
if "%NEO4J_BAT%"=="" if exist "C:\neo4j\bin\neo4j.bat" set "NEO4J_BAT=C:\neo4j\bin\neo4j.bat"
if "%NEO4J_BAT%"=="" if exist "C:\Program Files\Neo4j\bin\neo4j.bat" set "NEO4J_BAT=C:\Program Files\Neo4j\bin\neo4j.bat"

if "%NEO4J_BAT%"=="" (
    echo [ERROR] Neo4j binary not found.
    exit /b 1
)

echo [INFO] Starting Neo4j from: %NEO4J_BAT%
call "%NEO4J_BAT%" console > "%LOG_DIR%\neo4j.log" 2>&1
endlocal

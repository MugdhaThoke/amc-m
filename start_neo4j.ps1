# ===========================================================================
# Copyright (c) NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Start Neo4j Database for AMC Context Engineering POC
# ===========================================================================

$NEO4J_HOME = "$HOME\.Neo4jDesktop2\Data\dbmss\dbms-49637bb0-9857-4a15-80ce-c71aa9f2ed6b"
$NEO4J_BIN = "$NEO4J_HOME\bin\neo4j.bat"

if (-not (Test-Path $NEO4J_BIN)) {
    Write-Error "Neo4j binary not found at: $NEO4J_BIN"
    exit 1
}

$portCheck = netstat -ano 2>&1 | Select-String ":7687 .*LISTENING"
if ($portCheck) {
    Write-Host "[Neo4j] Already running and listening on bolt://localhost:7687" -ForegroundColor Green
    exit 0
}

Write-Host "[Neo4j] Starting Neo4j server..." -ForegroundColor Cyan
Write-Host "[Neo4j] Home: $NEO4J_HOME" -ForegroundColor DarkGray

& $NEO4J_BIN console

@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%\mf-context-engine"
echo ============================================================
echo   Starting MF Context Engine (React Frontend)
echo   Local URL: http://localhost:5173
echo ============================================================
call npx vite --host 0.0.0.0 --port 5173
popd
endlocal

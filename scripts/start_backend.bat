@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%\backend"

set "PYTHON_EXE=python"
if exist ".\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=.\.venv\Scripts\python.exe"
) else if exist "..\streamlit_app\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\streamlit_app\.venv\Scripts\python.exe"
)

echo ============================================================
echo   Starting ContextGraph Backend API
echo   Swagger Docs: http://localhost:8000/docs
echo   Health Status: http://localhost:8000/api/health
echo ============================================================
call "%PYTHON_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
popd
endlocal

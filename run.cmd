@echo off
pushd "%~dp0" || exit /b 1
set "VENV_PY=%~dp0\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo Cannot find repository virtual environment at %VENV_PY%
    popd
    exit /b 1
)
"%VENV_PY%" "%~dp0update.py"
popd

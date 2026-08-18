@echo off
REM ============================================================
REM  Lanzador de NetScan (nuevo CLI)
REM  - Usa el entorno virtual backend\.venv
REM  - Se auto-eleva a Administrador (necesario para el ARP scan)
REM  - Ejemplos: netscan.bat scan --full | netscan.bat serve | netscan.bat caps
REM ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permisos de Administrador...
    powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
set "PY=%~dp0backend\.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo ERROR: no existe el entorno virtual. Ejecuta primero:
    echo   python -m venv backend\.venv
    echo   backend\.venv\Scripts\pip install -e backend
    pause
    exit /b 1
)

if "%~1"=="" (
    "%PY%" -m netscan.cli scan --full
) else (
    "%PY%" -m netscan.cli %*
)

echo.
pause

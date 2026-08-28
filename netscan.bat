@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  Lanzador de NetScan (nuevo CLI)
REM  - Usa el entorno virtual backend\.venv
REM  - Se auto-eleva a Administrador (necesario para el ARP scan)
REM  - 'doctor', 'caps' y '--help'/'-h' no necesitan privilegios,
REM    igual que en netscan.sh.
REM  - Ejemplos: netscan.bat up | netscan.bat scan --full | netscan.bat doctor
REM  - Sin argumentos lanza 'up' (API + dashboard + navegador)
REM ============================================================

set "CMD1=%~1"
if "%CMD1%"=="" set "CMD1=up"
set "NEEDS_ADMIN=1"
if /i "%CMD1%"=="doctor" set "NEEDS_ADMIN=0"
if /i "%CMD1%"=="caps" set "NEEDS_ADMIN=0"
if /i "%CMD1%"=="--help" set "NEEDS_ADMIN=0"
if /i "%CMD1%"=="-h" set "NEEDS_ADMIN=0"

if "%NEEDS_ADMIN%"=="1" (
    net session >nul 2>&1
    if !errorlevel! neq 0 (
        echo Solicitando permisos de Administrador...
        powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
        exit /b
    )
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
    "%PY%" -m netscan.cli up
) else (
    "%PY%" -m netscan.cli %*
)

echo.
pause

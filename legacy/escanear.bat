@echo off
REM ============================================================
REM  Lanzador de NetScan
REM  - Usa Python310 (donde estan scapy, rich, etc.)
REM  - Se auto-eleva a Administrador (necesario para el ARP scan)
REM  - Pasa cualquier argumento al script (ej: escanear.bat --full)
REM ============================================================

REM --- Auto-elevacion a Administrador ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permisos de Administrador...
    powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

REM --- Ejecutar el escaner ---
cd /d "%~dp0"
set "PY=%LocalAppData%\Programs\Python\Python310\python.exe"

if not exist "%PY%" (
    echo ERROR: No se encontro Python310 en:
    echo   %PY%
    pause
    exit /b 1
)

REM Si no se pasan argumentos, escaneo completo por defecto
if "%~1"=="" (
    "%PY%" netscan.py --full
) else (
    "%PY%" netscan.py %*
)

echo.
pause

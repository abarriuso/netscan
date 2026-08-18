@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  NetScan — instalador completo (un solo comando)
REM
REM  Uso:  install.bat                 instala todo lo esencial
REM        install.bat --with-nuclei   + nuclei (auditoria web; AV puede
REM                                     marcarlo como falso positivo)
REM
REM  Instala TODO lo necesario:
REM   1. Entorno Python + backend (netscan CLI + API)
REM   2. Herramientas externas via winget: nmap, RustScan (+ Npcap si falta)
REM   3. Dependencias del frontend (dashboard)
REM
REM  Algunos pasos pediran elevacion (UAC) — acepta y listo.
REM ============================================================

cd /d "%~dp0"
set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"

echo.
echo ============================================================
echo   NetScan installer
echo ============================================================
echo.

REM --- 1. Python + backend ------------------------------------
echo [1/4] Comprobando Python 3.11+...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no encontrado. Instala Python 3.11+ desde https://python.org
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: se necesita Python 3.11 o superior.
    python --version
    pause
    exit /b 1
)

echo [1/4] Creando entorno virtual e instalando el backend...
if not exist "%VENV_PY%" (
    python -m venv backend\.venv
    if %errorlevel% neq 0 goto :error
)
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -e backend
if %errorlevel% neq 0 goto :error
echo       Backend OK.

REM --- 2. Herramientas externas (winget) ----------------------
echo.
echo [2/4] Instalando herramientas externas (nmap, RustScan, nuclei)...
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo       winget no esta disponible — se omiten las herramientas externas.
    echo       NetScan funcionara con degradacion elegante ^(escaneo interno^).
    goto :frontend
)

where nmap >nul 2>&1
if %errorlevel% neq 0 (
    echo       Instalando nmap...
    winget install --id Insecure.Nmap --silent --accept-package-agreements --accept-source-agreements
) else (
    echo       nmap ya instalado.
)

where rustscan >nul 2>&1
if %errorlevel% neq 0 (
    echo       Instalando RustScan...
    winget install --id bee-san.RustScan --silent --accept-package-agreements --accept-source-agreements
) else (
    echo       RustScan ya instalado.
)

REM --- nuclei: OPT-IN. Windows Defender lo marca como falso positivo     ---
REM --- (Trojan:Win32/Sonbokli.A!cl) porque es una herramienta de           ---
REM --- auditoria. El binario oficial esta verificado por SHA256 contra     ---
REM --- la release de ProjectDiscovery (ver scripts/verify-nuclei.ps1).     ---
REM --- Para instalarlo: install.bat --with-nuclei                          ---
if /i "%~1"=="--with-nuclei" (
    where nuclei >nul 2>&1
    if !errorlevel! neq 0 (
        echo       Instalando nuclei ^(no esta en winget; descarga directa^)...
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-nuclei.ps1"
        echo       nuclei instalado en %%LOCALAPPDATA%%\NetScan\bin ^(reinicia el terminal para el PATH^).
    ) else (
        echo       nuclei ya instalado.
    )
) else (
    echo       nuclei OMITIDO ^(opt-in: install.bat --with-nuclei^).
)

REM Npcap (necesario para el ARP scan en Windows; nmap suele traerlo)
sc query npcap | find "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo       Instalando Npcap ^(driver de captura para el ARP scan^)...
    winget install --id Insecure.Npcap --silent --accept-package-agreements --accept-source-agreements
) else (
    echo       Npcap OK.
)

REM --- 3. Frontend --------------------------------------------
:frontend
echo.
echo [3/4] Instalando dependencias del dashboard...
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo       npm no encontrado — instala Node.js 20+ para el dashboard.
    echo       El backend y la CLI funcionan sin el.
    goto :verify
)
cd frontend
call npm install --no-audit --no-fund
if %errorlevel% neq 0 (
    cd ..
    goto :error
)
cd ..
echo       Frontend OK.

REM --- 4. Verificacion ----------------------------------------
:verify
echo.
echo [4/4] Verificando capacidades...
"%VENV_PY%" -m netscan.cli caps

echo.
echo ============================================================
echo   Instalacion completa.
echo.
echo   CLI:       netscan.bat scan --full
echo   Servidor:  netscan.bat serve      ^(API en :8600^)
echo   Dashboard: cd frontend ^&^& npm run dev
echo ============================================================
pause
exit /b 0

:error
echo.
echo ERROR: la instalacion ha fallado. Revisa los mensajes anteriores.
pause
exit /b 1

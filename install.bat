@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  NetScan — instalador completo (un solo comando)
REM
REM  Uso:  install.bat             instala TODO (recomendado)
REM        install.bat --minimal  solo backend + frontend,
REM                               sin herramientas externas
REM
REM  Instala TODO lo necesario:
REM   1. Python 3.12 (via winget, si falta)
REM   2. Entorno virtual + backend (netscan CLI + API)
REM   3. Herramientas externas: nmap, RustScan, Npcap y nuclei
REM   4. Node.js LTS (via winget, si falta) + deps del dashboard
REM
REM  Algunos pasos pediran elevacion (UAC) — acepta y listo.
REM ============================================================

cd /d "%~dp0"
set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"
set "MINIMAL=0"
if /i "%~1"=="--minimal" set "MINIMAL=1"

echo.
echo ============================================================
echo   NetScan installer
echo ============================================================
echo.

REM --- 1. Python ----------------------------------------------
echo [1/5] Comprobando Python 3.11+...
set "PYBOOT="

REM Si el venv ya existe y es 3.11+, no hace falta tocar el Python del sistema
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        echo       Entorno virtual existente OK.
        goto :backend
    )
    echo       El entorno virtual usa un Python antiguo; se recrea.
    rmdir /s /q backend\.venv
)

where python >nul 2>&1
if !errorlevel! equ 0 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "PYBOOT=python"
)
if not defined PYBOOT (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        py -3.12 -c "import sys" >nul 2>&1 && set "PYBOOT=py -3.12"
        if not defined PYBOOT (
            py -3.11 -c "import sys" >nul 2>&1 && set "PYBOOT=py -3.11"
        )
    )
)
if not defined PYBOOT (
    echo       Python 3.11+ no encontrado ^(o es demasiado viejo^). Instalando Python 3.12 con winget...
    where winget >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: instala Python 3.11+ desde https://python.org y reintenta.
        pause
        exit /b 1
    )
    winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    echo.
    echo Python 3.12 instalado. Cierra esta ventana y vuelve a ejecutar install.bat
    echo ^(el PATH de esta sesion no se actualiza solo^).
    pause
    exit /b 0
)
echo       Python OK: %PYBOOT%

REM --- 2. Backend ---------------------------------------------
:backend
echo.
echo [2/5] Creando entorno virtual e instalando el backend...
if not exist "%VENV_PY%" (
    %PYBOOT% -m venv backend\.venv
    if !errorlevel! neq 0 goto :error
)
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -e backend
if !errorlevel! neq 0 goto :error
echo       Backend OK.

REM --- 3. Herramientas externas -------------------------------
echo.
if "%MINIMAL%"=="1" (
    echo [3/5] Herramientas externas OMITIDAS ^(modo --minimal^).
    goto :refresh_path
)
echo [3/5] Instalando herramientas externas ^(nmap, RustScan, Npcap, nuclei^)...
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo       winget no esta disponible — se omiten las herramientas externas.
    echo       NetScan funcionara con degradacion elegante ^(escaneo interno^).
    goto :refresh_path
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

REM Npcap (driver de captura para el ARP scan en Windows)
sc query npcap | find "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo       Instalando Npcap...
    winget install --id Insecure.Npcap --silent --accept-package-agreements --accept-source-agreements
) else (
    echo       Npcap OK.
)

REM nuclei: Windows Defender puede marcarlo como falso positivo
REM (Trojan:Win32/Sonbokli.A!cl) por ser herramienta de auditoria.
REM El binario se verifica por SHA256 contra la release oficial de
REM ProjectDiscovery antes de instalarse (scripts\install-nuclei.ps1).
REM Si Defender lo pone en cuarentena, el resto de NetScan sigue OK.
where nuclei >nul 2>&1
if %errorlevel% neq 0 (
    echo       Instalando nuclei ^(verificado por SHA256^)...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-nuclei.ps1"
    if !errorlevel! neq 0 (
        echo       AVISO: nuclei no se pudo instalar ^(posible cuarentena del antivirus^).
        echo       NetScan funciona sin el; la auditoria web quedara desactivada.
    ) else (
        echo       nuclei instalado en %%LOCALAPPDATA%%\NetScan\bin.
    )
) else (
    echo       nuclei ya instalado.
)

REM --- Refrescar PATH con lo que haya instalado winget --------
:refresh_path
for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
if defined SYS_PATH if defined USR_PATH set "PATH=!SYS_PATH!;!USR_PATH!"

REM --- 4. Node.js + frontend ----------------------------------
echo.
echo [4/5] Instalando dependencias del dashboard...
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo       Node.js no encontrado. Instalando Node LTS con winget...
    where winget >nul 2>&1
    if !errorlevel! neq 0 (
        echo       winget no disponible: instala Node.js 20+ desde https://nodejs.org
        echo       y reintenta. El backend y la CLI funcionan sin el.
        goto :verify
    )
    winget install --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
    for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
    for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
    if defined SYS_PATH if defined USR_PATH set "PATH=!SYS_PATH!;!USR_PATH!"
    where npm >nul 2>&1
    if !errorlevel! neq 0 (
        echo       Node instalado pero el PATH no se refresco.
        echo       Cierra esta ventana y vuelve a ejecutar install.bat para el dashboard.
        goto :verify
    )
)
cd frontend
call npm install --no-audit --no-fund
if !errorlevel! neq 0 (
    cd ..
    goto :error
)
cd ..
echo       Frontend OK.

REM --- 5. Verificacion ----------------------------------------
:verify
echo.
echo [5/5] Verificando capacidades...
"%VENV_PY%" -m netscan.cli caps

echo.
echo ============================================================
echo   Instalacion completa.
echo.
echo   CLI:       netscan.bat scan --full
echo   Servidor:  netscan.bat serve      ^(API en :8600^)
echo   Dashboard: cd frontend
echo              npm run dev
echo ============================================================
pause
exit /b 0

:error
echo.
echo ERROR: la instalacion ha fallado. Revisa los mensajes anteriores.
pause
exit /b 1

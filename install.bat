@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  NetScan — instalador completo (un solo comando)
REM
REM  Uso:  install.bat             instala TODO (recomendado)
REM        install.bat --minimal  solo backend + frontend,
REM                               sin herramientas externas
REM        install.bat --run      instala Y lanza todo (netscan up)
REM
REM  Instala TODO lo necesario:
REM   1. Python 3.12 (via winget, si falta)
REM   2. Entorno virtual + backend (netscan CLI + API)
REM   3. Herramientas externas: nmap, RustScan, Npcap y nuclei
REM   4. Node.js LTS (via winget, si falta) + build del dashboard
REM
REM  Algunos pasos pediran elevacion (UAC) — acepta y listo.
REM ============================================================

cd /d "%~dp0"
set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"
set "MINIMAL=0"
set "RUNAFTER=0"
for %%A in (%*) do (
    if /i "%%~A"=="--minimal" set "MINIMAL=1"
    if /i "%%~A"=="--run" set "RUNAFTER=1"
)

echo.
echo ============================================================
echo   NetScan installer
echo ============================================================
echo.

REM --- 1. Python ----------------------------------------------
echo [1/5] Checking Python 3.11+...
set "PYBOOT="

REM Si el venv ya existe y es 3.11+, no hace falta tocar el Python del sistema
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        echo       Existing virtual environment OK.
        goto :backend
    )
    echo       The virtual environment uses an old Python; recreating it.
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
    echo       Python 3.11+ not found ^(or too old^). Installing Python 3.12 with winget...
    where winget >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: install Python 3.11+ from https://python.org and try again.
        pause
        exit /b 1
    )
    winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    echo.
    echo Python 3.12 installed. Close this window and run install.bat again
    echo ^(this session's PATH does not update by itself^).
    pause
    exit /b 0
)
echo       Python OK: %PYBOOT%

REM --- 2. Backend ---------------------------------------------
:backend
echo.
echo [2/5] Creating the virtual environment and installing the backend...
if not exist "%VENV_PY%" (
    %PYBOOT% -m venv backend\.venv
    if !errorlevel! neq 0 goto :error
)
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -e backend
if !errorlevel! neq 0 goto :error
echo       Backend OK.

REM --- 3. Herramientas externas -------------------------------
echo.
if "%MINIMAL%"=="1" (
    echo [3/5] External tools SKIPPED ^(--minimal^).
    goto :refresh_path
)
echo [3/5] Installing external tools ^(nmap, RustScan, Npcap, nuclei^)...
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo       winget is not available - skipping the external tools.
    echo       NetScan will degrade gracefully ^(built-in scanning^).
    goto :refresh_path
)

where nmap >nul 2>&1
if %errorlevel% neq 0 (
    echo       Installing nmap...
    winget install --id Insecure.Nmap --silent --accept-package-agreements --accept-source-agreements
) else (
    echo       nmap already installed.
)

where rustscan >nul 2>&1
if %errorlevel% neq 0 (
    echo       Installing RustScan...
    winget install --id bee-san.RustScan --silent --accept-package-agreements --accept-source-agreements
) else (
    echo       RustScan already installed.
)

REM Npcap (driver de captura para el ARP scan en Windows)
sc query npcap | find "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo       Installing Npcap...
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
    echo       Installing nuclei ^(SHA256-verified^)...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-nuclei.ps1"
    if !errorlevel! neq 0 (
        echo       WARNING: nuclei could not be installed ^(possibly quarantined by the antivirus^).
        echo       NetScan works without it; the web audit will be disabled.
    ) else (
        echo       nuclei installed in %%LOCALAPPDATA%%\NetScan\bin.
    )
) else (
    echo       nuclei already installed.
)

REM --- Refrescar PATH con lo que haya instalado winget --------
:refresh_path
for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
if defined SYS_PATH if defined USR_PATH set "PATH=!SYS_PATH!;!USR_PATH!"

REM --- 4. Node.js + frontend ----------------------------------
echo.
echo [4/5] Installing the dashboard dependencies...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo       Node.js not found. Installing Node LTS with winget...
    where winget >nul 2>&1
    if !errorlevel! neq 0 (
        echo       winget not available: install Node.js 20+ from https://nodejs.org
        echo       and try again. The backend and the CLI work without it.
        goto :verify
    )
    winget install --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
    for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
    for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
    if defined SYS_PATH if defined USR_PATH set "PATH=!SYS_PATH!;!USR_PATH!"
    where node >nul 2>&1
    if !errorlevel! neq 0 (
        echo       Node installed but the PATH was not refreshed.
        echo       Close this window and run install.bat again for the dashboard.
        goto :verify
    )
)
cd frontend
set COREPACK_ENABLE_DOWNLOAD_PROMPT=0
call corepack pnpm install
if !errorlevel! neq 0 (
    cd ..
    goto :error
)
echo       Building the dashboard ^(pnpm run build^)...
call corepack pnpm run build
if !errorlevel! neq 0 (
    echo       WARNING: the dashboard build failed; the API will work without the built-in UI.
)
cd ..
echo       Frontend OK.

REM --- 5. Verificacion ----------------------------------------
:verify
echo.
echo [5/5] Verifying...
"%VENV_PY%" -m netscan.cli doctor

echo.
echo ============================================================
echo   Installation complete.
echo.
echo   Everything at once: netscan.bat up      ^(API + dashboard + browser^)
echo   API only:            netscan.bat serve
echo   Scan:                netscan.bat scan --full
echo   Speed test:          netscan.bat speedtest
echo   Diagnosis:           netscan.bat doctor
echo ============================================================

if "%RUNAFTER%"=="1" (
    echo.
    echo Starting NetScan...
    call "%~dp0netscan.bat" up
    exit /b 0
)
if "%NETSCAN_NONINTERACTIVE%"=="1" exit /b 0
pause
exit /b 0

:error
echo.
echo ERROR: the installation failed. Check the messages above.
if "%NETSCAN_NONINTERACTIVE%"=="1" exit /b 1
pause
exit /b 1

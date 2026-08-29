#!/usr/bin/env bash
# ============================================================
#  NetScan — instalador para Linux / macOS (un solo comando)
#
#  Uso:
#    ./install.sh              instala backend + dashboard + deps
#    ./install.sh --run        instala Y lanza todo (netscan up)
#    ./install.sh --minimal    sin herramientas externas (nmap, etc.)
#    ./install.sh --system     instala servicio systemd + comando global
#
#  Deja NetScan listo para:
#    ./netscan.sh up      -> API + dashboard + navegador (un comando)
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# NOT backend/.venv: on WSL that path is often the SAME directory as the
# Windows-native venv (repo checked out on the Windows filesystem, seen
# from WSL as /mnt/c/...). A Windows venv (.exe launchers) and a Linux venv
# (bin/python symlinks) cannot share one directory — installing one over
# the other corrupts both. Keep them fully separate.
VENV="$ROOT/backend/.venv-linux"
PY="$VENV/bin/python"
if [ -f "$ROOT/backend/.venv/Scripts/python.exe" ] && [ ! -e "$VENV" ]; then
  c_yellow() { printf '\033[33m%s\033[0m\n' "$1"; }
  c_yellow "Aviso: backend/.venv ya existe y parece un venv de Windows (tiene Scripts/python.exe)."
  c_yellow "Este instalador usa backend/.venv-linux en su lugar, así que no lo toca. Ignora este aviso si es la primera vez que ves esto."
fi

MINIMAL=0
RUN=0
SYSTEM=0
for arg in "$@"; do
  case "$arg" in
    --minimal) MINIMAL=1 ;;
    --run)     RUN=1 ;;
    --system)  SYSTEM=1 ;;
    *) echo "Opción desconocida: $arg"; exit 1 ;;
  esac
done

c_green() { printf '\033[32m%s\033[0m\n' "$1"; }
c_cyan()  { printf '\033[36m%s\033[0m\n' "$1"; }
c_yellow(){ printf '\033[33m%s\033[0m\n' "$1"; }

echo "============================================================"
c_cyan "  NetScan installer (Linux/macOS)"
echo "============================================================"

# --- 1. Python -----------------------------------------------
echo; c_cyan "[1/5] Comprobando Python 3.11+..."
PYBOOT=""
for cand in python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
      PYBOOT="$cand"; break
    fi
  fi
done
if [ -z "$PYBOOT" ]; then
  c_yellow "Python 3.11+ no encontrado. Intentando instalarlo..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y python3 python3-venv python3-pip
    PYBOOT=python3
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip && PYBOOT=python3
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm python python-pip && PYBOOT=python3
  elif command -v brew >/dev/null 2>&1; then
    brew install python@3.12 && PYBOOT=python3.12
  else
    echo "ERROR: instala Python 3.11+ manualmente y reintenta."; exit 1
  fi
fi
c_green "      Python OK: $($PYBOOT --version)"

# --- 2. Backend ----------------------------------------------
echo; c_cyan "[2/5] Creando entorno virtual e instalando el backend..."
if [ ! -x "$PY" ]; then
  if ! "$PYBOOT" -m venv "$VENV" 2>/tmp/netscan-venv-err.$$; then
    # Typical Debian/Ubuntu failure: python3 present but the venv/ensurepip
    # module lives in a separate "pythonX.Y-venv" package that isn't
    # installed. Install it and retry — but don't just retry once and let
    # a second failure kill the whole install under `set -e`: very new
    # Python releases (e.g. Ubuntu 26.04 shipping 3.14) can have the venv
    # package split differently than expected, or ensurepip itself broken
    # even once the OS package is present. Try progressively, and only
    # fail hard if every fallback is exhausted.
    if grep -qi "ensurepip is not available\|No module named venv" /tmp/netscan-venv-err.$$ 2>/dev/null \
       && command -v apt-get >/dev/null 2>&1; then
      PYVER="$("$PYBOOT" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
      c_yellow "      Falta el paquete de venv para Python $PYVER; instalando..."
      sudo apt-get update -y || true
      # Nombre versionado y genérico: en algunas versiones solo existe uno
      # de los dos, o el paquete versionado se llama distinto de lo
      # esperado — instalar los dos que existan, ignorar el que falle.
      sudo apt-get install -y "python${PYVER}-venv" || true
      sudo apt-get install -y python3-venv || true

      if "$PYBOOT" -m venv "$VENV" 2>/tmp/netscan-venv-err.$$; then
        rm -f /tmp/netscan-venv-err.$$
      elif grep -qi "ensurepip is not available" /tmp/netscan-venv-err.$$ 2>/dev/null; then
        # venv module itself now works (creates the dir/activate scripts)
        # but bundling pip via ensurepip still fails — sidestep ensurepip
        # entirely instead of chasing the exact missing OS package further.
        c_yellow "      Seguía sin poder instalar pip vía ensurepip; creando el venv sin pip y arrancándolo a mano..."
        rm -f /tmp/netscan-venv-err.$$
        "$PYBOOT" -m venv --without-pip "$VENV"
        if ! "$PY" -m ensurepip --upgrade 2>/dev/null; then
          curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.$$.py
          "$PY" /tmp/get-pip.$$.py
          rm -f /tmp/get-pip.$$.py
        fi
      else
        cat /tmp/netscan-venv-err.$$ >&2
        rm -f /tmp/netscan-venv-err.$$
        exit 1
      fi
    else
      cat /tmp/netscan-venv-err.$$ >&2
      rm -f /tmp/netscan-venv-err.$$
      exit 1
    fi
  fi
  rm -f /tmp/netscan-venv-err.$$
fi
"$PY" -m pip install --upgrade pip
# No --quiet: pip install here pulls scapy/cryptography/fastapi/uvicorn and
# friends, and on WSL2 against a /mnt/c/... path (cross-filesystem 9P I/O)
# this can take a couple of minutes. Silent output looks exactly like a
# hang; showing pip's normal progress avoids that.
"$PY" -m pip install -e "$ROOT/backend"
c_green "      Backend OK."

# --- 3. Herramientas externas --------------------------------
echo
if [ "$MINIMAL" = "1" ]; then
  c_yellow "[3/5] Herramientas externas OMITIDAS (--minimal)."
else
  c_cyan "[3/5] Instalando herramientas externas (nmap, masscan, whatweb, testssl.sh, RustScan, nuclei)..."
  install_tool() {
    command -v "$1" >/dev/null 2>&1 && { echo "      $1 ya instalado."; return; }
    if   command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y "$2" || true
    elif command -v dnf     >/dev/null 2>&1; then sudo dnf install -y "$2" || true
    elif command -v pacman  >/dev/null 2>&1; then sudo pacman -Sy --noconfirm "$2" || true
    elif command -v brew    >/dev/null 2>&1; then brew install "$2" || true
    else c_yellow "      No sé instalar $1 en este sistema; se omite (degradación elegante)."; fi
  }

  # Package-manager tools: same as install.bat's winget set, plus the two
  # that only exist on Linux (whatweb, testssl.sh have no Windows build).
  install_tool nmap nmap
  install_tool masscan masscan
  install_tool whatweb whatweb
  install_tool testssl.sh testssl.sh
  if ! command -v testssl.sh >/dev/null 2>&1; then
    # Not every distro's repo ships it (package name/version varies) — the
    # upstream repo always works and is what the README's manual steps use.
    c_cyan "      testssl.sh no estaba en los repos; clonando desde GitHub..."
    git clone --depth 1 -q https://github.com/drwetter/testssl.sh.git /tmp/testssl.sh.$$ 2>/dev/null \
      && sudo ln -sf /tmp/testssl.sh.$$/testssl.sh /usr/local/bin/testssl.sh \
      || c_yellow "      No se pudo instalar testssl.sh; se omite (degradación elegante)."
  fi

  # RustScan and nuclei: no apt/dnf/pacman package exists anywhere. Same
  # approach as Windows' verified nuclei download (see
  # scripts/install-nuclei.ps1) — grab the latest GitHub release binary.
  # amd64/x86_64 only; other architectures degrade gracefully.
  ARCH="$(uname -m)"
  if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
    if ! command -v rustscan >/dev/null 2>&1; then
      c_cyan "      Instalando RustScan..."
      # bee-san/RustScan (the RustScan/RustScan API path 301-redirects here).
      # Only Linux release asset is rustscan.deb.zip — a zip CONTAINING a
      # .deb, not a .deb itself (verified against a real release, not
      # guessed from the filename).
      ZIP_URL="$( (curl -sL https://api.github.com/repos/bee-san/RustScan/releases/latest \
        | grep -o '"browser_download_url": *"[^"]*rustscan\.deb\.zip"' | cut -d'"' -f4 | head -1) || true )"
      if [ -n "$ZIP_URL" ] && command -v dpkg >/dev/null 2>&1 && command -v unzip >/dev/null 2>&1; then
        ( curl -sL -o /tmp/rustscan.$$.zip "$ZIP_URL" \
          && unzip -oq /tmp/rustscan.$$.zip -d /tmp/rustscan.$$ \
          && sudo dpkg -i /tmp/rustscan.$$/*.deb >/dev/null 2>&1 \
          && rm -rf /tmp/rustscan.$$.zip /tmp/rustscan.$$ ) || true
      fi
      if ! command -v rustscan >/dev/null 2>&1 && command -v cargo >/dev/null 2>&1; then
        c_cyan "      dpkg no disponible; instalando RustScan vía cargo..."
        cargo install rustscan || true
      fi
      command -v rustscan >/dev/null 2>&1 \
        && c_green "      RustScan OK." \
        || c_yellow "      No se pudo instalar RustScan; se omite (degradación elegante)."
    else
      echo "      RustScan ya instalado."
    fi

    if ! command -v nuclei >/dev/null 2>&1; then
      c_cyan "      Instalando nuclei..."
      ZIP_URL="$( (curl -s https://api.github.com/repos/projectdiscovery/nuclei/releases/latest \
        | grep -o '"browser_download_url": *"[^"]*linux_amd64\.zip"' | cut -d'"' -f4 | head -1) || true )"
      if [ -n "$ZIP_URL" ] && command -v unzip >/dev/null 2>&1; then
        ( curl -sL -o /tmp/nuclei.$$.zip "$ZIP_URL" \
          && unzip -oq /tmp/nuclei.$$.zip -d /tmp/nuclei.$$ \
          && sudo install -m 755 /tmp/nuclei.$$/nuclei /usr/local/bin/nuclei \
          && rm -rf /tmp/nuclei.$$.zip /tmp/nuclei.$$ ) || true
      fi
      command -v nuclei >/dev/null 2>&1 \
        && c_green "      nuclei OK." \
        || c_yellow "      No se pudo instalar nuclei; se omite (degradación elegante)."
    else
      echo "      nuclei ya instalado."
    fi
  else
    c_yellow "      RustScan/nuclei: solo hay binario amd64 en GitHub; arquitectura $ARCH no soportada, se omiten."
  fi
fi

# --- 4. Node.js + dashboard ----------------------------------
echo; c_cyan "[4/5] Instalando y compilando el dashboard..."
if command -v npm >/dev/null 2>&1; then
  # npm install es fatal (como en install.bat); un fallo en el build del
  # dashboard NO debe abortar el resto de la instalación (degradación
  # elegante: la API sigue funcionando sin UI integrada), así que se
  # comprueba fuera de una cadena '&&' para no disparar 'set -e'.
  if ! ( cd "$ROOT/frontend" && npm install --no-audit --no-fund ); then
    echo "ERROR: fallo instalando dependencias del dashboard (npm install)." >&2
    exit 1
  fi
  if ( cd "$ROOT/frontend" && npm run build ); then
    c_green "      Dashboard compilado (frontend/dist)."
  else
    c_yellow "      AVISO: el build del dashboard falló; la API funcionará sin UI integrada."
  fi
else
  c_yellow "      Node/npm no encontrado. El backend y la CLI funcionan sin el dashboard."
  c_yellow "      Instala Node 20+ (https://nodejs.org) y ejecuta: ./netscan.sh up --build"
fi

# --- 5. Servicio del sistema (opcional) ----------------------
echo; c_cyan "[5/5] Verificando..."
"$PY" -m netscan.cli doctor || true

if [ "$SYSTEM" = "1" ]; then
  echo; c_cyan "Instalando comando global y servicio web (systemd)..."
  sudo ln -sf "$VENV/bin/netscan" /usr/local/bin/netscan

  # Fichero de entorno del servicio web: bind a toda la LAN + token generado.
  if [ ! -f /etc/netscan/netscan.env ]; then
    TOKEN="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')"
    sudo mkdir -p /etc/netscan
    sudo bash -c "cat > /etc/netscan/netscan.env" <<EOF
# Configuración del servicio web NetScan (leída por systemd)
# Escucha en toda la red local para servir el dashboard como servicio web.
NETSCAN_API_HOST=0.0.0.0
NETSCAN_API_PORT=8600
# Token requerido al exponer la API fuera de localhost. Cámbialo si quieres.
NETSCAN_API_TOKEN=$TOKEN
EOF
    sudo chmod 640 /etc/netscan/netscan.env
    c_green "      Config del servicio: /etc/netscan/netscan.env"
    c_yellow "      Token de la API: $TOKEN"
    c_yellow "      (guárdalo: lo necesita el dashboard al exponerlo en la LAN)"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    SERVICE=/etc/systemd/system/netscan.service
    sudo bash -c "sed 's#@ROOT@#$ROOT#g; s#@VENV@#$VENV#g' '$ROOT/packaging/linux/netscan.service' > '$SERVICE'"
    sudo systemctl daemon-reload
    sudo systemctl enable --now netscan.service || true
    IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    c_green "      Servicio netscan.service activo (systemctl status netscan)."
    c_green "      Dashboard web:  http://${IP:-<ip-del-servidor>}:8600/"
  fi
  # Lanzador de escritorio
  if [ -d "$HOME/.local/share/applications" ] || mkdir -p "$HOME/.local/share/applications" 2>/dev/null; then
    sed "s#@VENV@#$VENV#g; s#@ROOT@#$ROOT#g" "$ROOT/packaging/linux/netscan.desktop" \
      > "$HOME/.local/share/applications/netscan.desktop" 2>/dev/null || true
  fi
fi

echo
echo "============================================================"
c_green "  Instalación completa."
echo
echo "   Un comando para todo:   ./netscan.sh up"
echo "   Solo API:               ./netscan.sh serve"
echo "   Speed test:             ./netscan.sh speedtest"
echo "   Diagnóstico:            ./netscan.sh doctor"
echo "============================================================"

if [ "$RUN" = "1" ]; then
  echo; c_cyan "Lanzando NetScan..."
  exec "$ROOT/netscan.sh" up
fi

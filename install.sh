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
VENV="$ROOT/backend/.venv"
PY="$VENV/bin/python"

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
  "$PYBOOT" -m venv "$VENV"
fi
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -e "$ROOT/backend"
c_green "      Backend OK."

# --- 3. Herramientas externas --------------------------------
echo
if [ "$MINIMAL" = "1" ]; then
  c_yellow "[3/5] Herramientas externas OMITIDAS (--minimal)."
else
  c_cyan "[3/5] Instalando herramientas externas (best-effort: nmap...)"
  install_tool() {
    command -v "$1" >/dev/null 2>&1 && { echo "      $1 ya instalado."; return; }
    if   command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y "$2" || true
    elif command -v dnf     >/dev/null 2>&1; then sudo dnf install -y "$2" || true
    elif command -v pacman  >/dev/null 2>&1; then sudo pacman -Sy --noconfirm "$2" || true
    elif command -v brew    >/dev/null 2>&1; then brew install "$2" || true
    else c_yellow "      No sé instalar $1 en este sistema; se omite (degradación elegante)."; fi
  }
  install_tool nmap nmap
  # RustScan/nuclei suelen requerir cargo/go; se omiten si no están.
  command -v cargo >/dev/null 2>&1 && ! command -v rustscan >/dev/null 2>&1 && \
    { c_cyan "      Instalando RustScan vía cargo..."; cargo install rustscan || true; }
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

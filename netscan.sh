#!/usr/bin/env bash
# ============================================================
#  Lanzador de NetScan para Linux / macOS
#  - Usa el entorno virtual backend/.venv
#  - Se auto-eleva con sudo (el escaneo ARP necesita privilegios)
#  - Ejemplos:
#      ./netscan.sh up            API + dashboard + navegador
#      ./netscan.sh scan --full
#      ./netscan.sh serve
#      ./netscan.sh speedtest
#      ./netscan.sh doctor
# ============================================================
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "ERROR: no existe el entorno virtual. Ejecuta primero: ./install.sh"
  exit 1
fi

CMD="${1:-up}"
# 'doctor', 'caps' y '--help' no necesitan privilegios; el resto sí para ARP.
NEEDS_ROOT=1
case "$CMD" in
  doctor|caps|--help|-h) NEEDS_ROOT=0 ;;
esac

if [ "$NEEDS_ROOT" = "1" ] && [ "$(id -u)" != "0" ] && command -v sudo >/dev/null 2>&1; then
  # Reejecuta con sudo preservando el venv.
  exec sudo -E "$PY" -m netscan.cli "$@"
fi

exec "$PY" -m netscan.cli "$@"

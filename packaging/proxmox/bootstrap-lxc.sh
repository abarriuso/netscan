#!/usr/bin/env bash
# ============================================================
#  NetScan — bootstrap dentro de un LXC/VM Linux ya creado.
#
#  Dado un contenedor Debian/Ubuntu pelado (recién creado, sin git ni
#  siquiera sudo instalados, que es como vienen las plantillas de Proxmox),
#  lo deja con NetScan corriendo como servicio systemd: escuchando en toda
#  la LAN (0.0.0.0:8600) y con las capacidades de red que necesita el
#  escaneo ARP (CAP_NET_RAW/CAP_NET_ADMIN, vía install.sh --system).
#
#  Ejecutar como root DENTRO del contenedor:
#    curl -fsSL https://raw.githubusercontent.com/abarriuso/netscan/main/packaging/proxmox/bootstrap-lxc.sh | bash
#
#  Si ya tienes el repo clonado a mano, este script es prescindible:
#  solo hace de pegamento (git, sudo, curl + clonar) antes de llamar a
#  install.sh --system, que es donde está la lógica real.
#
#  Prerrequisito que este script NO puede arreglar desde dentro: el
#  contenedor tiene que estar en un bridge conectado a tu LAN real
#  (vmbr0 o el que uses), no detrás de NAT — si no, el escaneo ARP solo
#  se verá a sí mismo. Eso se decide al crear el CT (ver create-lxc.sh).
# ============================================================
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/abarriuso/netscan.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/netscan}"

c_cyan()   { printf '\033[36m%s\033[0m\n' "$1"; }
c_green()  { printf '\033[32m%s\033[0m\n' "$1"; }
c_yellow() { printf '\033[33m%s\033[0m\n' "$1"; }
c_red()    { printf '\033[31m%s\033[0m\n' "$1"; }

if [ "$(id -u)" != "0" ]; then
  c_red "Ejecuta esto como root dentro del contenedor (es lo normal nada más crearlo)."
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  c_red "Este script asume Debian/Ubuntu (apt-get). Para otras distros, sigue el README a mano."
  exit 1
fi

echo "============================================================"
echo "  NetScan — bootstrap LXC"
echo "============================================================"

c_cyan "[1/3] Paquetes base (git, sudo, curl)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git sudo curl ca-certificates >/dev/null
c_green "      OK."

c_cyan "[2/3] Clonando NetScan en $INSTALL_DIR (rama $BRANCH)..."
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" fetch --quiet origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout --quiet "$BRANCH"
  git -C "$INSTALL_DIR" pull --quiet origin "$BRANCH"
  c_green "      Ya existía; actualizado a lo último de $BRANCH."
else
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  c_green "      Clonado."
fi

cd "$INSTALL_DIR"
chmod +x install.sh netscan.sh 2>/dev/null || true

c_cyan "[3/3] Instalando como servicio systemd (./install.sh --system)..."
./install.sh --system

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "============================================================"
c_green "  Bootstrap completo."
echo "  Dashboard:  http://${IP:-<ip-del-contenedor>}:8600/"
echo "  Token API:  cat /etc/netscan/netscan.env"
echo "============================================================"

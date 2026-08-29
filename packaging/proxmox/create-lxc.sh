#!/usr/bin/env bash
# ============================================================
#  NetScan — crea un LXC de Proxmox, lo conecta a la LAN real y deja
#  NetScan corriendo dentro como servicio web, en un solo comando.
#
#  Ejecutar en la SHELL DEL HOST PROXMOX (como root), no dentro de un
#  contenedor:
#
#    ./create-lxc.sh
#
#  Todo se puede ajustar con variables de entorno (todas opcionales):
#
#    VMID=210 HOSTNAME=netscan BRIDGE=vmbr0 VLAN= \
#    STORAGE=local-lvm DISK_GB=8 CORES=2 MEMORY_MB=1024 IP=dhcp \
#    ./create-lxc.sh
#
#  - VMID: por defecto, el siguiente libre (pvesh get /cluster/nextid).
#  - BRIDGE: el bridge de Proxmox conectado a tu LAN física — normalmente
#    vmbr0. Este es EL ajuste que importa de verdad: si el contenedor no
#    comparte el mismo segmento L2 que el resto de tus dispositivos (por
#    ejemplo, un bridge NAT-only o una zona SDN aislada), el escaneo ARP
#    de NetScan solo se verá a sí mismo. Esto no se puede arreglar desde
#    dentro del contenedor — se decide aquí, al crearlo.
#  - VLAN: si tu LAN usa una VLAN etiquetada, pon el ID aquí. Vacío =
#    sin etiquetar (igual que el resto de la red, lo normal en un homelab).
#  - IP: "dhcp" (por defecto) o algo como
#    "192.168.1.50/24,gw=192.168.1.1" para IP estática.
#
#  Requiere que packaging/proxmox/bootstrap-lxc.sh esté junto a este
#  script (así viene en el repo); si no lo encuentra, lo baja de GitHub.
# ============================================================
set -euo pipefail

c_cyan()   { printf '\033[36m%s\033[0m\n' "$1"; }
c_green()  { printf '\033[32m%s\033[0m\n' "$1"; }
c_yellow() { printf '\033[33m%s\033[0m\n' "$1"; }
c_red()    { printf '\033[31m%s\033[0m\n' "$1"; }

if [ "$(id -u)" != "0" ] || ! command -v pct >/dev/null 2>&1; then
  c_red "Esto se ejecuta en la shell del HOST Proxmox (como root), no dentro de un contenedor."
  c_red "¿Buscabas bootstrap-lxc.sh? Ese va DENTRO del contenedor."
  exit 1
fi

VMID="${VMID:-$(pvesh get /cluster/nextid)}"
CT_HOSTNAME="${HOSTNAME:-netscan}"
BRIDGE="${BRIDGE:-vmbr0}"
VLAN="${VLAN:-}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
DISK_GB="${DISK_GB:-8}"
CORES="${CORES:-2}"
MEMORY_MB="${MEMORY_MB:-1024}"
IP="${IP:-dhcp}"
REPO_URL="${REPO_URL:-https://github.com/abarriuso/netscan.git}"
BRANCH="${BRANCH:-main}"

if pct status "$VMID" >/dev/null 2>&1; then
  c_red "Ya existe un contenedor con VMID $VMID. Elige otro: VMID=<n> ./create-lxc.sh"
  exit 1
fi

echo "============================================================"
echo "  NetScan — aprovisionando LXC $VMID ($CT_HOSTNAME) en $BRIDGE"
echo "============================================================"

c_cyan "[1/5] Buscando plantilla de Debian 12..."
TEMPLATE="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk '/debian-12-standard/{print $1}' | tail -1)"
if [ -z "$TEMPLATE" ]; then
  c_yellow "      No está descargada; descargando debian-12-standard..."
  pveam update >/dev/null
  LATEST="$(pveam available 2>/dev/null | grep debian-12-standard | tail -1 | awk '{print $2}')"
  if [ -z "$LATEST" ]; then
    c_red "      No se encontró ninguna plantilla debian-12-standard disponible."
    c_red "      Descárgala a mano desde la UI (Storage -> local -> CT Templates) y reintenta."
    exit 1
  fi
  pveam download "$TEMPLATE_STORAGE" "$LATEST"
  TEMPLATE="${TEMPLATE_STORAGE}:vztmpl/${LATEST}"
fi
c_green "      Plantilla: $TEMPLATE"

c_cyan "[2/5] Creando CT $VMID..."
NET0="name=eth0,bridge=$BRIDGE,ip=$IP"
[ -n "$VLAN" ] && NET0="$NET0,tag=$VLAN"

pct create "$VMID" "$TEMPLATE" \
  --hostname "$CT_HOSTNAME" \
  --cores "$CORES" \
  --memory "$MEMORY_MB" \
  --swap 512 \
  --rootfs "${STORAGE}:${DISK_GB}" \
  --net0 "$NET0" \
  --unprivileged 1 \
  --features nesting=0 \
  --onboot 1 \
  --start 0
c_green "      CT $VMID creado (unprivileged, bridge=$BRIDGE${VLAN:+, vlan=$VLAN})."

c_cyan "[3/5] Arrancando..."
pct start "$VMID"
for _ in $(seq 1 30); do
  pct exec "$VMID" -- true 2>/dev/null && break
  sleep 1
done

c_cyan "[4/5] Esperando IP..."
CTIP=""
for _ in $(seq 1 30); do
  CTIP="$(pct exec "$VMID" -- hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$CTIP" ] && break
  sleep 1
done
if [ -z "$CTIP" ]; then
  c_yellow "      Sin IP todavía tras 30s — revisa la config de red del bridge/VLAN."
else
  c_green "      IP: $CTIP"
fi

c_cyan "[5/5] Instalando NetScan dentro del contenedor..."
BOOTSTRAP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bootstrap-lxc.sh"
if [ ! -f "$BOOTSTRAP" ]; then
  c_yellow "      bootstrap-lxc.sh no está junto a este script; descargándolo..."
  BOOTSTRAP="/tmp/bootstrap-lxc.$$.sh"
  curl -fsSL "https://raw.githubusercontent.com/abarriuso/netscan/main/packaging/proxmox/bootstrap-lxc.sh" -o "$BOOTSTRAP"
fi
pct push "$VMID" "$BOOTSTRAP" /root/bootstrap-lxc.sh
pct exec "$VMID" -- bash -c "chmod +x /root/bootstrap-lxc.sh; REPO_URL='$REPO_URL' BRANCH='$BRANCH' /root/bootstrap-lxc.sh"

echo
echo "============================================================"
c_green "  NetScan listo en el CT $VMID."
echo "  Dashboard:  http://${CTIP:-<ip-del-ct>}:8600/"
echo "  Token API:  pct exec $VMID -- cat /etc/netscan/netscan.env"
echo "  Logs:       pct exec $VMID -- journalctl -u netscan -f"
echo "============================================================"

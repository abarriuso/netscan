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
#    VMID=210 CT_NAME=netscan BRIDGE=vmbr0 VLAN= \
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
#  - OS_TEMPLATE: por defecto "ubuntu-26.04-standard". Cualquier plantilla
#    basada en Debian/Ubuntu vale para NetScan (bootstrap-lxc.sh solo usa
#    apt-get) — para Debian 12 por ejemplo:
#      OS_TEMPLATE=debian-12-standard ./create-lxc.sh
#    Mira los nombres exactos disponibles con: pveam available | grep -i debian
#
#  Requiere que packaging/proxmox/bootstrap-lxc.sh esté junto a este
#  script (así viene en el repo); si no lo encuentra, lo baja de GitHub.
#
#  Si lo lanzas a mano en una terminal, pregunta VMID/nombre/plantilla/
#  bridge/IP uno a uno (con lo de arriba como valor por defecto — pulsa
#  Enter para aceptarlo). Cualquier variable que ya venga fijada por
#  entorno NO se pregunta; y si la entrada estándar no es una terminal
#  (por ejemplo, ejecutado desde un pipe/automatización), tampoco se
#  pregunta nada — se usan los valores por defecto sin más, para no
#  quedarse colgado esperando una respuesta que nunca llega.
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

# Pide VARNAME "pregunta" "valor por defecto" — si VARNAME ya viene fijada
# por variable de entorno se respeta sin preguntar; si no hay terminal de
# por medio (pipe, cron, CI) se usa el valor por defecto en silencio.
prompt_var() {
  local __name="$1" __question="$2" __default="$3" __answer
  if [ -n "${!__name:-}" ]; then
    return
  fi
  if [ -t 0 ]; then
    read -r -p "$__question [$__default]: " __answer </dev/tty || __answer=""
    printf -v "$__name" '%s' "${__answer:-$__default}"
  else
    printf -v "$__name" '%s' "$__default"
  fi
}

prompt_var VMID        "VMID del contenedor"                       "$(pvesh get /cluster/nextid)"
prompt_var CT_NAME     "Nombre del contenedor"                     "netscan"
prompt_var OS_TEMPLATE "Plantilla (Debian/Ubuntu)"                 "ubuntu-26.04-standard"
prompt_var BRIDGE      "Bridge de red (LAN real, no NAT)"          "vmbr0"

# IP se pregunta en dos pasos simples (IP/CIDR y gateway por separado) en
# vez de un único campo con la sintaxis "cidr,gw=..." de Proxmox — así no
# hay forma de escribirlo mal. Si IP ya viene fijada por entorno (con o
# sin "gw=" incluido) se respeta tal cual, sin preguntar nada.
if [ -z "${IP:-}" ]; then
  if [ -t 0 ]; then
    read -r -p "IP estática, formato 192.168.1.21/24 (vacío = dhcp): " __ip_cidr </dev/tty || __ip_cidr=""
  else
    __ip_cidr=""
  fi
  if [ -z "$__ip_cidr" ]; then
    IP="dhcp"
  else
    __gw=""
    if [ -t 0 ]; then
      read -r -p "Gateway, ej. 192.168.1.1: " __gw </dev/tty || __gw=""
    fi
    IP="$__ip_cidr${__gw:+,gw=$__gw}"
  fi
elif [ "$IP" != "dhcp" ] && [[ "$IP" == *,* ]]; then
  # Defensa contra IP=cidr,1.2.3.1 fijado a mano por variable de entorno
  # sin el prefijo gw= que Proxmox exige — si el segundo trozo no lleva
  # ya una clave conocida, se la añadimos.
  __after_comma="${IP#*,}"
  case "$__after_comma" in
    gw=*|tag=*|firewall=*) ;; # ya trae una clave válida, no tocar
    *) IP="${IP%%,*},gw=${__after_comma}" ;;
  esac
fi

# pct create no pone contraseña de root por defecto — sin --password el CT
# queda sin forma de hacer login (ni consola ni SSH) salvo `pct enter` desde
# el host. Se pregunta con eco desactivado (como cualquier prompt de
# contraseña); vacío = generar una aleatoria y mostrarla al final, igual
# que ya hacemos con el token de la API.
GENERATED_PASSWORD=0
if [ -z "${CT_PASSWORD:-}" ]; then
  if [ -t 0 ]; then
    read -rs -p "Contraseña de root del contenedor (vacío = generar una aleatoria): " CT_PASSWORD </dev/tty || CT_PASSWORD=""
    echo
  fi
  if [ -z "${CT_PASSWORD:-}" ]; then
    CT_PASSWORD="$(openssl rand -base64 18 2>/dev/null || tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
    GENERATED_PASSWORD=1
  fi
fi

VLAN="${VLAN:-}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
DISK_GB="${DISK_GB:-8}"
CORES="${CORES:-2}"
MEMORY_MB="${MEMORY_MB:-1024}"
REPO_URL="${REPO_URL:-https://github.com/abarriuso/netscan.git}"
BRANCH="${BRANCH:-main}"

if pct status "$VMID" >/dev/null 2>&1; then
  c_red "Ya existe un contenedor con VMID $VMID. Elige otro: VMID=<n> ./create-lxc.sh"
  exit 1
fi

echo "============================================================"
echo "  NetScan — aprovisionando LXC $VMID ($CT_NAME) en $BRIDGE"
echo "============================================================"

c_cyan "[1/5] Buscando plantilla $OS_TEMPLATE..."
TEMPLATE="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk -v p="$OS_TEMPLATE" '$1 ~ p {print $1}' | tail -1)"
if [ -z "$TEMPLATE" ]; then
  c_yellow "      No está descargada; buscando $OS_TEMPLATE para descargar..."
  pveam update >/dev/null
  LATEST="$(pveam available 2>/dev/null | grep -i "$OS_TEMPLATE" | sort -V | tail -1 | awk '{print $2}')"
  if [ -z "$LATEST" ]; then
    c_red "      No se encontró ninguna plantilla que case con '$OS_TEMPLATE'."
    c_red "      Mira los nombres exactos con: pveam available | grep -i <distro>"
    c_red "      y pásalo como OS_TEMPLATE=<nombre-exacto-sin-versión-ni-arch> ./create-lxc.sh"
    exit 1
  fi
  pveam download "$TEMPLATE_STORAGE" "$LATEST"
  TEMPLATE="${TEMPLATE_STORAGE}:vztmpl/${LATEST}"
fi
c_green "      Plantilla: $TEMPLATE"

c_cyan "[2/5] Creando CT $VMID..."
NET0="name=eth0,bridge=$BRIDGE,ip=$IP"
[ -n "$VLAN" ] && NET0="$NET0,tag=$VLAN"

# nesting=1: newer systemd (Ubuntu 24.04+/26.04, Debian 13) needs it for
# systemd-resolved to actually work inside an unprivileged LXC — without
# it the container can get a real IP but DNS resolution silently fails
# (apt-get errors with "Temporary failure resolving ..." even though the
# network itself is fine). Safe to leave on for an unprivileged CT.
pct create "$VMID" "$TEMPLATE" \
  --hostname "$CT_NAME" \
  --cores "$CORES" \
  --memory "$MEMORY_MB" \
  --swap 512 \
  --rootfs "${STORAGE}:${DISK_GB}" \
  --net0 "$NET0" \
  --unprivileged 1 \
  --features nesting=1 \
  --password "$CT_PASSWORD" \
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
# ${BASH_SOURCE[0]:-} (not bare ${BASH_SOURCE[0]}) matters here: when this
# script runs as `bash -c "$(curl ...)"` (no real source file, just a
# string), BASH_SOURCE is unset entirely, and `set -u` turns a bare
# reference into a hard crash instead of the empty string we actually want.
SELF="${BASH_SOURCE[0]:-}"
BOOTSTRAP=""
if [ -n "$SELF" ] && [ -f "$(dirname "$SELF")/bootstrap-lxc.sh" ]; then
  BOOTSTRAP="$(cd "$(dirname "$SELF")" && pwd)/bootstrap-lxc.sh"
fi
if [ -z "$BOOTSTRAP" ]; then
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
if [ "$GENERATED_PASSWORD" = "1" ]; then
  echo "  Root del CT: $CT_PASSWORD   (generada — guárdala, no se puede recuperar después)"
else
  echo "  Root del CT: la contraseña que escribiste al principio"
fi
echo "============================================================"

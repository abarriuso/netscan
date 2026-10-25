"""Device classification: role inference and MAC address analysis.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Pure functions, no I/O. The role is inferred by crossing every signal the
scanner collected — open ports, mDNS service types, OUI vendor, hostname,
web UI title, the MAC's own bits — and always comes with the *reason* that
decided it, so the dashboard can show why a box was labelled "NAS".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROLES = (
    "gateway",
    "netscan",
    "hypervisor",
    "nas",
    "server",
    "workstation",
    "mobile",
    "printer",
    "media",
    "camera",
    "iot",
    "network",
    "vm",
    "unknown",
)

# OUI prefixes of hypervisors / container runtimes (lower-case, colon form).
_VIRTUAL_OUIS = {
    "00:50:56": "VMware",
    "00:0c:29": "VMware",
    "00:05:69": "VMware",
    "08:00:27": "VirtualBox",
    "52:54:00": "QEMU/KVM",
    "00:15:5d": "Hyper-V",
    "bc:24:11": "Proxmox VE",
    "00:16:3e": "Xen",
    "02:42:ac": "Docker",
}

_VENDOR_HINTS: list[tuple[str, str]] = [
    (r"synology|qnap|western digital|asustor|terramaster|buffalo|ixsystems", "nas"),
    (r"hewlett|brother|epson|canon|kyocera|lexmark|xerox|ricoh|konica", "printer"),
    (r"hikvision|dahua|reolink|axis comm|amcrest|foscam|uniview|ezviz", "camera"),
    (
        r"espressif|tuya|shelly|sonoff|itead|signify|philips light|lifx|nanoleaf|wiz|ring|nest|ecobee|tasmota",
        "iot",
    ),
    (
        r"roku|sonos|nvidia|chromecast|amazon tech|lg electronics|samsung electronics.*tv|vizio|hisense|tcl",
        "media",
    ),
    (
        r"ubiquiti|mikrotik|cisco|aruba|ruckus|juniper|zyxel|netgear|tp-link|d-link|tenda|linksys|fortinet|"
        # ISP gateways / ONTs (Orange Livebox = Sagemcom/Arcadyan, Movistar = Askey/Mitrastar, ...)
        r"sagemcom|arcadyan|technicolor|askey|mitrastar|sercomm|compal broadband|zte|avm gmbh",
        "network",
    ),
    (r"apple|samsung|xiaomi|oneplus|huawei|honor|oppo|vivo|motorola|google|realme|nothing tech", "mobile"),
    (r"raspberry|intel|dell|lenovo|hewlett|asrock|gigabyte|micro-star|supermicro|asustek", "workstation"),
]

_MDNS_HINTS: dict[str, str] = {
    "googlecast": "media",
    "airplay": "media",
    "raop": "media",
    "spotify-connect": "media",
    "nvstream_dbd": "media",
    "ipp": "printer",
    "ipps": "printer",
    "printer": "printer",
    "pdl-datastream": "printer",
    "hap": "iot",
    "homekit": "iot",
    "esphomelib": "iot",
    "mqtt": "iot",
}

_TITLE_HINTS: list[tuple[str, str]] = [
    (r"proxmox|esxi|vsphere|xcp-ng|xen orchestra", "hypervisor"),
    (r"truenas|freenas|openmediavault|diskstation|synology|qnap|unraid", "nas"),
    (r"home assistant|homebridge|zigbee2mqtt|node-red|esphome", "iot"),
    (r"pi-hole|adguard|portainer|grafana|prometheus|nextcloud|gitea|vaultwarden|uptime kuma", "server"),
    (r"jellyfin|plex|emby|kodi|navidrome", "media"),
    (r"unifi|omada|openwrt|luci|routeros|mikrotik|pfsense|opnsense|livebox|fritz|router", "network"),
    (r"printer|laserjet|officejet|epson|brother", "printer"),
    (r"camera|nvr|dvr|hikvision|reolink|frigate", "camera"),
]

_HOSTNAME_HINTS: list[tuple[str, str]] = [
    (r"\b(pve|proxmox|esxi?|xcp|hyperv)\b", "hypervisor"),
    (r"\b(nas|truenas|freenas|unraid|omv|synology|diskstation)\b", "nas"),
    (r"\b(homeassistant|hassio|hass)\b", "iot"),
    (r"\b(iphone|ipad|android|galaxy|pixel|redmi|phone)\b", "mobile"),
    (r"\b(printer|print|mfp|laserjet|officejet)\b", "printer"),
    (r"\b(cam|camera|nvr|doorbell)\b", "camera"),
    (r"\b(tv|chromecast|shield|roku|appletv|firetv|sonos)\b", "media"),
    (r"\b(esp|shelly|tasmota|sonoff|plug|bulb|sensor)\b", "iot"),
    (r"\b(desktop|laptop|pc|workstation|macbook|imac|win)\b", "workstation"),
    (
        r"\b(switch|ap|unifi|router|gw|firewall|opnsense|pfsense|livebox|fritzbox|fritz|ont|modem)\b",
        "network",
    ),
]


@dataclass
class MacInfo:
    mac: str
    oui: str = ""
    locally_administered: bool = False  # randomized/private MAC, or a VM/container
    multicast: bool = False
    virtual_platform: str = ""  # "Proxmox VE", "Docker"... when the OUI says so

    def as_dict(self) -> dict[str, object]:
        return {
            "oui": self.oui,
            "locally_administered": self.locally_administered,
            "randomized": self.locally_administered and not self.virtual_platform,
            "virtual_platform": self.virtual_platform,
        }


def mac_info(mac: str) -> MacInfo:
    info = MacInfo(mac=mac)
    parts = mac.lower().split(":")
    if len(parts) != 6:
        return info
    try:
        first = int(parts[0], 16)
    except ValueError:
        return info
    info.oui = ":".join(parts[:3])
    info.locally_administered = bool(first & 0x02)
    info.multicast = bool(first & 0x01)
    info.virtual_platform = _VIRTUAL_OUIS.get(info.oui, "")
    if not info.virtual_platform and info.oui.startswith("02:42"):
        info.virtual_platform = "Docker"
    return info


@dataclass
class Classification:
    role: str = "unknown"
    reasons: list[str] = field(default_factory=list)
    confidence: int = 0  # 0-100, how many independent signals agreed

    def as_dict(self) -> dict[str, object]:
        return {"role": self.role, "reasons": self.reasons, "confidence": self.confidence}


def classify(
    *,
    ip: str,
    mac: str = "",
    vendor: str = "",
    hostname: str = "",
    mdns_name: str = "",
    mdns_services: list[str] | None = None,
    ports: set[int] | None = None,
    os_guess: str = "",
    web_titles: list[str] | None = None,
    gateway_ip: str | None = None,
    local_ip: str | None = None,
) -> Classification:
    """Infer the device's role. Every vote carries a human-readable reason."""
    ports = ports or set()
    services = [s.lower() for s in (mdns_services or [])]
    titles = " ".join(web_titles or []).lower()
    vendor_l = vendor.lower()
    name = f"{hostname} {mdns_name}".lower()

    if gateway_ip and ip == gateway_ip:
        return Classification("gateway", ["IP is the default gateway"], 100)
    if local_ip and ip == local_ip:
        return Classification("netscan", ["this host (runs NetScan)"], 100)

    votes: dict[str, list[str]] = {}

    def vote(role: str, reason: str) -> None:
        votes.setdefault(role, []).append(reason)

    # Ports — the strongest signal: they say what the box actually serves.
    if 8006 in ports:
        vote("hypervisor", "port 8006 (Proxmox VE web UI)")
    if 902 in ports or "vmware esxi" in titles:
        vote("hypervisor", "VMware ESXi signature")
    if ports & {5000, 5001} and ("synology" in vendor_l or "diskstation" in titles or "dsm" in titles):
        vote("nas", "ports 5000/5001 + Synology DSM")
    if "truenas" in titles or "freenas" in titles:
        vote("nas", "TrueNAS web UI title")
    if ports & {548, 2049} or (445 in ports and ports & {111, 2049}):
        vote("nas", "file-sharing ports (AFP/NFS)")
    if ports & {9100, 515, 631}:
        vote("printer", "printing ports (JetDirect/LPD/IPP)")
    if 554 in ports or 8554 in ports:
        vote("camera", "RTSP stream port")
    if ports & {32400, 8096, 8920, 8008, 8009}:
        vote("media", "media server/cast port (Plex/Jellyfin/Cast)")
    if 1883 in ports or 8883 in ports:
        vote("iot", "MQTT broker port")
    if 62078 in ports:
        vote("mobile", "port 62078 (iOS lockdown/sync)")
    if ports & {3389, 135}:
        vote("workstation", "Windows ports (RDP/RPC)")
    elif 445 in ports and 22 not in ports:
        # SMB alone is weak evidence: ISP routers and NAS boxes share USB
        # disks over SMB too — a hint, not a port-strength vote.
        vote("workstation", "SMB without SSH (Windows-like file sharing)")
    if 22 in ports and ports & {80, 443, 3306, 5432, 6379, 27017, 9000, 9090, 8080}:
        vote("server", "SSH + network services")
    if 161 in ports and not ports & {9100, 631}:
        vote("network", "SNMP agent")

    for pattern, role in _TITLE_HINTS:
        if titles and re.search(pattern, titles):
            vote(role, f"web UI title matches '{pattern.split('|')[0]}'")
            break

    for svc in services:
        if svc in _MDNS_HINTS:
            vote(_MDNS_HINTS[svc], f"mDNS service _{svc}._tcp")

    for pattern, role in _VENDOR_HINTS:
        if vendor_l and re.search(pattern, vendor_l):
            vote(role, f"vendor '{vendor}'")
            break

    for pattern, role in _HOSTNAME_HINTS:
        if name.strip() and re.search(pattern, name):
            vote(role, f"hostname '{(hostname or mdns_name).strip()}'")
            break

    if os_guess.lower().startswith("windows"):
        vote("workstation", f"OS guess '{os_guess}'")

    minfo = mac_info(mac) if mac else None
    if minfo and minfo.virtual_platform:
        vote("vm", f"MAC OUI of {minfo.virtual_platform}")
    elif minfo and minfo.locally_administered and not votes:
        vote("mobile", "randomized (locally administered) MAC — typical of phones/tablets")

    if not votes:
        return Classification("unknown", ["no distinctive ports, mDNS services or vendor"], 0)

    # Port/mDNS evidence outranks vendor/hostname hints: a Raspberry Pi
    # (vendor → workstation) serving Proxmox on 8006 is a hypervisor.
    def weight(item: tuple[str, list[str]]) -> tuple[int, int]:
        _role, reasons = item
        strong = sum(
            1
            for r in reasons
            if r.startswith(
                (
                    "port",
                    "ports",
                    "mDNS",
                    "RTSP",
                    "MQTT",
                    "SSH",
                    "Windows",
                    "TrueNAS",
                    "VMware",
                    "web UI",
                    "file",
                    "printing",
                    "media",
                    "SNMP",
                )
            )
        )
        return (strong, len(reasons))

    role, reasons = max(votes.items(), key=weight)
    confidence = min(100, 35 * len(reasons) + 10 * (len(votes) == 1))
    return Classification(role, reasons, confidence)

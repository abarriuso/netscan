# Changelog

Todos los cambios notables de NetScan se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

### Seguridad
- Autenticación opcional por token (`NETSCAN_API_TOKEN`) en HTTP y WebSocket.
- La API escucha en `127.0.0.1` por defecto; CORS restringido y configurable.
- Los escaneos por API solo aceptan redes privadas (RFC 1918 / loopback / link-local).
- `install-nuclei.ps1` verifica el SHA256 del binario contra las checksums
  oficiales antes de instalarlo.
- AdGuard: `verify_ssl` configurable (antes TLS sin verificar hardcodeado).

### Añadido
- `install.bat` instala TODO de una: Python y Node.js vía winget si faltan,
  backend, nmap, RustScan, Npcap y nuclei (`--minimal` para saltárselo).
- Logging central a consola y a `data/netscan.log`.
- SQLite en modo WAL con `busy_timeout` y retención de los últimos 200 scans.
- Dashboard: banners de error visibles en todos los paneles cuando la API no
  responde; `aria-label` en botones de icono; `lang="es"`.
- Escaneo ARP de redes grandes troceado en /24 con watchdog por chunk.
- WoL: broadcast dirigido de la red local y 3 paquetes (antes 1 a 255.255.255.255).

### Corregido
- Detección de la red local por la puerta de enlace por defecto (antes podía
  elegir interfaces de WSL/Hyper-V/Docker).
- Fingerprint TLS con `cryptography` (antes API privada `ssl._ssl._test_decode_cert`,
  ficheros PEM temporales sin borrar y parseo de fechas dependiente del locale).
- La latencia de ping se parsea del output del comando (tolerante a locale);
  antes medía el arranque del proceso (~30-80 ms de más en Windows).
- Un fallo enriqueciendo un host ya no aborta el escaneo completo.
- Frontend: bucle de refetch en `usePoll` y reconexión zombie del WebSocket.
- nuclei limitado a `nuclei_max_targets` (20 por defecto).
- Docker: `npm ci` + `.dockerignore` en el frontend; `extra_hosts` para que el
  proxy de nginx alcance el backend en el host.
- CI: cobertura real (`--cov=netscan` con umbral del 49 %), subida a Codecov
  estricta y chequeo de licencias que falla de verdad.
- Legal: PEP 639 en `pyproject.toml`, NOTICE corregido (sin proxmoxer/websockets,
  con typer/PyYAML), LICENSE + NOTICE incluidos en el paquete.

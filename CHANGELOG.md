# Changelog

Todos los cambios notables de NetScan se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

### Añadido — arranque, servicio web y métricas
- **`netscan up`**: un solo comando que sirve la API y el dashboard integrado
  en el mismo puerto y abre el navegador. La API sirve `frontend/dist` como
  estático (SPA con fallback), así que ya no hacen falta dos procesos.
- **Multiplataforma, consola y "programa normal"**:
  - `install.sh` / `netscan.sh` para Linux/macOS (un comando, `--run`,
    `--minimal`, `--system`); auto-sudo para el ARP scan.
  - `install.bat` ahora compila el dashboard y admite `--run`; `netscan.bat`
    lanza `up` por defecto.
  - Instalador Windows con **Inno Setup** (`packaging/windows/netscan.iss` →
    `NetScan-Setup.exe`, con desinstalador y accesos del menú Inicio) y workflow
    `installer.yml` que lo compila en CI.
  - **Servicio web systemd** en Linux (`packaging/linux/netscan.service` +
    `install.sh --system`): bind a `0.0.0.0`, token generado en
    `/etc/netscan/netscan.env`, `CAP_NET_RAW`, y lanzador `.desktop`.
- **Speed test por dispositivo** (`scanner/speed.py`): latencia media/mín/máx,
  jitter, pérdida de paquetes, handshake TCP por puerto, throughput HTTP
  opcional y puntuación de calidad 0–100. CLI `netscan speedtest` y endpoint
  `POST /api/devices/{mac}/speedtest`.
- **Estado del sistema** (`system.py`, `psutil`): CPU por núcleo, RAM/swap,
  discos, tráfico por interfaz en vivo, link speed, proceso del backend y
  estado del frontend. Endpoints `GET /api/system` y `GET /api/status`.
- **Histórico de métricas**: nueva tabla `metric_samples` (con poda) +
  `GET /api/devices/{mac}/metrics` y `GET /api/metrics/summary`; migración
  aditiva que añade columnas a bases de datos antiguas sin borrarlas.
- **Dashboard**: panel "Estado del sistema" (server + frontend + host con toda
  la info), columnas de jitter/pérdida/calidad y botón de speed test por fila,
  tarjetas y medidores **animados** (respetan `prefers-reduced-motion`).
- `netscan doctor`: diagnóstico de Python, privilegios, toolchain, Node,
  dashboard compilado, base de datos e interfaces de red.
- Banner ASCII 3D en rosa chillón (`pyfiglet`, fuente `3-d`) al lanzar
  `netscan up`; el wordmark "Netscan" del dashboard tiene el mismo
  tratamiento (extrusión 3D vía `text-shadow` + shimmer animado,
  respeta `prefers-reduced-motion`) y favicon a juego. Es la única
  excepción deliberada a la paleta de un solo acento — el resto del
  dashboard no cambia.
- README: sección "Instalación en un comando" al principio, antes de
  "Qué hace", con los dos one-liners (`install.bat --run` /
  `./install.sh --run`) sin que haga falta bajar a buscarlos.
- `install.sh` ahora instala también `masscan`, `whatweb` y `testssl.sh`
  (paquete del sistema, o clonado desde GitHub si el repo no lo trae) y,
  en amd64/x86_64, descarga los binarios de RustScan y nuclei desde su
  último release de GitHub cuando no hay `cargo` a mano — antes solo
  intentaba `nmap` y RustScan vía `cargo`. Degradación elegante si algo
  falla o la arquitectura no es amd64.
- **whatweb y testssl.sh conectados de verdad al motor de escaneo**
  (antes solo se detectaban, pero nunca se llamaban): `whatweb` añade
  huella de tecnologías web (`HttpInfo.tech`) a cada web UI encontrada;
  `testssl.sh` audita la configuración TLS y sus hallazgos se suman a
  `vulnerabilities` junto a los de nuclei (cada entrada lleva ahora
  `tool: "nuclei" | "testssl"`). Lanzables individualmente desde el menú
  "acciones" del dashboard (`only=whatweb` / `only=testssl` en
  `POST /api/scans`), igual que ARP/mDNS/nmap/RustScan/nuclei.
- **Aprovisionamiento de Proxmox LXC en un comando**
  (`packaging/proxmox/create-lxc.sh` + `bootstrap-lxc.sh`): desde la shell
  del host Proxmox, crea un CT sin privilegiar (Ubuntu 26.04 LTS por
  defecto, cualquier plantilla Debian/Ubuntu vale) en el bridge de
  la LAN real, lo arranca y le instala NetScan dentro
  (`install.sh --system`) — termina imprimiendo la URL del dashboard y
  dónde está el token. `bootstrap-lxc.sh` también se puede usar solo,
  contra cualquier CT/VM Linux ya creado.
- **Diálogo de token en el dashboard** (`<TokenDialog>`): sustituye al
  `window.prompt()` nativo para pedir `NETSCAN_API_TOKEN` — se abre solo
  al primer 401, o a mano con el icono de llave del header (para
  cambiarlo tras rotar el token). Todas las peticiones concurrentes
  esperan al mismo diálogo en vez de reintentar cada una por su cuenta.

### Seguridad
- Autenticación opcional por token (`NETSCAN_API_TOKEN`) en HTTP y WebSocket.
- La API escucha en `127.0.0.1` por defecto; CORS restringido y configurable.
- Los escaneos por API solo aceptan redes privadas (RFC 1918 / loopback / link-local).
- `install-nuclei.ps1` verifica el SHA256 del binario contra las checksums
  oficiales antes de instalarlo.
- AdGuard: `verify_ssl` configurable (antes TLS sin verificar hardcodeado).
- `GET /api/system` ya no filtra `db_url` en crudo: si la cadena de conexión
  lleva credenciales (Postgres/MySQL), se redactan antes de enviarlas al
  dashboard.
- Comparación de token de API con `secrets.compare_digest` (antes `==`,
  vulnerable a timing attack) en HTTP y WebSocket.
- Rate limiting en autenticación: 429 (HTTP) / cierre 4429 (WS) tras 10
  intentos fallidos en 60 s por IP.
- `netscan.example.yaml` ya no trae `0.0.0.0` sin token por defecto (API
  abierta a toda la LAN si se copiaba tal cual).
- Job `security` en CI (`pip-audit --strict` + `npm audit`); dependencias con
  CVEs conocidos actualizadas (scapy, zeroconf, cryptography, starlette y
  varias transitivas del frontend).

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
- `install-nuclei.ps1` ya notifica a Windows (`WM_SETTINGCHANGE`) tras añadir
  su carpeta al PATH de usuario; antes, una terminal o acceso directo ya
  abierto no veía `nuclei` como disponible hasta cerrar sesión, aunque el
  binario estuviera instalado.
- `release.yml` / `installer.yml`: ambos publicaban al mismo GitHub Release
  en paralelo al reaccionar los dos al mismo tag (condición de carrera, y
  `installer.yml` sin `permissions: contents: write`). `installer.yml` es
  ahora un workflow reutilizable; `release.yml` orquesta backend, instalador
  Windows y bundle Linux en un único job de publicación.
- `netscan.bat` pedía elevación UAC incluso para `doctor` (solo lectura),
  a diferencia de `netscan.sh`; ahora tiene la misma lista de excepciones.
- `install.sh` abortaba toda la instalación si fallaba `npm run build`;
  ahora es un aviso no fatal, igual que `install.bat`.
- **Bug real, encontrado en vivo**: `install.sh`/`netscan.sh` usaban
  `backend/.venv`, el mismo path que `install.bat` en Windows. Al correr
  `install.sh` desde WSL sobre un checkout compartido en `/mnt/c/...`, esto
  corrompe el venv nativo de Windows (un venv de Windows y uno de Linux no
  pueden convivir en el mismo directorio). Ahora usan `backend/.venv-linux`,
  totalmente separado. `install.sh` también instala automáticamente
  `pythonX.Y-venv` si falta (causa típica de `ensurepip is not available`
  en Ubuntu) y reintenta, en vez de fallar.
- Legal: PEP 639 en `pyproject.toml`, NOTICE corregido (sin proxmoxer/websockets,
  con typer/PyYAML), LICENSE + NOTICE incluidos en el paquete.
- **Cinco bugs reales de aprovisionamiento LXC, encontrados en una instalación
  en vivo sobre Proxmox (Ubuntu 26.04/Python 3.14)**, todos con el
  aprovisionamiento colgándose o fallando sin completar la instalación:
  - `needrestart` (viene en la plantilla `standard` de Debian/Ubuntu) muestra
    un diálogo interactivo en cualquier `apt-get install`, ignorando
    `DEBIAN_FRONTEND=noninteractive` — sin tty (`pct exec`, `curl | bash`) se
    queda colgado para siempre sin ningún error. `install.sh` y
    `bootstrap-lxc.sh` ahora lo silencian antes de instalar nada.
  - La detección de "falta el paquete `pythonX.Y-venv`" comprobaba la frase
    completa `ensurepip is not available` contra el `stderr` capturado, pero
    CPython envuelve ese mensaje en dos líneas (ancho variable) **y lo
    imprime por `stdout`, no por `stderr`** — la comprobación nunca podía
    coincidir. Ahora captura ambos flujos y busca solo la palabra
    `ensurepip`, inequívoca y nunca partida por el ajuste de línea.
  - Ese mismo bug dejaba, tras un intento fallido anterior, un venv "válido"
    (binario de Python ejecutable) pero sin pip instalado — la comprobación
    de idempotencia (`[ -x $PY ]`) lo daba por bueno y la reinstalación
    fallaba más adelante en `pip install --upgrade pip` con un error mucho
    menos claro. Ahora también prueba `$PY -m pip --version` y reconstruye
    el venv si no responde.
  - `install.sh`/`netscan.sh` estaban trackeados en git como no ejecutables
    (`100644`); el `chmod +x` de `bootstrap-lxc.sh` tras cada clonado creaba
    un cambio de permisos sin commitear que hacía fallar el siguiente
    `git pull` en un CT ya aprovisionado (`your local changes would be
    overwritten by merge`). Commiteados ahora como `100755`.
  - `install.sh` nunca instalaba Node.js — solo comprobaba si ya existía y
    se saltaba el build del dashboard en silencio si no. Una plantilla LXC
    pelada nunca trae Node, así que `frontend/dist` no se generaba nunca y
    `/` devolvía `{"detail": "Not Found"}`. Ahora instala Node 20+ vía el
    script de NodeSource en apt (con fallback a `dnf module`/`pacman`/`brew`)
    antes de darse por vencido.
- `create-lxc.sh`: memoria por defecto subida de 1024 a 2048 MB tras un
  `oom-kill` real del servicio `netscan` (confirmado por `journalctl`)
  durante el build de Vite del dashboard.

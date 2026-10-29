# Changelog

Todos los cambios notables de NetScan se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

### Corregido — estabilidad en ejecución (LXC / Linux)
- **Uptime lento que crecía con el histórico**: con 30 días de datos el informe
  tardaba ~4,4 s por petición (más en un LXC de 2 vCPU), acaparando el GIL y
  frenando WebSockets y API. Ahora: índice cubriente
  `(device_mac, bucket_start, probes, up)` (también se crea en bases
  existentes), totales por ventana agregados en SQL y línea de tiempo en una
  sola pasada → ~0,2 s para la vista de 24 h.
- **Zona horaria**: el LXC corre en UTC y la API enviaba horas sin
  desfase, así que el navegador (hora de España) desplazaba una hora los
  "hace X", la duración de los estados y el orden de la terminal. Todas las
  horas de la API llevan ahora el desfase del servidor (`+00:00`).
- **Falsas caídas en Linux**: dispositivos que ignoran el ping (PCs con
  firewall, móviles en ahorro de energía) caían y volvían en bucle porque el
  respaldo ARP solo existía en Windows. Ahora el monitor consulta la tabla de
  vecinos del kernel (`ip neigh`): `REACHABLE` cuenta como arriba y los
  estados en verificación (`STALE`/`DELAY`/`PROBE`) no cuentan ni a favor ni
  en contra.
- **Dashboard sin token**: el stream de eventos reintentaba sin parar
  (WebSocket + sondeo cada 2 s), disparando el limitador anti fuerza bruta
  (429). Ahora espera al diálogo del token y se reconecta solo.
- **El diálogo del token volvía a pedirlo en bucle**: "Ahora no" lo reabría
  al instante, y con el servidor lento las peticiones enviadas antes de
  guardar el token volvían con 401 y lo reabrían aunque el token fuera
  correcto. Ahora un 401 de un token ya sustituido se reintenta con el nuevo,
  un token rechazado no se reenvía (tampoco desde los WebSockets), "Ahora no"
  deja el diálogo cerrado hasta abrirlo desde la cabecera, y se acepta pegar
  la línea `NETSCAN_API_TOKEN=...` entera. El limitador solo cuenta
  peticiones con un token incorrecto (las que no llevan ninguno ya no
  bloquean la IP) y un token con caracteres no ASCII da 401 en vez de 500.

### Añadido — observabilidad, uptime, mapa, seguridad y herramientas
- **Tutorial de primera visita** al estilo de los videojuegos: foco sobre cada
  elemento (el resto se oscurece), diálogo que se escribe solo, contador
  "misión 05/15" con barra de progreso, cambia a cada pestaña que explica y
  termina con un botón para lanzar el primer escaneo. Teclas → / ← / Esc; se
  repite con el botón **?** de la cabecera.
- **Terminal en vivo** acoplada abajo en todas las pestañas (tecla `` ` ``):
  mezcla los eventos del backend (BE: cada sondeo ARP/ICMP, puerto abierto,
  petición HTTP, certificado TLS, comando externo exacto, tick del monitor,
  llamada a la API vista por el servidor) con los del navegador (FE: cada
  petición con estado, tiempo y tamaño, estado del WebSocket, errores).
  Filtros por origen y nivel, búsqueda (texto o `/regex/`), pausa, exportación
  `.log`. Bus de eventos nuevo (`events.py`) con `/ws/events` (reanuda desde el
  último `seq`) y `/api/events` como respaldo.
- **Monitor en vivo** reescrito: cadena de sondas ICMP → TCP → ARP, histéresis
  (caído tras 3 fallos seguidos), RTT del gateway y de Internet, estado real en
  el inventario y en el historial del equipo.
- **Uptime por dispositivo** (1 h / 24 h / 7 d / 30 d) con barras tipo status
  page, **cobertura** (qué parte de la ventana se observó), caídas, MTTR y caída
  más larga. Buckets de 5 min en SQLite.
- **Mapa de red** ("radar de latencia": distancia = RTT en escala log, sector =
  rol, anillo = riesgo) y **mapa de IPs** de la subred (ocupación, libres).
- **Rol inferido** por equipo con sus motivos (puertos, mDNS, título web, OUI,
  hostname, MAC virtual/aleatoria).
- **Riesgo 0–100** por equipo con cada factor desglosado (evidencia +
  remediación), exposición por puerto, certificados, hallazgos, integridad del
  gateway. Pestaña **Seguridad**.
- **Alertas nuevas**: `ports_changed`, `ip_conflict`, `gateway_mac_changed`
  (indicio de ARP spoofing), `device_back`. "Marcar todo leído".
- **Ficha de dispositivo** única (tabla, mapa, uptime, seguridad): resumen,
  uptime, métricas, servicios/TLS, riesgo, historial y notas editables.
- **Herramientas** (pestaña nueva, sin binarios externos): ping, traceroute
  nativo, consulta DNS con cliente propio, benchmark de resolvers, TCP, escaneo
  de puertos de un host privado, tiempos HTTP por fase, inspector TLS, subred,
  MAC.
- **`/metrics`** en formato Prometheus (segundos y ratios 0–1) y **exportación**
  del inventario a CSV/JSON con rol, riesgo y disponibilidad 24 h.
- **Descubrimiento sin privilegios**: sin admin, barrido ICMP + caché ARP del
  sistema en vez de fallar el escaneo entero.
- `docs/METRICS.md`: definición, fórmula y unidad de cada número.

### Corregido
- Los equipos nunca pasaban a *offline* con la configuración por defecto (solo
  se marcaban con `alert_on_device_down`). Un escaneo de otra subred ya no
  marca caído el resto del inventario.
- La subida de logo de integraciones no exigía token (solo debía estar
  exento el GET); `/metrics` queda tras el token.
- `ping.exe` daba por vivo un host con "Host de destino inaccesible" (exit 0).
- Pi-hole abría una sesión nueva en cada sondeo y agotaba las sesiones de la
  API v6 (429); además leía los clientes del campo equivocado.
- AdGuard: `avg_processing_time` viene en segundos y se mostraba como ms.
- Calidad: un host sin respuesta puntuaba 20/100; un host que filtra ICMP
  puntuaba 0. Ahora se mide por handshake TCP o se muestra "—".
- Throughput: incluía conexión/TLS en el tiempo y subestimaba el ancho de banda.
- Velocidad de enlace tomada de un adaptador virtual (Hyper-V) en vez del real.
- Puertos cerrados que nunca desaparecían del inventario.
- Fingerprint HTTP/TLS perdido en routers con TLS antiguo y en proxies con SNI
  estricto; Proxmox (8006) no estaba entre los puertos comunes.
- El propio host no aparecía en el inventario; el DNS inverso bloqueaba ~5 s
  por equipo.
- Dos peticiones simultáneas podían recibir "escaneo iniciado"; el error real
  de un escaneo fallido se ocultaba tras "see netscan.log".
- El planificador ignoraba el último escaneo al reiniciar; el log crecía sin
  límite (ahora rota 5 MiB × 3) y `/api/logs` lo releía entero.
- La tendencia de red mezclaba speed tests manuales; la serie "dispositivos
  online" contaba en realidad equipos medidos.
- KPI "calidad: estable" fijo; atajos R/F anunciados pero sin conectar;
  descripciones de escaneo rápido/completo que no correspondían a lo que hacían.
- `memory.free` era en realidad la memoria disponible; las tasas de red
  `*_bps` eran bytes/s (nuevos campos explícitos `available_bytes`,
  `rx/tx_bytes_per_s`).

### Añadido — monitor en vivo y más gráficas
- **Monitor en vivo**: un servicio de fondo (`netscan/live.py`) hace ping
  continuo a los dispositivos conocidos y expone `/api/live`. Nueva pestaña
  **"En vivo"** con la latencia de red en directo y un **mapa de red** (estado
  vivo verde/rojo + RTT de cada equipo).
- **Analítica** amplía a 6 series: se suman *dispositivos online* y *pérdida de
  paquetes* en el tiempo.
- **Detalle por dispositivo**: al pinchar un equipo en la tabla, un diálogo con
  su histórico de latencia, calidad, jitter y pérdida.
- El título del dashboard respira más (espaciado).

### Añadido — rediseño del dashboard web
- **Navegación por secciones** (Resumen · Dispositivos · Analítica · Integraciones ·
  Sistema) en vez de una única página con todo apilado; solo se monta y sondea la
  sección activa.
- **Gráficas de series temporales**: nuevos endpoints `/api/metrics/history` y
  `/api/scans/history`, y una pestaña Analítica con la evolución de latencia,
  calidad, throughput y dispositivos por escaneo (Recharts).
- **Feedback de escaneo** claro: toast al iniciar/terminar/fallar, etapa actual +
  contador + tiempo transcurrido, y sondeo HTTP de respaldo si el WebSocket no
  conecta.
- **Responsive**: la tabla oculta columnas secundarias y las pestañas se reducen a
  iconos en pantallas pequeñas.

### Cambiado — rendimiento y consistencia del dashboard
- Capa GET con deduplicación e invalidación en mutaciones (evita pedir
  `/api/devices` por duplicado) y **pausa del sondeo con la pestaña en segundo plano**.
- **Code-splitting** de la pestaña Analítica (Recharts) e Integraciones para
  aligerar la carga inicial.
- Estados de carga uniformes (skeletons), *hover* fluido en tarjetas y transiciones
  que respetan `prefers-reduced-motion`.

### Cambiado — el frontend usa pnpm
- El dashboard pasa de **npm a pnpm** (`pnpm-lock.yaml`, campo `packageManager`).
  Build, Docker, workflows de CI e instaladores (`install.sh`/`install.bat`,
  `netscan up`) usan `pnpm` vía `corepack` (incluido con Node ≥16.9), sin
  instalación global aparte.


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
- **Integraciones configurables desde la web**: nueva tabla en la base de
  datos (`IntegrationInstance`) y CRUD completo
  (`GET/POST/PATCH/DELETE /api/settings/integrations`) para añadir, editar
  y borrar Proxmox/TrueNAS/AdGuard/Pi-hole/marcadores personalizados sin
  tocar `netscan.yaml` — las instancias definidas ahí se siguen mostrando,
  de solo lectura. Nuevo panel "Integraciones" en el dashboard con el
  formulario de alta/edición (campos según el tipo) y los botones de
  editar/borrar. Las credenciales se enmascaran (`••••••••`) en cualquier
  respuesta de la API y una edición que no las toca no las sobrescribe.
- **Pi-hole** (API v6, sesión por contraseña): nuevo cliente
  (`integrations/pihole.py`) y tarjeta en el dashboard, mismo patrón que
  AdGuard Home.
- **Marcadores personalizados**: tarjeta con logo propio (subida de imagen,
  PNG/SVG/JPG/WEBP hasta 2MB) + comprobación de arriba/abajo por HTTP HEAD,
  para cualquier servicio que no tenga una integración dedicada.
- Insignia de la cabecera rediseñada como un pequeño radar ascii
  (`◜◝ / ◟◞`, monoespaciada, sin el gradiente sólido anterior) — elegida
  entre 3 bocetos ascii mostrados como mockup antes de implementarla.
- Título ascii "NETSCAN" en la fuente `doom` de `pyfiglet` sobre la
  cabecera del dashboard, translúcido encima de los blobs de la aurora
  (degradado violeta/azul/teal/rosa con un barrido lento, sin tarjeta de
  cristal detrás) — generado con un script, no tecleado a mano, para
  garantizar que las 46 columnas de cada línea cuadran.

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
- Job `security` en CI (`pip-audit --skip-editable` + `npm audit`);
  dependencias con CVEs conocidos actualizadas (scapy, zeroconf,
  cryptography, starlette y varias transitivas del frontend).

### Corregido — CI en verde por primera vez en el histórico visible
- **react-hooks/rules-of-hooks real**: `QualityBadge` llamaba a
  `useAnimatedNumber` después de un `return` condicional — se movió antes,
  como exige React.
- **`security` (pip-audit)**: fallaba con "netscan-homelab: Dependency not
  found on PyPI" porque auditaba también el propio paquete, que nunca va a
  estar publicado ahí. Se instala editable + `--skip-editable` (no se puede
  combinar con `--strict`: trata el propio skip como un fallo).
- **`license-check`, dos bugs reales**: (1) la cabecera de `pip-licenses`
  ("Name Version License") no coincidía con ninguna licencia permitida, así
  que el job fallaba *siempre*, sin importar las licencias reales — se
  descarta con `tail -n +2`. (2) scapy declara "GNU General Public License
  v2 (GPLv2)" sin el "+", y la regex solo aceptaba `GPLv2\+` — GPL-2.0-only
  es compatible con el GPL-2.0-or-later de este proyecto, no una
  incompatibilidad real.
- **`backend` (subida de cobertura a Codecov)**: Codecov exige token incluso
  en repos públicos ahora; no hay `CODECOV_TOKEN` configurado.
  `fail_ci_if_error: false` — los 77 tests y el umbral de cobertura del
  49 % ya gatean la corrección por sí solos, esto era solo el reporte.

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

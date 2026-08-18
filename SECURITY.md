# Política de seguridad

## Alcance

NetScan es una herramienta de **automatización y monitorización de tu propia
red**. Ejecuta escaneos ARP, sondeos de puertos y (opcionalmente) auditorías
con nuclei. Úsala solo contra redes y equipos que te pertenecen o para los que
tienes autorización expresa.

## Modelo de exposición de la API

- Por defecto la API escucha en `127.0.0.1` y **sin autenticación**: solo es
  accesible desde el propio equipo.
- Si la expones fuera de localhost (`api_host: 0.0.0.0` o similar), define
  **siempre** `NETSCAN_API_TOKEN`. Todos los endpoints HTTP y el WebSocket lo
  exigirán (header `X-API-Key` o `Authorization: Bearer`).
- Los escaneos por API solo aceptan redes privadas (RFC 1918, loopback y
  link-local): no se puede usar la API como oráculo de escaneo de Internet.
- Los secretos (tokens de Proxmox/TrueNAS/AdGuard) deben llegar por variables
  de entorno, nunca commiteados en `netscan.yaml` (está en `.gitignore`).

## Herramientas externas

nmap, RustScan, nuclei, etc. se instalan por separado y se invocan como
procesos. `scripts/install-nuclei.ps1` verifica el SHA256 del binario contra
las checksums oficiales de ProjectDiscovery antes de instalarlo. Algunos
antivirus marcan nuclei como falso positivo (es una herramienta de auditoría);
si tu AV lo pone en cuarentena, NetScan funciona sin él.

## Reportar una vulnerabilidad

**No abras un issue público.** Escribe al mantenedor a través de
[GitHub Security Advisories](https://github.com/abarriuso/netscan/security/advisories/new)
con una descripción del problema, pasos para reproducirlo y el impacto
estimado. Se acusa recibo en un máximo de 7 días.

## Versiones soportadas

| Versión | Soportada |
| ------- | --------- |
| main    | ✅        |
| tags    | solo la última |

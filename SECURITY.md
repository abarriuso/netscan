# Security policy

## Scope

NetScan is a tool for **automating and monitoring your own network**. It runs
ARP scans, port probes and (optionally) audits with nuclei. Only use it against
networks and machines you own or are explicitly authorised to test.

## API exposure model

- By default the API listens on `127.0.0.1` with **no authentication**: it is
  only reachable from the machine itself.
- If you expose it beyond localhost (`api_host: 0.0.0.0` or similar), **always**
  set `NETSCAN_API_TOKEN`. Every HTTP endpoint and the WebSocket will then
  require it (`X-API-Key` header or `Authorization: Bearer`).
- Scans through the API only accept private networks (RFC 1918, loopback and
  link-local): the API cannot be used as an Internet scanning oracle.
- Secrets (Proxmox/TrueNAS/AdGuard tokens) must come from environment
  variables, never be committed in `netscan.yaml` (which is in `.gitignore`).

## External tools

nmap, RustScan, nuclei, etc. are installed separately and invoked as processes.
`scripts/install-nuclei.ps1` checks the binary's SHA256 against
ProjectDiscovery's official checksums before installing it. Some antivirus
products flag nuclei as a false positive (it is an auditing tool); if yours
quarantines it, NetScan works without it.

## Reporting a vulnerability

**Do not open a public issue.** Write to the maintainer through
[GitHub Security Advisories](https://github.com/abarriuso/netscan/security/advisories/new)
with a description of the problem, steps to reproduce it and the estimated
impact. Receipt is acknowledged within 7 days.

## Supported versions

| Version | Supported |
| ------- | --------- |
| main    | ✅        |
| tags    | latest only |

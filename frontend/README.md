# NetScan Dashboard

Frontend de NetScan: React 19 + TypeScript + Vite + Tailwind + shadcn/ui.

Consume la API del backend (`http://localhost:8600` por defecto) con polling y
un WebSocket de progreso de escaneo (`/ws/progress`).

## Desarrollo

```bash
npm install
npm run dev        # http://localhost:3000 (proxy a la API en :8600)
```

El backend debe estar corriendo (`netscan.bat serve` o `netscan serve`).

## Calidad

```bash
npm run lint       # ESLint
npm run typecheck  # tsc --noEmit
npm run build      # build de producción en dist/
```

## Autenticación

Si el backend tiene `NETSCAN_API_TOKEN` configurado, el dashboard pedirá el
token la primera vez que la API responda 401 y lo guardará en
`localStorage` (`netscan_token`).

## Docker

La imagen (`Dockerfile`) construye el estático con `npm ci` y lo sirve con
nginx; `nginx.conf` proxifica `/api` y `/ws` hacia el backend.

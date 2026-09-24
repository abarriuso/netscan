# NetScan Dashboard

NetScan's frontend: React 19 + TypeScript + Vite + Tailwind + shadcn/ui.

It talks to the backend API (`http://localhost:8600` by default) with polling
and a scan-progress WebSocket (`/ws/progress`). The interface is available in
English and Spanish (`src/i18n/`).

## Development

```bash
pnpm install
pnpm dev        # http://localhost:3000 (proxied to the API on :8600)
```

The backend must be running (`netscan.bat serve` or `netscan serve`).

## Quality

```bash
pnpm lint       # ESLint
pnpm typecheck  # tsc --noEmit
pnpm test       # Vitest
pnpm build      # production build in dist/
```

## Authentication

If the backend has `NETSCAN_API_TOKEN` set, the dashboard asks for the token the
first time the API answers 401 and stores it in `localStorage`
(`netscan_token`).

## Docker

There is no separate image for the dashboard: `docker/Dockerfile` builds it and
the backend serves it together with the API (see the main README).

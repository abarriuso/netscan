# One image: the backend serves the API and the built dashboard on the same
# port, just like `netscan up`. Build from the repository root:
#   docker compose up --build

# ── Dashboard build ─────────────────────────────────────────────────────────
FROM node:20-alpine AS dashboard
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && corepack pnpm install --frozen-lockfile
COPY frontend/ ./
RUN corepack pnpm run build

# ── Backend ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim
# The API finds the dashboard at ./frontend/dist relative to its working dir.
WORKDIR /app
COPY backend/pyproject.toml backend/README.md ./backend/
COPY backend/src ./backend/src
RUN pip install --no-cache-dir ./backend && mkdir -p /data
COPY --from=dashboard /app/dist ./frontend/dist
COPY netscan.example.yaml /etc/netscan/netscan.example.yaml

ENV NETSCAN_CONFIG=/config/netscan.yaml \
    NETSCAN_DATA_DIR=/data
EXPOSE 8600
CMD ["netscan", "serve"]

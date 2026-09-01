# Contribuir a NetScan

¡Gracias por contribuir! NetScan es GPL-2.0-or-later: al enviar un PR aceptas
que tu código se distribuye bajo esa licencia.

## Puesta en marcha

```bash
python -m venv backend/.venv
backend/.venv/Scripts/pip install -e "backend[dev]"
cd frontend && pnpm install
```

## Antes de abrir un PR

1. `cd backend && pytest && ruff check . && ruff format --check . && mypy src/netscan`
2. `cd frontend && pnpm lint && pnpm typecheck && pnpm build`
3. Si añades una dependencia Python, verifica que su licencia sea compatible
   con GPL-2.0-or-later (MIT/BSD/Apache/LGPL) y añádela a `NOTICE`.
4. Si integras una herramienta externa GPL/AGPL, **no la importes ni la
   distribuyas**: invócala como proceso externo con degradación elegante
   (ver `backend/src/netscan/scanner/tools.py`).
5. Actualiza tests y README si cambias comportamiento.

## Estilo

- Python: ruff (line-length 110), type hints obligatorios en APIs públicas.
- TypeScript: ESLint + strict mode; componentes shadcn/ui vendored no se
  editan a mano (regenerar con el CLI de shadcn).
- Commits: formato conventional (`feat:`, `fix:`, `docs:`, …) recomendado.

## Reportar bugs

Incluye: SO, versión de Python/Node, salida de `netscan caps`, y logs del
backend con el error.

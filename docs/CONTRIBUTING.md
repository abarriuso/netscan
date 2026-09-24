# Contributing to NetScan

Thanks for contributing! NetScan is GPL-2.0-or-later: by sending a PR you agree
that your code is distributed under that licence.

## Getting started

```bash
python -m venv backend/.venv
backend/.venv/Scripts/pip install -e "backend[dev]"   # Linux/macOS: backend/.venv/bin/pip
cd frontend && pnpm install
```

## Before opening a PR

1. `cd backend && pytest && ruff check . && ruff format --check . && mypy src/netscan`
2. `cd frontend && pnpm lint && pnpm typecheck && pnpm build`
3. If you add a Python dependency, check that its licence is compatible with
   GPL-2.0-or-later (MIT/BSD/Apache/LGPL) and add it to `NOTICE`.
4. If you integrate a GPL/AGPL external tool, **do not import or distribute
   it**: invoke it as an external process with graceful degradation (see
   `backend/src/netscan/scanner/tools.py`).
5. Update the tests and the README (`README.md` and `README.es.md`) if you
   change behaviour.

## Style

- Python: ruff (line length 110), type hints required on public APIs.
- TypeScript: ESLint + strict mode; vendored shadcn/ui components are not
  edited by hand (regenerate them with the shadcn CLI).
- Commits: conventional format (`feat:`, `fix:`, `docs:`, …) recommended.

## Reporting bugs

Include: OS, Python/Node version, the output of `netscan caps`, and the backend
logs with the error.

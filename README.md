# VisionKit

VisionKit project.

## Modules

- `web/`: Next.js web application.
- `backend/`: Python 3.10 backend, managed with uv.
- `ai/`: internal model inspection/inference service, managed with uv.

Runtime source metadata is stored in `data/visionkit.sqlite3` by `backend/app/db/` and `backend/app/modules/sources/`. Media files and database files under `data/` are local and ignored by Git.

## Local development

Install dependencies once:

```bash
(cd backend && uv sync)
(cd ai && uv sync)
(cd web && npm install)
```

From the project root (Linux/macOS, Python >=3.10):

```bash
./dev.py
```

The launcher starts AI, waits for its health API, then starts backend and checks
that its log collector can reach AI. Finally it starts the web development server
and verifies the frontend API proxy. It sets the internal URLs and CORS origins
for the selected ports automatically. No model is loaded until requested.

Preferred ports are frontend **3001**, backend **8000**, AI **8001**. If a preferred
port is occupied, the launcher chooses an unused port and prints the actual URL.
An explicitly requested port must be free; it never stops or takes over existing
services. Stop an earlier Next.js development session before starting another
against the same `web/` directory (Next.js permits only one dev server per checkout).

To use the ports from this working session:

```bash
./dev.py --web-port 3002 --backend-port 18000 --ai-port 18001
```

Stop the managed session from another terminal with `./dev.py --stop` (add the
same `--data-dir` if you started an isolated session). The launcher validates its
session lock/PID and does not stop manually started services. Duplicate launchers
against the same data directory are rejected before opening the database.

Keep the terminal open. **Ctrl+C** stops every process started by that invocation,
including Next.js children and AI workers. If a service exits unexpectedly, the
launcher reports the failure and shuts down its remaining services so backend is
not left running without AI. Other applications are unaffected.

Service stdout/stderr is saved in `data/dev-logs/{ai,backend,web}.log`, with up to
two rotated backups and a 5 MiB limit per file. The existing in-app runtime log
viewer remains available through backend; these launcher files are for startup
and process diagnostics. The launcher does not install dependencies or auto-reload
Python services; restart it after backend/AI code changes. Next.js retains HMR.

Useful test options:

```bash
# Separate database/files, without affecting your workspace data:
./dev.py --no-web --data-dir /tmp/visionkit-sandbox --backend-port 18100 --ai-port 18101

# Launcher port/readiness/signal/failure-cleanup regression tests:
python3 -m unittest discover -s tests -v
```

`--data-dir` overrides database, source, model and run paths for both Python
services. Without it, existing `VISIONKIT_*` storage settings keep working, with
`data/` in this repository as the default. The web calls backend via `/api/v1`.
API documentation is at the backend URL printed by the launcher, under `/docs`.

# VisionKit

VisionKit project.

## Modules

- `web/`: Next.js web application.
- `backend/`: Python 3.10 backend, managed with uv.
- `ai/`: internal model inspection/inference service, managed with uv.

Runtime source metadata is stored in `data/visionkit.sqlite3` by `backend/app/db/` and `backend/app/modules/sources/`. Media files and database files under `data/` are local and ignored by Git.

## Local development

Start Docker Desktop (or Docker Engine + Compose), then install dependencies once:

```bash
docker compose pull mediamtx
(cd backend && uv sync)
(cd ai && uv sync)
(cd web && npm install)
```

From the project root (Linux/macOS, Python >=3.10):

```bash
./dev.py
```

The launcher starts MediaMTX, then AI, waits for its health API, then starts backend and checks
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

## RTSP preview via MediaMTX / WebRTC

Camera preview uses RTSP/TCP → MediaMTX → WebRTC → browser `<video>`. Python only
handles source configuration, camera status and WHEP SDP signaling. Preview has
no frame decoding, JPEG encoding, image transfer or transcoding. The browser hook
keeps the same peer connection / MediaStream across client-side route changes.

`./dev.py` runs MediaMTX in Docker Compose using the official `bluenviron/mediamtx:1.21.3`
image, pinned by registry digest in `compose.yaml`. AI/backend/web stay local.
Preferred relay host ports are Control API 9997, WHEP HTTP 8889, ICE UDP+TCP 8189
and RTSP 8554; occupied ports are skipped. Each data directory gets its own Compose
project. Ctrl+C / `./dev.py --stop` stops and removes only that project's relay
container/network; saved sources, models and database remain under `data/`.

The launcher requires a running Docker daemon. It downloads the pinned image if
missing. `--no-media` uses an externally managed relay at backend
`VISIONKIT_MEDIAMTX_API_URL` / `VISIONKIT_MEDIAMTX_WEBRTC_URL`.
To run MediaMTX independently: `docker compose up -d mediamtx`, then
`./dev.py --no-media`; stop it with `docker compose down`.
Do not run both managed and independent modes at once.

Docker publishes the relay ports only on host loopback for local development;
listeners bind inside the container. Configuration is mounted read-only and there
are no data volumes for the relay. Camera LAN URLs are unchanged. When started
by the launcher, camera localhost/127.0.0.1/::1 is translated to
`host.docker.internal` only in the internal MediaMTX payload; the saved URL stays
unchanged. An independently managed relay can enable this with backend
`VISIONKIT_MEDIAMTX_SOURCE_HOST=host.docker.internal`.
For remote browsers, deployment must configure reachable ICE hosts/listeners and
TURN if needed; proxying HTTP alone does not forward WebRTC media. The Control API
must stay internal. H.264 without B-frames is the practical camera configuration;
unsupported browser codecs produce an actionable error rather than a transcode.

Authentication feedback comes from MediaMTX source state: available/ready means
media can be read; RTSP 401/403 in `lastError` means camera rejected access. The
`online` flag alone does not prove readable media or successful authentication.
Anonymous cameras may also be readable. Saved credentials remain in the local
source DB and MediaMTX internal config; public session/status responses contain no
camera URL. The form also supports checking an unsaved RTSP URL and showing video
without adding it to the library. Its URL configuration lives only in backend RAM
and MediaMTX until the last viewing lease ends. Saving is a separate explicit action.

See `web/src/features/video-stream/README.md` for the hook and lifecycle contract.

Docker integration checks (isolated containers, no workspace data):

```bash
VISIONKIT_RUN_DOCKER_TESTS=1 python3 -m unittest discover -s tests -v
(cd backend && VISIONKIT_RUN_DOCKER_TESTS=1 .venv/bin/python -m unittest discover -s tests -v)
```

Live AI now runs alongside preview: check RTSP → select model → configure → Run.
AI reads the shared MediaMTX RTSP relay and returns JSON annotations while WebRTC
video remains independent. The default is at most 5 AI FPS for 60 minutes,
configurable in the pipeline. Runs continue across routes and can be stopped from
the Run step after returning with the same configuration. `VISIONKIT_MEDIAMTX_RTSP_URL`
configures the relay address reachable by AI (launcher sets it automatically).

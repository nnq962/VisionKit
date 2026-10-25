# VisionKit

VisionKit project.

## Modules

- `web/`: Next.js web application.
- `backend/`: Python 3.10 backend, managed with uv.

Runtime source metadata is stored in `data/visionkit.sqlite3` by `backend/app/db/` and `backend/app/modules/sources/`. Media files and database files under `data/` are local and ignored by Git.

## Local development

Run in separate terminals:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd web
npm install
npm run dev -- --port 3001
```

The web source library calls the FastAPI backend through the Next.js `/api/v1` proxy. Image/screenshot files are saved in `data/sources/` and their metadata in SQLite. API documentation is available at `http://localhost:8000/docs`.

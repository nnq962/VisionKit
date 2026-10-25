# VisionKit Web

Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui (Radix), and Manrope.

## Development

```bash
npm install
npm run dev
```

## Routes and organization

```text
src/
  app/
    layout.tsx                  # Fonts, metadata, global providers
    page.tsx                    # Redirect / to /database
    (workspace)/                # Shared sidebar layout; absent from URLs
      layout.tsx
      database/page.tsx         # /database
      pipelines/yolo/page.tsx   # /pipelines/yolo
    dashboard/page.tsx          # Redirect the original demo URL to /database
  features/
    pipelines/yolo/             # YOLO-specific UI and configuration flow
  components/
    app-sidebar.tsx
    workspace-header.tsx
    ui/                         # shadcn primitives
  lib/navigation.ts             # Sidebar links and active route matching
```

Add workspace routes under `src/app/(workspace)/` to reuse the sidebar. Keep feature-specific components under `src/features/<feature>/` and add navigation entries in `src/lib/navigation.ts`.

The Database route is a placeholder. The YOLO source picker is integrated with the backend for persistent image/screenshot storage. Model configuration and inference are not connected.

## Checks

```bash
npm run lint
npm run build
```

## Source API integration

Run the backend on port 8000 before using the persistent library. Next.js proxies `/api/v1/*` to `http://127.0.0.1:8000`; set `VISIONKIT_API_URL` in the web server environment to use another backend address. Restart Next.js after changing its configuration/environment.

Images and one-shot screen captures preview locally first. Selecting “Lưu source để tái sử dụng” uploads the actual file and persists metadata; the saved library survives page reloads. It supports previews, rename, confirmed deletion and loading additional pages. Search filters currently loaded entries. Video, webcam and remote sources remain local configuration/preview features; their persistent upload and inference are not enabled yet.

`src/features/sources/api.ts` owns the HTTP contract. The reusable source module handles metadata, browser capture and library state; the four YOLO step components remain separate. The UI reports API errors and retries without falling back to sample data.

HEIC/HEIF files use the backend's transient `/api/v1/sources/inspect` endpoint for preview before saving, since browser HEIC decoding varies. This uploads temporarily but does not add to the saved library. After saving, `preview_url` displays a JPEG sidecar while the backend retains the original HEIC bytes. JPEG iPhone images continue to work with the normal local preview flow.

## Source drafts

`SourceProvider` lives in the shared workspace layout so changing routes does not destroy the current source picker state. `use-source-drafts.ts` keeps independent drafts for each source type, including the original File, HEIC preview Blob, URL text, display name and save preference. Selecting an existing library source does not replace a new-source draft.

Draft files and metadata are saved locally in IndexedDB (`visionkit-source-drafts`), not automatically uploaded to the saved library. Blob preview URLs are reconstructed after reload. A draft remains local to this browser/origin and can be explicitly discarded; saving to the backend removes it from the unsaved draft cache. Browser storage is best-effort: if unavailable/full, the UI reports that drafts are only retained during in-app navigation and warns before leaving/reloading. Files interrupted during metadata reading are retained with a retry action. Camera streams are never persisted, and are stopped when switching away or leaving the pipeline route.

## Model Hub

`/models` reads its catalog, saved model library and download jobs from `/api/v1/models`. Download progress uses actual backend byte counts; jobs survive navigation and reload, and can be cancelled or retried. Completed downloads are saved in backend SQLite/storage. There is no browser-only mock download or localStorage model library. Backend startup and model API details are documented in `../backend/README.md`.

## Pipeline model selection

The YOLO model step uses the real `/api/v1/models` library, or uploads custom `.pt`/`.onnx` weights with family/task metadata via `/api/v1/models/upload`. It selects saved model IDs, validates file availability before advancing, and displays browser upload progress. Reusable components and the selection provider live in `features/models/`; `steps/model-step.tsx` only composes them. IndexedDB retains model selection and unsaved upload drafts across routes and reloads. Runtime compatibility remains the responsibility of the AI module.

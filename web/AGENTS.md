<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## UI conventions

- When using shadcn Select, always wrap the items inside `SelectContent` with `SelectGroup`: `<SelectContent><SelectGroup>...</SelectGroup></SelectContent>`.

- Workspace routes share the container in `app/(workspace)/layout.tsx`: `max-w-6xl`, centered, page padding 16px on mobile and 32px from `md`. Do not add route-specific max-width or outer padding.
- Use `WorkspacePage` for page headings and 32px section gaps; use `WorkspaceSection` for panels with matching header/body/footer padding (16px mobile, 24px from `md`). Form groups use 24px gaps and label/control groups use 8px gaps.

- Keep product copy concise and professional: prefer short labels and statuses; omit repeated explanations of normal behaviour. Keep actionable errors and essential limitations, and avoid implementation details in the UI.

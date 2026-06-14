# FundOps Frontend

React 19 + TypeScript + Vite single-page app, served in production by the FastAPI backend.
Styling is a custom dark institutional design system (`src/styles/design-system.css`) — no CSS
framework.

## Development

Run `npm install && npm start` from the repo root first (sets up the venv and builds everything).
Then, for frontend work with hot reload:

```bash
npm run dev        # Vite dev server on :5173, proxies /api to :8000
npx tsc --noEmit   # typecheck
npm run build      # production build (output served by the backend)
npm run lint       # eslint
```

The API target defaults to `http://localhost:8000`; override with `VITE_API_TARGET` or `API_PORT`.

## Structure

- `src/pages/` — routed surfaces: Home (chat), Inbox, Runs, Markets, Portfolio, Library,
  Settings, Company Page, Artifact Reader, plus the workflow stage pages
  (Screener, Thesis, IC Review, Memo)
- `src/components/` — shared UI, including `chat/` (FundOps Chat) and `workflow/` (run surfaces)
- `src/api/` — typed API client; all backend calls go through `client.ts`
- `src/styles/design-system.css` — design tokens and shared component styles

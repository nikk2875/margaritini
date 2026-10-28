# Margaritini web application

The React + Vite client for Margaritini. Start the whole app (API, migrations and
web application) with `./run_app.sh` in the repository root (`./run_app_venv.sh`
runs it without uv, using the existing `.venv`), or work on the client alone
with the scripts below.

```bash
npm install     # once
npm run dev     # http://127.0.0.1:6002
npm run build   # type-check and bundle into dist/
npm run lint    # oxlint
```

## Layout

- `src/App.tsx` – workspace shell: canvas, selection and project actions.
- `src/components/` – header, details pane, connection details and the plan view.
- `src/lib/` – plan ordering and Markdown, download helpers, project-file parsing.
- `src/api/client.ts` – typed, project-scoped API client.

## Configuration

- `VITE_API_URL` – API base URL (default `http://localhost:8000/api`).
- `VITE_API_TOKEN` – sent as `X-Margaritini-Token` when the API is started with
  `MARGARITINI_API_TOKEN`.

The dev server and the API both listen on loopback only. A restrictive
Content-Security-Policy is injected into production builds by `vite.config.ts`;
the dev server runs without it because hot module replacement needs inline
scripts.

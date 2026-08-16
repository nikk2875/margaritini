## Goal
Harden and correct the Task Planner implementation: fix the critical Alembic/app database mismatch, close the security gaps in the API (unscoped object access, unvalidated import, permissive CORS, unbounded payloads, side-effecting GET, DB concurrency), fix domain-rule holes (re-parenting, dependency revalidation), tighten the frontend file-handling paths, and update `implementation_plan.md`, CI, and tests so these guarantees are documented and regression-tested.

## Steps

### A. Critical correctness: one database URL, one source of truth
1. `backend/alembic.ini` line 89 sets `sqlalchemy.url = sqlite:///./idea_planner.db`, while `backend/app/db/database.py` uses `sqlite:///./task_planner.db`. Migrations therefore never touch the file the app opens (`backend/task_planner.db` is currently 0 bytes ⇒ a fresh run has no tables). Fix by making the app the single source:
   - Add `backend/app/core/config.py` with a `pydantic_settings.BaseSettings` subclass (`pydantic-settings` is already a dependency but unused): fields `database_url: str = "sqlite:///./task_planner.db"`, `cors_origins: list[str] = ["http://localhost:6002"]`, `max_import_nodes: int = 2000`, `max_import_tasks: int = 20000`, `max_request_bytes: int = 5_000_000`, `api_token: str | None = None`; `model_config = SettingsConfigDict(env_prefix="TASK_PLANNER_", env_file=".env")`. Export a module-level `settings`.
   - `backend/app/db/database.py`: replace the hardcoded `DATABASE_URL` with `settings.database_url`. Resolve relative SQLite paths against the repository/backend root (e.g. `Path(__file__).resolve().parents[2]`) so the DB no longer depends on the process CWD.
   - `backend/alembic/env.py`: in both `run_migrations_offline` and `run_migrations_online`, call `config.set_main_option("sqlalchemy.url", settings.database_url)` (escape `%` as `%%`) instead of reading the value from `alembic.ini`; delete/blank the stale `sqlalchemy.url` in `backend/alembic.ini`.
   - Add a smoke test in `backend/tests/` that asserts `alembic upgrade head` produces the same tables as `Base.metadata` (or at least that both point at the same URL).

### B. Transport / exposure hardening
2. `backend/app/main.py`: set `allow_credentials=False` (no cookies or auth headers are used, and `True` combined with `allow_methods=["*"]`/`allow_headers=["*"]` is needlessly permissive), replace `allow_methods=["*"]` with the explicit verbs used (`GET, POST, PATCH, PUT, DELETE, OPTIONS`), `allow_headers=["Content-Type"]` (plus the auth header from step 4 if enabled), and read origins from `settings.cors_origins`.
3. `backend/app/main.py`: add `TrustedHostMiddleware` with `allowed_hosts=["localhost", "127.0.0.1"]` (DNS-rebinding protection for a local dev server), and add a small ASGI middleware that rejects requests whose `Content-Length` exceeds `settings.max_request_bytes` with HTTP 413 (and rejects missing/chunked bodies over the limit while streaming).
4. `backend/app/main.py` + `backend/app/api/routes.py`: add an optional shared-secret dependency (`X-Task-Planner-Token` compared with `hmac.compare_digest` against `settings.api_token`) applied via `APIRouter(dependencies=[...])`; when `api_token` is `None` the dependency is a no-op so local single-user use is unchanged. Mirror it in `frontend/src/api/client.ts` by sending `import.meta.env.VITE_API_TOKEN` when defined.
5. `run_app.sh`: pass `--host 127.0.0.1` to `uvicorn` explicitly and add `--host 127.0.0.1` (or `--strictPort`) to the Vite dev command / `frontend/vite.config.ts` `server.host = '127.0.0.1'`, so the API and UI can never be exposed on a LAN by an inherited default. Also `set -o pipefail` is present; add a check that `uv`/`npm` exist and fail with a clear message.
6. `frontend/index.html`: set a real `<title>` ("Task Planner") and add a restrictive CSP `<meta http-equiv="Content-Security-Policy">` allowing `default-src 'self'`, `connect-src 'self' http://localhost:8000`, `img-src 'self' data:`, `style-src 'self' 'unsafe-inline'` (React Flow injects styles). Document that the dev server needs a relaxed variant.

### C. Object-level authorization / IDOR
7. `backend/app/api/routes.py`: the routes `/nodes/{node_id}`, `/dependencies/{dependency_id}`, `/tasks/{task_id}`, `/actions/{action_id}/tasks*`, `/actions/{action_id}/task-settings` accept any UUID with no project scoping — anything reachable on the port can enumerate and mutate every project. Either (preferred) re-nest them under `/projects/{project_id}/…`, or add a helper in `backend/app/services/domain.py` such as `node_in_project(db, project_id, node_id)` and require the project id as a path segment. Update `frontend/src/api/client.ts` accordingly (it already threads `projectId` for most calls).
8. `backend/app/api/routes.py::delete_dependency`: also verify the edge belongs to the caller-supplied project once step 7 lands.

### D. Import endpoint hardening (largest attack surface)
9. `backend/app/schemas/schemas.py`:
   - `NodeCreate.description` has no length bound (only `NodeUpdate` caps it at 5000) and SQLite does not enforce `String(5000)`, so import/create can store unbounded text. Add `Field(max_length=5000)` to `NodeCreate.description` and reuse a shared annotated type.
   - Constrain `ProjectExport` list sizes with `Field(max_length=settings.max_import_nodes / max_import_tasks)` on `nodes`, `dependencies`, `tasks`, `task_settings`.
   - Add `model_config = ConfigDict(extra="forbid")` to `ProjectExport*` models so malformed/hostile documents are rejected rather than silently partially applied.
   - Align `ProjectCreate/ProjectUpdate.name` (currently `max_length=500`) with the `projects.name` column `String(200)` — pick one and make model, schema, and migration agree.
10. `backend/app/api/routes.py::import_project`: currently bypasses every domain rule. Rewrite so that after id remapping it validates the incoming graph *before* commit:
    - reject duplicate `ProjectExportNode.id` values;
    - reject parent references that form containment cycles or a third goal level, actions with children, and actions without a goal parent — reuse `validate_parent` / a new pure `validate_hierarchy(nodes)` helper in `backend/app/services/domain.py`;
    - reject tasks/`task_settings` whose `action_id` maps to a non-action node;
    - normalise task `position` per action to `0..n-1` (or reject duplicates) so the `uq_task_position` constraint cannot raise an unhandled `IntegrityError` → 500;
    - run dependency rules and the cycle check through `validate_dependency` for each imported edge;
    - wrap the commit in `try/except IntegrityError: db.rollback(); raise invalid(...)`;
    - replace `assert imported_node is not None` (stripped under `python -O`) with an explicit `if ... is None: raise invalid(...)`;
    - change `raise invalid(...)` inside `except KeyError as error` to `raise invalid(...) from error` and call `db.rollback()` first;
    - replace the per-node `db.flush()` loop with client-generated UUIDs plus a single `bulk_save_objects`/`add_all` to avoid O(n) round trips on large imports.
11. `backend/app/api/routes.py::export_project`: calls `project_or_404(db, project_id)` twice — store the project once and reuse `project.name`.

### E. Domain-rule gaps
12. `backend/app/services/domain.py::validate_parent`: it only checks the *moving* node's level, not its subtree. A primary goal that owns secondary goals can be re-parented under another primary goal, creating an illegal third level. Add a check that no descendant goal would exceed depth 2 (compute the subtree's goal depth and compare against the new parent's depth).
13. `backend/app/api/routes.py::update_node` / `convert_to_action` / `convert_to_goal`: after a successful re-parent or type change, existing dependencies may become invalid (e.g. sibling-action edges whose parents diverged, or action→parent-goal edges). Add a `revalidate_dependencies(db, node)` helper in `domain.py` that either rejects the change (422 with the offending edge) or deletes the now-invalid edges; document which behaviour is chosen and cover it in tests.
14. `backend/app/api/routes.py::convert_to_action`: if an `ActionTaskSettings` row already exists for the node (goal → action → goal → action round trip), `db.add(ActionTaskSettings(...))` raises an `IntegrityError` → 500. Use `db.get(...) or ActionTaskSettings(...)` / `db.merge`.
15. `backend/app/api/routes.py::create_task`: `max(position)+1` is racy and violates `uq_task_position` under concurrency → 500. Wrap the commit with `except IntegrityError: db.rollback()` and retry once, or serialise via a per-action transaction.
16. `backend/app/api/routes.py::get_task_settings`: a `GET` that inserts a row and commits. Make it read-only, returning a default `TaskSettingsOut(action_id=..., display_style=BULLETED)` when absent; keep persistence in the `PUT` handler only.
17. `backend/app/api/routes.py`: mutating nodes, dependencies, tasks, and task settings never touches `projects.updated_at`, so the "ordered by last modification" requirement in plan §6/§15 is not met. Add a `touch_project(db, project_id)` helper and call it from every mutating endpoint (or add an ORM event listener).

### F. Database robustness and performance
18. `backend/app/db/database.py`: in the existing `connect` listener also execute `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`, and pass `connect_args={"check_same_thread": False, "timeout": 30}`. FastAPI runs sync endpoints in a threadpool, so concurrent writers currently surface as `database is locked` 500s.
19. `backend/app/db/database.py::get_db`: add `except: db.rollback(); raise` around the `yield` so a failed request never leaves a dirty session in a pooled connection.
20. `backend/app/services/domain.py::descendants`: `Node.parent_id.in_(pending)` can exceed SQLite's bound-parameter limit for large trees — chunk `pending` into batches of ~500. In `delete_subtree`, the `sorted(..., key=lambda item: len(descendants(db, item)))` call re-walks the tree once per node (O(n²) queries); replace it with a single BFS that records depth and delete deepest-first (or rely on the `ON DELETE CASCADE` FK now that `PRAGMA foreign_keys=ON` is set, keeping the manual delete only as a documented fallback).
21. `backend/app/services/domain.py::validate_dependency`: the cycle walk plus the insert in `create_dependency` are not atomic; two concurrent requests can create a cycle. Perform the check inside the same transaction with `SELECT ... ` under a write lock (e.g. `BEGIN IMMEDIATE` for SQLite) or re-check after insert and roll back on failure.

### G. Frontend fixes
22. `frontend/src/App.tsx::PlanView.exportMarkdown`: `link.download = \`${project?.name ?? 'project-plan'}.md\`` uses the raw, user-controlled project name (path separators, `..`, newlines). Extract the sanitiser already used in `exportProject` into a shared `safeFileName(name, extension)` helper and use it in both places.
23. `frontend/src/App.tsx::importProject`: `JSON.parse(await file.text())` runs on an arbitrary file with no guard. Add a client-side size check (e.g. reject > 5 MB), a `try/catch` that reports "Not a valid project file", and a shape check that `format_version === 1` and `Array.isArray(nodes/dependencies/tasks/task_settings)` before POSTing.
24. `frontend/src/App.tsx::exportProject` / `exportMarkdown`: `URL.revokeObjectURL(url)` is called immediately after `link.click()`, which can abort the download in some browsers; defer it with `setTimeout(..., 0)` and append/remove the link from `document.body` for Firefox/Safari compatibility (plan §15 explicitly targets Safari).
25. `frontend/src/App.tsx::reverseConnection`: on failure it deletes then attempts to restore the edge with a best-effort `.catch(() => undefined)`, so a crash between the two calls loses data. Add a backend endpoint `PATCH /dependencies/{id}` (or `POST .../reverse`) that swaps predecessor/successor atomically with validation, and call that instead; expose it in `frontend/src/api/client.ts`.
26. `frontend/src/App.tsx`: split the file — it is a single 268-line module with several ~1000-character JSX lines (header block, `Detail`, `PlanView`). Extract `PlanView`, `Detail`, `ConnectionDetail`, `dependencyOrder`, and the markdown generator into `frontend/src/components/` and `frontend/src/lib/plan.ts` so they are reviewable and unit-testable. Note `@tanstack/react-query` is a declared dependency but unused — either adopt it for the fetch/refresh logic or drop it from `frontend/package.json`.
27. `frontend/src/assets/` contains unused `hero.png`, `react.svg`, `vite.svg` and `frontend/README.md` is the Vite template — remove or replace.

### H. Tests and CI
28. `backend/tests/test_api.py` (or new `backend/tests/test_import.py`, `test_security.py`): add regression tests for
    - malicious import: cyclic parents, third-level goals, action-with-children, duplicate task positions, tasks attached to goals, oversized lists → all 422 and no partial project left behind;
    - re-parenting a primary goal that owns secondary goals → 422 (step 12);
    - dependency revalidation after re-parent/convert (step 13);
    - goal→action→goal→action conversion round trip (step 14);
    - `GET /actions/{id}/task-settings` performs no write (step 16);
    - project `updated_at` bumps after node/task edits (step 17);
    - cross-project access is rejected once routes are scoped (step 7);
    - export/import round-trip data integrity (plan §19 lists it but no test exists).
29. `.github/workflows/ci.yml`: the plan's release checklist (§19) includes `uv run mypy backend/app` and the frontend lint, but CI runs only `ruff` + `pytest` + `vite build`. Add `uv run mypy backend/app` to the backend job and `npm run lint --prefix frontend` to the frontend job; pin `actions/*` versions already used.
30. `pyproject.toml`: enable stricter linting/typing — add `[tool.ruff.lint] select = ["E","F","I","B","S","UP"]` (Bandit `S` rules catch the `assert` and hardcoded-bind issues) with a per-file ignore of `S101` for `backend/tests`, and a `[tool.mypy]` section with `strict = true` for `backend/app`.

### I. Documentation
31. `implementation_plan.md`: add a new section (e.g. "§19a Security and robustness requirements") capturing the rules this work introduces — loopback-only binding, explicit CORS allow-list without credentials, optional API token, request-size and import-size limits, import validated by the same domain rules as the interactive API, project-scoped resource access, no side effects on GET, SQLite WAL + busy timeout, filename sanitisation for all downloads. Also correct §3 ("Create a local SQLite database configuration") to state that the app and Alembic must share one configured URL.
32. `README.md`: add a short "Security and data" note — the app is a single-user local tool with no authentication, listens on loopback only, stores everything in an unencrypted local SQLite file, and imported JSON should be treated as untrusted; mention the `TASK_PLANNER_*` environment variables introduced in step 1.

# Margaritini — Implementation Report

Status snapshot of the codebase as measured against `implementation_plan.md`
(sections §1–§20, including §19a security requirements) and
`verification_plan.md` (hardening steps A–I). Quality gates verified at the
time of writing: `ruff` clean, `mypy --strict` clean (16 files), **34/34
pytest tests passing**, `oxlint` clean, and `npm run build` succeeds.

---

## 1. Project overview

Margaritini is a single-user, local visual planning workspace:

- **Backend** — FastAPI + SQLAlchemy 2 + Alembic over SQLite, Python 3.13,
  managed with `uv` from the repository root.
- **Frontend** — React 19 + Vite + `@xyflow/react` (React Flow) canvas client,
  TypeScript, linted with `oxlint`.
- **Domain model** — projects contain nodes (goals/actions) in a two-level
  goal hierarchy, with actions carrying tasks; dependencies connect nodes
  under strict connection rules.

The three commits in the repository (`Initial development` → `Renamed
project` → `After verification with Opus`) indicate the full feature set was
built, then hardened per the verification plan. The working tree is clean.

---

## 2. Repository layout (plan §2)

| Path | Purpose | Status |
|---|---|---|
| `backend/app/` | API, models, schemas, services, middleware | ✅ |
| `backend/alembic/` | migrations (2 revisions) | ✅ |
| `backend/tests/` | 5 test modules + helpers + conftest | ✅ |
| `frontend/src/` | React app, split into `components/`, `lib/`, `api/` | ✅ |
| `plans/` | implementation + verification plans | ✅ |
| `run_app.sh` | one-step startup script | ✅ |
| `.env.example`, `.github/workflows/ci.yml`, root `pyproject.toml`, `uv.lock` | config | ✅ |

---

## 3. Backend implementation

### 3.1 Configuration — single source of truth (plan §3, verification A)

`backend/app/core/config.py` defines a `pydantic_settings.BaseSettings` class
(`SettingsConfigDict(env_prefix="MARGARITINI_", env_file=...)`) with:

- `database_url` (default `sqlite:///./margaritini.db`)
- `cors_origins` (both `localhost` and `127.0.0.1` on port 6002)
- `allowed_hosts` (loopback names only)
- `max_import_nodes` (2000), `max_import_tasks` (20000),
  `max_request_bytes` (5 MB)
- `api_token: str | None = None`

Relative SQLite paths are anchored to `backend/` via
`resolve_sqlite_url()` so the DB no longer depends on the process CWD. This
fixed the critical bug flagged in verification step A, where `alembic.ini`
pointed at `idea_planner.db` while the app used `task_planner.db` (the
default before the project was renamed to Margaritini). Today:

- `alembic.ini` has an empty `sqlalchemy.url` (line 90) — asserted by
  `test_alembic_ini_does_not_pin_a_database_url`.
- `backend/alembic/env.py` calls `config.set_main_option("sqlalchemy.url",
  settings.resolved_database_url)` in **both** offline and online modes.
- `backend/tests/test_migrations.py` proves `alembic upgrade head` produces
  exactly the tables and columns of `Base.metadata`.

The stale `backend/idea_planner.db` legacy file was deleted and the local
database files were renamed to `margaritini.db` (+ WAL/SHM files) during
the project rename.

### 3.2 Database engine (plan §3, verification F)

`backend/app/db/database.py`:

- `connect_args={"check_same_thread": False, "timeout": 30}` (FastAPI sync
  endpoints run in a threadpool).
- On connect: `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`,
  `PRAGMA busy_timeout=5000`.
- `get_db()` rolls back and re-raises on any exception, so a failed request
  never leaves a dirty session in the pool (verification step 19).

### 3.3 Data model (plan §4) — `backend/app/models/models.py`

| Model | Key fields / constraints |
|---|---|
| `Project` | `name` (200), `created_at`, `updated_at` (onupdate) |
| `Node` | FK project (cascade), self-FK parent (cascade), `node_type`
(goal/action enum), `text` (500), `description` (5000), canvas x/y, timestamps |
| `Dependency` | FKs predecessor/successor, `UniqueConstraint(project_id,
predecessor_id, successor_id)` |
| `Task` | FK action (cascade), `text`, `is_completed`, `position`,
`UniqueConstraint(action_id, position)` |
| `ActionTaskSettings` | PK = action FK, `display_style` (bulleted/numbered) |

### 3.4 Migrations (plan §5)

- `09d7f71e5caa_initial_schema.py` — projects, nodes, dependencies, tasks,
  task settings.
- `bf39a5c1d2e4_add_node_descriptions.py` — adds `nodes.description`
  (batch ALTER, server default `""`).
- Migrations run before startup in `run_app.sh`; smoke-tested in
  `test_migrations.py`.

### 3.5 API surface (plan §6–§9) — `backend/app/api/routes.py`

All routes are prefixed `/api` and carry the optional token dependency
(`APIRouter(prefix="/api", dependencies=[Depends(require_api_token)])`).
**Every node/dependency/task/task-settings route is nested under
`/projects/{project_id}/…`** — the IDOR fix from verification step C is
fully in place.

**Projects (§6)**

- `GET /projects` — ordered by `updated_at` descending
- `POST /projects`, `GET/PATCH/DELETE /projects/{id}`
- `GET /projects/{id}/export` — versioned JSON (`format_version: 1`) with
  name, nodes (titles, descriptions, positions), dependencies, tasks
  (text/completion/position), task styles
- `POST /projects/import` — remaps all identifiers to fresh UUIDs

**Nodes (§7)**

- `GET/POST /projects/{id}/nodes`, `GET/PATCH/DELETE
  /projects/{id}/nodes/{node_id}`
- `POST .../nodes/{id}/convert-to-action` and `.../convert-to-goal`
- Validation (in `backend/app/services/domain.py`): actions must have a goal
  parent; actions cannot contain children; secondary goals must have a
  primary-goal parent; a third goal level is rejected — **including on
  re-parent**, via `subtree_goal_depth()` which checks the depth of the whole
  moved subtree (verification step 12); parent/child must share the project;
  containment cycles rejected.
- **Dependency revalidation**: `revalidate_dependencies()` rejects
  re-parents and type conversions that would invalidate an existing edge
  (422 naming the offending rule) rather than silently deleting data — the
  chosen behaviour is documented in its docstring and covered by tests
  (verification step 13).

**Dependencies (§8)**

- `GET/POST /projects/{id}/dependencies`, `DELETE
  /projects/{id}/dependencies/{dep_id}`
- **`POST .../dependencies/{dep_id}/reverse`** — swaps predecessor/successor
  atomically in one transaction with validation (verification step 25)
- Validation: same project, no self-dependency, duplicates rejected via the
  unique constraint (caught as a clean 422), cycles rejected via
  `dependency_cycle_error()` graph walk, and connection rules:
  primary↔primary, secondary↔secondary (same level only),
  action↔sibling-action (same parent), action↔its own parent goal.

**Tasks (§9)**

- `GET/POST .../actions/{id}/tasks`, `PATCH/DELETE
  /projects/{id}/tasks/{task_id}`
- `PUT .../actions/{id}/tasks/reorder` — requires every task exactly once;
  uses temporary negative positions to dodge the per-action uniqueness
  constraint mid-reorder.
- `PUT/GET .../actions/{id}/task-settings` — **the GET is read-only** and
  returns the default (`bulleted`) when no row exists (verification step 16).
- `create_task` computes `max(position)+1` with an `IntegrityError` retry
  loop (3 attempts) instead of racing the unique constraint (verification
  step 15).
- Every mutating endpoint calls `touch_project()` so `updated_at` ordering
  is meaningful (verification step 17).

### 3.6 Import hardening (verification D) — the largest attack surface

`backend/app/services/domain.py` provides pure validation helpers reused by
the interactive API:

- `validate_import_hierarchy()` — duplicate node ids, unknown parent
  references, containment cycles, third-level goals, orphan actions,
  actions-with-children.
- `validate_import_dependencies()` — unknown references, duplicate edges,
  connection rules, cycle detection over the incoming graph.
- `validate_import_action_targets()` — tasks/settings may only attach to
  actions.

`routes.py::import_project` runs all of these **before** creating any rows,
renumbers task positions per action (duplicate positions are normalized,
not fatal), remaps ids to fresh UUIDs, adds rows in FK-safe order, and wraps
the commit in `except IntegrityError: rollback; 422` — nothing is stored
partially.

### 3.7 Schemas (plan §4/§6, verification D) — `backend/app/schemas/schemas.py`

- Shared annotated bounds: `Text` (1–500), `Name` (1–200, aligned with the
  column), `Description` (≤5000, applied to **create** as well as update).
- `ProjectExport*` models use `ConfigDict(extra="forbid")` — unknown fields
  rejected.
- Every export list is bounded with `Field(max_length=...)` derived from
  settings; `format_version: Literal[1]`.
- `ProjectExportTask.position` validated `ge=0`.

### 3.8 Security and robustness (plan §19a, verification B) — all implemented

- **TrustedHostMiddleware** with loopback `allowed_hosts` (DNS-rebinding
  protection) — tested with a hostile `Host` (400).
- **BodySizeLimitMiddleware** (`backend/app/middleware.py`) — rejects
  declared bodies over `max_request_bytes` (413) and undeclared/chunked
  bodies (411); tested with an oversized payload.
- **CORS**: `allow_credentials=False`, explicit method list, headers limited
  to `Content-Type` + the token header, origins from settings; tested that a
  foreign origin gets no `access-control-allow-origin` and that the
  allow-credentials header is absent.
- **Optional shared secret** (`backend/app/core/security.py`): the
  `X-Margaritini-Token` header is compared with `hmac.compare_digest`;
  disabled unless `MARGARITINI_API_TOKEN` is set; 401 paths tested. The
  frontend mirrors it with `VITE_API_TOKEN`.
- **No side effects on GET** — task-settings GET returns a default instead of
  inserting; regression-tested by comparing `updated_at` before/after.
- **Object-level scoping** — every helper (`get_project_node`,
  `get_project_action`, `get_project_task`, `get_project_dependency`) returns
  404 for ids belonging to other projects; 12 cross-project attempts tested
  (verification step C).
- **Robustness of bulk operations**: `chunked()` batches ids (500 per query)
  to stay under SQLite's parameter limit; `delete_subtree` deletes via
  level-ordered batches (leaves first, so it works regardless of FK cascade
  configuration) and cleans dependencies/tasks/settings first.

---

## 4. Frontend implementation

### 4.1 Structure (plan §10, verification G/26)

`App.tsx` (413 lines) holds state and orchestration; the previously monolithic
pieces were extracted as the verification plan required:

| Module | Responsibility |
|---|---|
| `src/components/Header.tsx` | app title, project dropdown, editable plan name, project action group, import file input, "Add primary goal", "Print plan" |
| `src/components/Detail.tsx` | node details pane (title/description editing, add child goals/actions, conversion, task management) |
| `src/components/ConnectionDetail.tsx` | dependency pane (reverse direction, delete) |
| `src/components/PlanView.tsx` | nested planning view + Markdown export |
| `src/lib/plan.ts` | `dependencyOrder` (topological sort with alphabetical tie-break), `planMarkdown` generator, `childrenOf`/`primaryGoals` |
| `src/lib/download.ts` | `safeFileName` sanitizer + `downloadBlob` |
| `src/lib/projectFile.ts` | client-side import validation (≤5 MB, JSON parse, shape check incl. `format_version === 1`) |
| `src/api/client.ts` | typed fetch wrapper, all calls thread `projectId` |

Unused Vite-template assets (`hero.png`, `react.svg`, `vite.svg`) are gone;
`frontend/README.md` is a real project README; the unused
`@tanstack/react-query` dependency was **dropped** from `package.json`.

### 4.2 Canvas and visuals (plan §10–§11)

- Grid workspace `75% / 25%` (canvas / details pane), responsive fallback at
  ≤700px.
- Elliptical nodes (`border-radius: 50%`) with dark text; primary goals light
  blue (`#cfe8ff`), secondary goals light pink (`#ffd9e3`), actions light
  yellow (`#fff1ad`) — no type icons or labels, per spec.
- Containment links: non-selectable, non-focusable dashed `smoothstep`
  connectors; dependency links: directional arrows (`arrowclosed` marker),
  editable via React Flow connect interaction.
- Controlled React Flow state (`useNodesState`/`useEdgesState`);
  `onNodeDragStop` persists positions through the API.
- Selection: node click, dependency edge click, empty-pane click clears both
  selections; the details pane stays blank until something is selected.
- New nodes are placed near the existing cluster (centroid + offset) for
  roots and near the parent (fixed offsets) for children.

### 4.3 Details pane and tasks (plan §12–§13)

- Title editing only after explicitly selecting the title button; Enter
  saves, Escape cancels.
- Goal-only description editor with an explicit **Save description** button.
- Goal-specific controls: *Add secondary goal* (primary only), *Add action*.
- Node deletion with `confirm()`; destructive controls styled red with white
  labels, normal controls blue with white labels (App.css).
- Tasks: add from the pane, click-to-edit text (Enter/Escape), checkbox
  completion with strike-through, bulleted/numbered style selector, move
  up/down buttons visible only in numbered mode, every move persisted via
  the reorder endpoint.

### 4.4 Dependencies (plan §14)

Drawing a connection calls the API and reports validation errors in an error
banner; selecting an arrow shows *Reverse direction* and *Delete connection*;
reversal uses the atomic `/reverse` endpoint (no delete-and-recreate data
loss); containment connectors are ignored on edge click.

### 4.5 Projects, files, and export (plan §15–§17, verification G/22–24)

- Project dropdown in modification order; editable title beside it;
  grouped New / Export / Load / Delete buttons.
- Import goes through the browser file picker and the
  `readProjectFile` guard before POSTing.
- Downloads use a shared `safeFileName()` sanitizer (both JSON export and
  Markdown export — closing the path-traversal filename hole) and
  `downloadBlob` appends the link to `document.body` and defers
  `URL.revokeObjectURL` with `setTimeout` for Safari/Firefox compatibility.
- **Print plan** replaces the canvas with a scrollable nested view:
  primary goal → secondary goals → their actions → direct actions, siblings
  ordered by topological sort of dependencies with alphabetical
  tie-breaking, task lists rendered in their stored style, completed tasks
  struck through; *Back to canvas* returns without data loss.
- **Export Markdown** generates a nested outline matching the displayed
  plan, preserving indentation, numbered/bulleted task styles, and
  `~~completed task~~` strike-through.

### 4.6 Transport hardening (verification B/5–6)

- `vite.config.ts`: dev and preview servers pinned to `127.0.0.1:6002`
  `strictPort`; a build-only `injectContentSecurityPolicy` plugin inserts a
  restrictive CSP meta tag (`default-src 'self'`, `connect-src` loopback API,
  `object-src 'none'`, `frame-ancestors 'none'`, `style-src` allows inline
  for React Flow).
- `index.html`: real `<title>Margaritini</title>`; a comment explains why
  the CSP is build-only (HMR needs relaxed scripts).

---

## 5. Startup, documentation, tests, and CI

### 5.1 Startup (plan §18) — `run_app.sh`

Checks `uv` and `npm` exist (clear error otherwise), requires
`frontend/node_modules`, runs `alembic upgrade head` before starting
uvicorn on **`--host 127.0.0.1`**, starts Vite on `127.0.0.1 --strictPort`,
prints both URLs, and traps EXIT/INT/TERM to kill and wait on both
processes on Ctrl+C.

### 5.2 Documentation (plan §18, verification I/31–32)

- `README.md` — user-facing: what the app does, install, start, basic
  workflow, plus the required **Security and data** note (single-user, no
  auth, loopback-only, unencrypted SQLite, untrusted imports, and the
  `MARGARITINI_*` / `VITE_*` environment variables).
- `.env.example` — documents every setting with comments.
- `implementation_plan.md` — already updated with §19a (security and
  robustness requirements) and §20 (final acceptance review) reflecting the
  hardened behaviour.

### 5.3 Tests (plan §19, verification H/28) — 34 tests, all passing

| File | Coverage |
|---|---|
| `test_api.py` (17) | action-parent requirement; goal-level limits; dependency connection rules (cross-level, sibling, parent-goal); conversion + cycle rejection; subtree deletion with dependency cleanup; multiple task creation & ordering; **re-parent with goal children → 422**; re-parent/conversion invalidated-dependency rejection; goal↔action conversion round trip keeping settings usable; GET task-settings performs no write; `updated_at` bumps after node/task edits; task reorder (incl. partial-list 422); atomic dependency reversal (incl. reversal that would close a cycle) |
| `test_import.py` (10) | export/import round-trip integrity (ids remapped, structure/payload preserved); containment cycles; third goal level; actions with children / orphan actions; duplicate node ids; unknown references; tasks on goals; invalid + cyclic dependencies; duplicate task positions normalized; oversized lists / unknown fields / over-long descriptions all 422 with no partial project |
| `test_security.py` (7) | 12 cross-project access attempts → 404 with data intact; cross-project parenting; cross-project dependency endpoints; unknown Host → 400; oversized body → 413; API token 401/200 paths; CORS allow-list without credentials |
| `test_migrations.py` (2) | `alembic.ini` pins no URL; `alembic upgrade head` matches `Base.metadata` |
| `test_import.py`/`conftest.py` | tests run on an isolated in-memory SQLite with FK enforcement — the dev DB is never touched |

### 5.4 Quality gates and CI (plan §19, verification H/29–30)

| Gate | Status |
|---|---|
| `ruff check` (select `E,F,I,B,S,UP`; `S101` ignored for tests) | ✅ clean |
| `mypy --strict` on `backend/app` | ✅ 16 files, no issues |
| `pytest` | ✅ 34 passed |
| `npm run lint` (oxlint) | ✅ clean |
| `npm run build` (`tsc -b` + vite) | ✅ builds, CSP injected |

`.github/workflows/ci.yml` runs all of the above on PRs and pushes to
`main`, with pinned `actions/*` versions, in separate backend/frontend jobs.

---

## 6. Verification plan status summary

| Verification step | Area | Status |
|---|---|---|
| A | One database URL for app + Alembic | ✅ Done (settings-driven, CWD-independent, smoke-tested) |
| B | Transport: CORS, TrustedHost, body limit, token, loopback binding, CSP | ✅ Done (all six sub-steps, all tested) |
| C | Project-scoped routes / IDOR | ✅ Done (all routes nested, 404s tested) |
| D | Import hardening | ✅ Done (schema bounds, `extra="forbid"`, full pre-commit validation, position normalization, atomic commit) |
| E | Domain-rule gaps (subtree re-parent, dependency revalidation, settings round trip, racy task creation, side-effect-free GET, `touch_project`) | ✅ Done (reject-and-report behaviour chosen and documented) |
| F | SQLite robustness (WAL, busy timeout, rollback in `get_db`, chunked queries, level-ordered deletion) | ✅ Done |
| G | Frontend (filename sanitiser, import guard, deferred revoke, atomic reversal, module split, template cleanup) | ✅ Done (all seven sub-steps) |
| H | Tests + CI (all regression tests, mypy/lint in CI, stricter ruff/mypy config) | ✅ Done |
| I | Documentation (plan §19a, README security note, `.env.example`) | ✅ Done |

---

## 7. Deviations and design decisions worth noting

1. **Dependency invalidation is reject, not delete** — when a re-parent or
   conversion would invalidate existing edges, the change is rejected with a
   422 naming the rule; the plan allowed either behaviour and required the
   choice to be documented (it is, in `revalidate_dependencies`'s docstring).
2. **Chunked body streaming** — the body-size middleware rejects undeclared
   (chunked) bodies outright rather than counting streamed bytes; justified
   by the fact that the only client is the bundled web app.
3. **Import task positions are normalized** (sorted, renumbered 0..n-1)
   rather than rejected on duplicates — the plan permitted either.
4. **Reversal endpoint is `POST .../reverse`** rather than `PATCH`, keeping
   the verbs explicit.
5. **Plan order is "dependencies first, then alphabetical"** —
   `dependencyOrder` implements Kahn's algorithm with alphabetical
   tie-breaking among ready nodes, matching §16.

---

## 8. Remaining observations (not blockers)

- **Local venv mismatch — resolved:** the `.venv` was originally created
  when the repository lived at `task_planner/`, so its script shebangs broke
  `uv run` after the rename to `margaritini/`. It was rebuilt with
  `uv sync --all-groups`, and `uv run` works again (`.venv/` is gitignored).
- **Stale `backend/idea_planner.db`** (the old mismatched Alembic target)
  still exists in the tree; it is harmless but could be deleted.
- **Concurrency of the cycle check** (verification step 21): the dependency
   cycle check plus insert are still not strictly atomic between two
   concurrent writers; SQLite's WAL + single-writer serialisation plus the
   unique-edge constraint make this practically unreachable for a
   single-user tool, but the plan's most defensive option (BEGIN IMMEDIATE)
   was not implemented.
- **No frontend unit tests** — the plan only requires lint + build for the
   frontend; `lib/plan.ts` and `lib/download.ts` were deliberately extracted
   to be unit-testable, but no test runner is configured for the frontend.
- **`ConnectionDetail` shows raw node UUIDs** (`{edge.source} →
  {edge.target}`) rather than node titles — cosmetic only.

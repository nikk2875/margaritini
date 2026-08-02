# Idea Planner Implementation Plan

## 1. Define product rules

- Model a project as a visual planning workspace.
- Support three planning item types:
  - primary goals;
  - secondary goals;
  - actions.
- Restrict goals to two levels:
  - primary goals are root items;
  - secondary goals belong to primary goals;
  - secondary goals cannot contain further goals.
- Require every action to belong to either a primary or secondary goal.
- Allow tasks only on actions.
- Define dependency rules:
  - primary goals connect only to primary goals;
  - secondary goals connect only to secondary goals;
  - actions can connect to their direct parent goal;
  - actions can connect to sibling actions that share a parent;
  - dependency cycles are rejected.

## 2. Create the repository layout

- Keep the web application in `frontend/`.
- Keep the API, data models, migrations, and tests in `backend/`.
- Keep the UV project configuration, lockfile, and virtual environment at the repository root.
- Add a root `.gitignore` for local environments, caches, databases, frontend dependencies, build output, and local configuration.
- Add a root `run_app.sh` script for one-step local startup.

## 3. Configure the backend project

- Define backend runtime and development dependencies in root `pyproject.toml`.
- Configure Python test imports so the `backend/` source directory is available when commands run from the repository root.
- Configure FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, Ruff, and MyPy.
- Create a local SQLite database configuration.
- Configure CORS for the local web application.
- Ensure Alembic, rather than application startup, owns schema creation.

## 4. Design persistent data

Create persistent models for:

- Projects:
  - name;
  - creation date;
  - modification date.
- Nodes:
  - project relationship;
  - parent relationship;
  - goal/action type;
  - title;
  - goal description;
  - canvas position;
  - timestamps.
- Dependencies:
  - project relationship;
  - predecessor and successor nodes;
  - uniqueness constraint.
- Tasks:
  - action relationship;
  - text;
  - completion state;
  - position;
  - uniqueness of a task position within an action.
- Action task settings:
  - action relationship;
  - bulleted or numbered display style.

## 5. Create database migrations

- Create the initial schema migration for projects, nodes, dependencies, tasks, and task settings.
- Add a migration for goal descriptions.
- Apply migrations before local startup.
- Verify migrations can upgrade an empty database and an existing local database.

## 6. Build project APIs

Implement endpoints to:

- list projects ordered by last modification date, descending;
- create a project;
- read and rename a project;
- delete a project and its contained data;
- export one project as a versioned JSON document;
- import a JSON document as a new project with safely remapped identifiers.

The project export format must include:

- project name;
- node hierarchy, titles, descriptions, and positions;
- dependencies;
- task contents, completion state, and order;
- action task display styles.

## 7. Build node APIs and validation

Implement endpoints to:

- list project nodes;
- create a node;
- update title, description, parent, and canvas position;
- delete a node and its subtree;
- convert an eligible goal to an action;
- convert an eligible action to a goal.

Validate that:

- an action always has a goal parent;
- an action cannot contain children;
- a secondary goal has a primary-goal parent;
- a third goal level cannot be created;
- parent and child belong to the same project;
- containment cannot form a cycle;
- conversion preserves containment and task rules.

## 8. Build dependency APIs and validation

Implement endpoints to:

- list dependencies for a project;
- create a dependency;
- delete a dependency.

Validate that:

- both nodes belong to the selected project;
- a node cannot depend on itself;
- duplicate dependencies are rejected;
- dependency cycles are rejected;
- connections follow the primary, secondary, and action rules.

## 9. Build task APIs and validation

Implement endpoints to:

- list tasks for an action in stored order;
- create a task;
- update task text and completion state;
- delete a task;
- reorder all tasks for an action;
- read and update the action task-list style.

Ensure that:

- tasks can be created repeatedly without position conflicts;
- reordering safely avoids temporary uniqueness conflicts;
- only actions expose tasks and task settings.

## 10. Build the frontend workspace

- Create a full-width application shell with a header, canvas, and persistent details pane.
- Make the canvas use 75% of the workspace and the details pane use 25%.
- Keep the details pane blank until an item or dependency is selected.
- Clear selection when the empty canvas is selected.
- Use controlled React Flow state for visible dragging and persisted node positions.
- Render containment links as non-editable dashed connectors.
- Render dependency links as editable directional arrows.

## 11. Build node visuals and creation controls

- Use ellipse-shaped nodes with readable dark labels.
- Use light blue for primary goals.
- Use light pink for secondary goals.
- Use light yellow for actions.
- Do not use node type icons or type-description labels.
- Add primary goals from the header.
- Add secondary goals from selected primary goals.
- Add actions from selected goals.
- Place new root nodes near the existing node cluster.
- Place new child nodes near their parent.

## 12. Build details-pane editing

- Allow title editing only after explicitly selecting the title.
- Save title changes on Enter and cancel them on Escape.
- Show a goal description editor for goals.
- Save descriptions through an explicit Save description control.
- Show goal-specific controls for adding secondary goals and actions.
- Show action-specific task controls.
- Provide node deletion with confirmation.
- Style normal controls blue with white labels and destructive controls red with white labels.
- Provide suitable spacing between detail controls.

## 13. Build task interaction

- Let users add a task from an action details pane.
- Let users click task text to edit it.
- Save task text on Enter and cancel editing on Escape.
- Render checked tasks with strike-through.
- Support bulleted and numbered task styles.
- Show move-up and move-down controls while numbered mode is active.
- Persist task ordering after every move.

## 14. Build dependency interaction

- Let users draw valid dependency arrows on the canvas.
- Show validation errors for invalid links.
- Let users select a dependency arrow.
- Provide controls to reverse arrow direction.
- Provide controls to delete an arrow.
- Keep containment connectors non-selectable and non-editable.

## 15. Build project controls and file handling

- Show projects in a dropdown ordered by modification date.
- Keep the project title editable and visually distinct beside the dropdown.
- Group New project, Export project, Load project, and Delete project controls.
- Use the browser file picker for loading JSON project files.
- Use browser-standard download behavior for JSON export so the workflow works in Safari and other browsers.
- Explain that final download location behavior is controlled by browser settings.

## 16. Build the nested planning view

- Add a Print plan control.
- Replace the canvas workspace with a scrollable planning view when it is selected.
- Provide a Back to canvas control.
- Organize the plan by containment:
  - primary goal;
  - its secondary goals;
  - each secondary goal’s actions;
  - direct actions under the primary goal;
  - next primary goal.
- Order sibling items by dependencies using a topological sort.
- Sort otherwise unconstrained sibling items alphabetically ascending.
- Render task lists under actions using their stored bulleted or numbered style.
- Render completed tasks with strike-through.

## 17. Build Markdown export

- Add Export Markdown to the planning view.
- Generate a nested Markdown outline matching the displayed plan.
- Preserve indentation for goals and actions.
- Preserve numbered and bulleted task-list styles.
- Render completed tasks as `~~completed task~~`.

## 18. Add startup and documentation

- Create `run_app.sh` to:
  - apply migrations;
  - start the API;
  - start the web application;
  - cleanly stop both processes on Ctrl+C.
- Write a user-facing README that explains what the app does, installation, startup, and basic use.
- Keep implementation details in this plan rather than the README.

## 19. Add tests and quality checks

Add regression tests for:

- action parent requirements;
- goal-level limits;
- dependency cycle prevention;
- valid and invalid cross-level connections;
- sibling-action connections;
- subtree deletion and dependency cleanup;
- multiple task creation and task ordering;
- project import/export data integrity.

Run before release:

```bash
uv run ruff check backend/app backend/tests
uv run mypy backend/app
uv run pytest -q
cd frontend && npm run build
```

## 20. Final acceptance review

Verify that a user can:

- start the app with one command;
- create, rename, switch, export, import, and delete projects;
- create and organize all goal/action levels correctly;
- create and edit tasks;
- create, reverse, and delete valid dependencies;
- inspect a nested, dependency-aware plan;
- export that plan as Markdown;
- return to the canvas without losing saved data.

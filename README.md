# Task Planner

Task Planner is a visual workspace for turning ideas into an actionable project plan.

Use it to create primary goals, break them into secondary goals, add actions and tasks, connect related work, and produce a clear written plan when you are ready to share it.

## What you can do

- Create primary goals and secondary goals.
- Add actions under either type of goal.
- Add, edit, complete, reorder, and style action tasks.
- Draw dependency connections between related items.
- Keep multiple projects, rename them, delete them, and switch between them.
- Export a project to a JSON file and load it again later.
- Open a nested project plan and export it as Markdown.

## Install

Install the required tools before starting:

- [uv](https://docs.astral.sh/uv/)
- Node.js 22 or later

Install the web-app packages once:

```bash
cd frontend
npm install
cd ..
```

## Start the app

From the project folder, run:

```bash
./run_app.sh
```

Then open [http://localhost:6002](http://localhost:6002).

Press `Ctrl+C` in the terminal to stop the app.

## Basic workflow

1. Create or select a project in the header.
2. Add a primary goal.
3. Select it to add secondary goals or actions.
4. Select an action to add tasks and choose its task-list style.
5. Drag items onto the canvas and draw connections where work depends on other work.
6. Use **Print plan** to review the nested plan or export it as Markdown.
7. Use **Export project** to save a portable copy, or **Load project** to bring one back into the app.

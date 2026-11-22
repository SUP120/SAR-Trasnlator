# Working on SAR Translator

Read [HANDOFF](docs/agent-memory/HANDOFF.md), [PROJECT_CONTEXT](docs/agent-memory/PROJECT_CONTEXT.md), [PROGRESS](docs/agent-memory/PROGRESS.md), [ARCHITECTURE](docs/agent-memory/ARCHITECTURE.md), [DECISIONS](docs/agent-memory/DECISIONS.md), [BUGS](docs/agent-memory/BUGS.md), [README](README.md), and [USER_ACTIONS](docs/agent-memory/USER_ACTIONS.md) in that order. Consult [the PRD](docs/PRD.md) for acceptance criteria and confirm the documented state against the code and test results.

- Keep Python logic typed, route handlers small, and TypeScript in strict mode. Keep geospatial computations independently testable.
- Calculate all reported measurements in the geospatial pipeline. Explanations can summarize those facts. Label synthetic fixtures explicitly and record measured results only after verification.
- Keep acquisition dates, scene metadata, processing parameters, and limitations visible. Use the PRD quality rubric and record threshold changes with their validation evidence.
- Preserve offline functionality. Keep credentials and bulky source data outside tracked files. Record dependency or architectural changes and why they were needed.
- Update the relevant memory files alongside implementation. In PROGRESS use `Done (tested)`, `Done (untested)`, `Partial`, or `Blocked`; include the commands and actual results. Leave one concrete continuation task in HANDOFF.
- Use small `type(scope): summary` commits when a Git repository is available. Follow [README](README.md) to install, run, and test locally.

# agent-console-mod-imports

Agent Console imports feature module. It plugs the import library `agent-console-imports` into the server.
It imports definitions by **copying** them from the settings of a project folder (`.claude/`, `CLAUDE.md`, `.mcp.json`). The originals are only read.
It does not read the user's global configuration (`~/.claude/agents`, `~/.claude/settings.json`, and so on); the app does not
reach outside registered project folders and its own workspace.

- Routes: `GET /resources/import/sources`, `POST /resources/import/preview` (no writes), and `POST /resources/import`.
- Required port: `definitions.store` (the store the imported definitions are written to). Optional ports: `secrets.rules` (the default suspicion rules without it),
  and `projects.folders` and `definitions.spaces` (below).
- Project assembly: when `projects.folders` is present, the source is `.claude/`, `CLAUDE.md`, and `.mcp.json` of the folder of the query
  `?project=<registration id>`, and `project_dir` is not used. The save location is the query `target`
  (`project` by default → that project's space `definitions.spaces`; `library` → the shared library `definitions.store`).
  Without `project`, only the sources that need no folder exist, `target=project` returns 422 `project.required`, and an unregistered id returns
  404 `project.not_found`. Without the ports (the module alone), the settings below apply as they are and `?project=` returns 409 `feature_unavailable`.
- Settings `modules.options.mod-imports` (the old top-level `imports` points to the new location with a `settings.removed_key` error.
  The old `home` (the user `~/.claude` source) was removed, and when it remains, a `settings.removed_key` error explains why):
  `project_dir` (empty = the host `paths.base_dir`, the settings file folder. The runs module's `working_directory` is not read
  as the default; to import the `.claude/` of a project folder, set this value directly) and `options` (source factory name → options).
- Web role: `imports`.

## Install

```bash
pip install agent-console-mod-imports
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-imports
```

## Minimal usage

Without a definition store, the module is off (with the reason reported). Assemble it with a providing module.

```python
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_imports import module
>>> from agent_console_mod_imports.testing import local_definitions_module
>>> assemble([module]).report[0].missing
('definitions.store',)
>>> [(r.id, r.state.value) for r in assemble([module, local_definitions_module()]).report]
[('local-definitions', 'active'), ('mod-imports', 'active')]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

Standalone run (the same modkit host, 127.0.0.1 by default). Without `--with`, it attaches `testing.local_definitions_module`
(a file store in the workspace folder). To use another provider, pass `--with <module id>`.

```bash
python -m agent_console_mod_imports [--with ID] [--config PATH] [--port 0] [--check]
```

# agent-console-link-runs-teams

Runs and teams link module. It connects team semantics (`ac-teams`) to the runs module (`mod-runs`).

- `runs.preparers`: after engine validation, the team rule check (`validate_team`; issues that mean the same as engine issues are dropped with `merge_validation`) and run preparation (`prepare_run`: allowed interactions and interaction wait settings).
- Pre-check (`TeamRules.preflight`, an optional method of `mod-runs`): before a run is created, when a node has no execution backend (`ac-teams.resolve_backends`, `unresolved_backends`), it returns 422 `backend.unresolved` (`details` = `BackendUnresolvedDetails{nodes, options}`, `fix.actions` = [Set on node] and [Set as default]). No run or turn record is left. The text, web route roles, settings section, and focus are `BackendFixTexts` data (`TeamRules(fix_texts=)`). Child runs are not pre-checked (the node fails with `agent.no_backend`).
- `runs.services`: node services (`ac-nodes-core` keys: agent and resource lookup, common settings, default backend, project folder, run file folder, nested team lookup `TEAM_LOOKUP`).
- Nested teams: reading teams (`load_graph(id, version_hash)` of `runs.starter`, including pinned versions) provides the node service `TEAM_LOOKUP` and the nesting checks of the team rules (`team.recursive`, `team.nesting_exceeded`, `team.team_not_found`, `team.child_no_entry`).
- Definition source of a run: when the run environment has `definitions` and the node service `RUN_DEFINITIONS` is set, the node services (`AGENT_LOOKUP`, `TEAM_LOOKUP` (including pinned versions), `RESOURCE_LOOKUP` (bodies and multiple files)) and the pre-run checks and pre-checks look only at that one source (`lookups_from(source) -> RunLookups`). Turning it on and off (no resource or team reading) works as before.
- `graphs.validation`: validation summaries for the team list (cached by workspace fingerprint, also dropped through the `definitions.saved` subscription). Space lists (`?project=`) use the optional method `space_summaries(space, ids, lookup=)`, computed only when `runs.starter` has the optional method `check_project(graph_id, project_id)` (`ProjectRunChecker`, the same definition source and run scope as a run start); otherwise null.
- Route `POST /graphs/{id}/validate` (a graph in the body or the saved one; 200 even with issues). The result = engine validation + team rules + the warnings and info of the optional port `definitions.checks` (pre-save definition checks; for example the pre-save definition warnings that other link modules raise, with their suggestions). Errors of the checks are not added because the save routes reject them with 422, and the same code, target, and path is reported once. Without a providing module, it is engine validation + team rules only (`definition_check_issues` and `with_definition_checks` also work without HTTP). With the optional query `?project=<id>`, the result is for running in that project (`check_project` and `load_graph(project_id=)` of `runs.starter`: the definitions and run scope of that space; items that exist only in the space are read too). Without `check_project`, 409 `feature_unavailable`; when the source provider blocks, that error (for example 422 `project.not_imported` for an item that is not in the space). In that case the pre-save checks are also for that space (the optional method `space_issues` of the checks, or `issues` when it is missing).

When this link is off, runs use only engine validation (`mod-runs` warns `team.rules_unavailable`), list validation summaries are null, and the validation route returns 404. Agent nodes fail with `agent.lookup_unavailable` because there is no agent lookup service, and nested team nodes fail with `team.lookup_unavailable` because there is no team lookup.

## Install

```bash
pip install agent-console-link-runs-teams
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-runs-teams
```

## Minimal usage

Assemble it with the companion module for standalone runs (`testing.local_runs_module`: a `runs.starter` that only validates, and a file definition store) and validate.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Graph
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_runtime import Registries
>>> from agent_console_link_runs_teams import RUN_PREPARERS, module
>>> from agent_console_link_runs_teams.testing import local_runs_module
>>> root = Path(tempfile.mkdtemp())
>>> paths = Paths(base_dir=root, workspace=root / "ws", state=root / "state")
>>> assembly = assemble([local_runs_module(), module], base=BaseServices(paths=paths, registries=Registries()))
>>> [(r.id, r.state.value) for r in assembly.report]
[('link-runs-teams', 'active'), ('local-runs', 'active')]
>>> [rules] = assembly.ports(RUN_PREPARERS)
>>> rules.workspace.agent_defaults.backend is None
True

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

### Fix button table

The mapping from validation issue and node failure codes to fix buttons (`Fix.actions`) is the data `data/issue_fixes.json` (no entry or reply edge,
no or unknown backend, unknown type, delegation depth). `TeamRules` attaches them to validation issues (the `mod-runs` optional method
`annotate_issues`), and through the node service `ERROR_FIXES` also to node failures (`agent.no_backend` of a child run, and so on).
To use another table, build it with `load_issue_fixes(text)` and pass it to `TeamRules(issue_fixes=)`.

In the server, change or turn it off with the administrator options (`modules.options.link-runs-teams`, `RunsTeamsLinkSettings`).

| Key | Default | Meaning |
| --- | --- | --- |
| `issue_fixes_file` | null | Fix button table JSON file. null or an empty string = the package default (`DEFAULT_ISSUE_FIXES`); a path = that file (a relative path is relative to the settings file folder; when the file is missing, a warning and an empty table); a file with `{"rules": []}` = no buttons |

`issue_fixes_of(path, base folder)` turns the option value into a table (also usable outside the module).

```python
>>> from agent_console_link_runs_teams import DEFAULT_ISSUE_FIXES
>>> fix = DEFAULT_ISSUE_FIXES.fix_for("team.no_entry", team_kind="graph", graph_id="g1")
>>> fix.actions[0].target.role, fix.actions[0].target.id
('definition:graph', 'g1')

```

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `runs.starter` | `check(graph)`, `load_graph(id, version_hash=None)` (also used for nested team lookup) |
| Required | `definitions.lookup` | `get(kind, id).document` (when the fingerprint inputs `kinds()` and `summaries(kind)` exist, they are used as the cache key) |
| Optional | `workspace.settings` / `resources.lookup` / `resources.types` | Common settings / resource lookup / resource types |
| Optional (several providers) | `definitions.checks` | `issues(kind, document) -> Sequence[Issue]` (adds warnings and info to the validation route), optional `space_issues(space, kind, document)` |
| Provides (multi) | `runs.preparers` / `runs.services` | `TeamRules` (the node services include the nested team lookup `TEAM_LOOKUP`, the team rules include the nesting checks) |
| Provides | `graphs.validation` | `ValidationSummaries.summaries(graph_ids)`, optional `space_summaries(space, graph_ids, lookup=)` |
| Subscribes | `definitions.saved` | Drops the validation summary cache |

## Standalone run

```bash
python -m agent_console_link_runs_teams [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_runs_module`. To actually run teams: `--with mod-runs --with mod-definitions`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

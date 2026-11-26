# agent-console-link-projects-runs

Agent Console projects and runs link module. It finds the project from a run's `project_id` (an opaque string) and inserts the
**project settings layer** (the project folder `working_directory` + the project `settings`) directly below the common layer.
The runs module (`mod-runs`) and the projects module (`mod-projects`) do not know each other; this link connects them.

- Receives (required): `projects.lookup`. When `mod-projects` is off, this link is off too. The optional method
  `get_view` (`ProjectView`) of the same object is used to check the status and the record database.
- Receives (optional): `definitions.spaces` (the definition source of a run = the project space) and `definitions.lookup` (the library;
  only for `in_library` of `project.not_imported`).
- Provides: `runs.scopes` (on every run start, the project layer in the node service `SCOPE_LAYERS`, the definition source
  `run_definitions`, and pre-check rejections `errors`) and `settings.scope_layers` (the effective settings routes with `?project=`).
- Pre-checks: `project.required` (422), `project.not_found` (404),
  `project.folder_missing` and `project.manifest_invalid` (409), `project.not_imported` (422, `in_library`),
  `project.records_unavailable` (409), and `project.outside_folder` (422, path, layer, node). Path fields are found only through the schema
  annotation `x-path` (agent settings + the `backend_options` schema of the effective backend). The app workspace and state
  folders are allowed, and `{workspace}` is checked as the project folder.
- Child runs (nested teams) inherit the parent's services and use the project layer and definition source of the root run. Path guarding checks
  the child and grandchild team nodes of nested teams before the start (node service `TEAM_LOOKUP`, taking pinned versions and the node's
  team layer overrides into account, `node_id` = `"<team node>/<child node>"`). Right before a child run is created, it checks once more with the child graph that will
  actually run (`check_child`, `mod-runs` `RunChildScoper`; when blocked, the node fails with `validation_failed` without a child run, and
  `details.issues[0].code` is `project.outside_folder`).
- Marker that it handles project scoping: `accepts_project(project_id)` (`mod-runs` `RunProjectScoper`), true when project
  reading is available.
- When this link is off, there is no provider that handles projects, so in an assembly with `mod-projects` on, `mod-runs` blocks runs and conversation turns that carry a
  `project_id` with 409 `feature_unavailable` (`details.port = "runs.scopes"`) so that nothing runs outside the project folder (the policy and text are the
  `mod-runs` setting `unscoped_project_runs`). Runs without a project and assemblies without `mod-projects` still run on their own.
- Settings `modules.options.link-projects-runs`: `layer_id` (default `project`), `layer_label` (the layer's display name),
  `unknown_message` (`string.Template`, variable `project`), and `require_project` (default true since 0.3.0: runs and conversation turns that start without a project return 422 `project.required`. To allow runs without a project, set it to `false`. The default of the `ProjectScope(require_project=)` constructor is still false).

## Install

```bash
pip install agent-console-link-projects-runs
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-projects-runs
```

## Minimal usage

Build a project layer without a server (project reading is injected).

```python
>>> from agent_console_contracts import Project
>>> from agent_console_link_projects_runs import ProjectScope
>>> from agent_console_link_projects_runs.testing import MemoryProjects
>>> projects = MemoryProjects([Project(id="app", name="App", folder="/w/app",
...                                    settings={"model": "m1"})])
>>> scope = ProjectScope(lambda: projects)
>>> [(layer.id, dict(layer.value)) for layer in scope.layers("app").layers]
[('project', {'model': 'm1', 'working_directory': '/w/app'})]
>>> [w.code for w in scope.layers("ghost").warnings]
['project.unknown']
>>> [e.code for e in ProjectScope(lambda: projects, require_project=True).scope_run(
...     None, {}, project_id=None).errors]
['project.required']

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Standalone run (with an empty in-memory projects module): `python -m agent_console_link_projects_runs --check`.
With the real modules: `--with mod-projects --with mod-runs`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

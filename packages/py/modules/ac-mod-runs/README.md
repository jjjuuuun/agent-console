# agent-console-mod-runs

Runs feature module. It plugs the run engine (`ac-runtime`) and run history (the legacy tables of `ac-store`) into the server.

- Routes: `POST/GET /runs` (`?root=` = all child runs under that root), `GET /runs/{id}` (`children` = direct children, in creation order), `POST /runs/{id}/cancel` (also propagated to child runs), `GET /runs/{id}/events`, interactions (`/runs/{id}/interactions…`, `GET /interactions` (`?root=` = those of the root and its child runs)), resume (`/runs/{id}/resume-options`, `POST /runs/{id}/resume`; a child run returns 409, resume its root instead), descriptors (`/node-types`, `/edge-types`, `/backends`, `/delegation-strategies`, `/interaction-kinds`, `/condition-operators`), the observe tab event prefixes (`GET /observe-event-prefixes`), and `GET /agents/{id}/activity`.
- Child runs (nested teams, `ctx.run_child`): `RunService.prepare_child` is plugged into the engine's child run preparer (`GraphRuntime.child_preparer`), so child runs go through the same preparer (`runs.preparers`) checks and preparation as regular runs. The services are those of the parent run (+ whatever the node adds).
- Condition operators: the host plugin loader reads `agent_console.condition_operators` into the named registry `condition_operators` of the bundle (report group of the same name), and the module gives that registry to the node and edge types that use operators (`ac-conditions.OperatorConsumer`). So operators turned off with `plugins.enabled` disappear from the list, the pre-save checks, and run-time evaluation together.
- Masking evaluation evidence: after the secret resolver is built, `secrets.redact` is given to the node and edge types that build evaluation evidence
  (`ac-conditions.RedactorConsumer`) (`plugins.bind_redactor`). Evidence is masked before it is truncated.
- WS topics: `run:<id>` (event replay → live) and `interactions` (waiting interactions).
- Storage: the run history tables (`runs`, `node_runs`, `run_events`, `interactions`) are owned by this module's migration lineage `runs` (`storage/migrations/versions`, version table `alembic_version_runs`). `runs_0001` is an empty baseline that takes over the tables legacy created, and `runs_0002` adds the lineage's new columns (`runs.root_run_id` and `parent_node_id`, `node_runs.call` and `invoked_by`, `interactions.root_run_id`) and indexes. When the module is off, the lineage is not applied. The store code is in `ac-store`. To roll back, roll back only the `runs` lineage (NodeRun rows with `call > 0` cannot fit the old primary key and are lost). Legacy is never downgraded.
- On startup, **the very first thing** it does is mark unfinished runs of the previous process as interrupted (`recover_unfinished_runs`).
- The engine does not know node types or team semantics. Team rules come through `runs.preparers`, node services through `runs.services`, and special paths such as resuming conversation turns through `runs.resume_handlers` (all of them multi-provider ports; when missing, only that part is off).
- Definition source per run: when the optional method `run_definitions(project_id, graph_id)` (`RunDefinitionsScoper`) of a `runs.scopes` entry returns a source (`DefinitionSource`: `get`, `get_version`, optional `read_content`, `list_files`, `read_file`), the root graph (current and versioned) and `graph_of_run` are read only from that source (no fallback to the library), and the source is passed to node service providers as `RunEnvironment.definitions` and to nodes, preparers, and child runs as the service `RUN_DEFINITIONS` (`runs.definitions`). When it returns an `ErrorInfo`, the run is rejected without being created (`RunPreflightError`). Without a `project_id` or without the method, the current behavior applies. `POST /runs` decides the source once through `RunService.start_graph`.
- Child run check: the optional method `check_child(graph, services, *, project_id)` (`RunChildScoper`) of a `runs.scopes` entry is called in a run with a `project_id` right before a child run (nested team) is created (before the team rule check). When it returns an `ErrorInfo`, the child run is not created and a blocking issue with the same code, text, and `details` is raised (node failure `validation_failed`, `details.issues[0].code`). Exceptions are logged and skipped.
- Project runs with no scope provider: the optional method `accepts_project(project_id) -> bool` (`RunProjectScoper`) of a `runs.scopes` entry finds the provider that handles the scope (project folder, pre-checks, definition source) of that `project_id`. When the optional port `projects.lookup` is present (the projects feature is on) but no provider accepts the project (for example, the projects and runs link is off), run starts, conversation turns, resumes, and project-based validation (`check_project`, `load_graph(project_id=)`) are blocked with 409 `feature_unavailable` (`details = {module, port: "runs.scopes", project_id}`) before the definition source is decided, and no run is created. While this is blocked, the `warnings` of `GET /server-info` contain a warning with the same code and `details.port` (the screens use it to disable the start button). Setting `unscoped_project_runs`: `policy` (`reject` by default · `allow` = run without a scope) and `message` (the error and warning text). Without a `project_id` or without `projects.lookup`, runs work on their own as before. Viewing the graph of past runs (`graph_of_run`) is not blocked.

### Run list page query (`GET /runs/page`)

Sorted by `created_at` and `id` in descending order; all conditions are combined with AND. Pass `next_cursor` as `cursor=` in the next request to continue with the same conditions. In an assembly with record spaces, `?project=` reads the folder record database to the end and then continues with the old records in the app database; both sources are filtered with the same conditions.

| Query | Meaning |
| --- | --- |
| `cursor` | `next_cursor` of the previous response (opaque; 400 `bad_request` when wrong; its source takes precedence over `source`) |
| `limit` | 1 to 1000 (default 50) |
| `project` · `source` | Runs of that project · record source (`project` by default; `app` = old records in the app database) |
| `root_only` | Root runs only (children hidden) |
| `status` (repeatable) | Statuses combined with OR |
| `graph_id` · `conversation_id` | Equality |
| `agent_id` | Runs with events that this agent left as the actor |
| `root` | All descendants under that root (the root itself is excluded) |
| `label=<key>=<value>` (repeatable) | Labels combined with AND (only root runs have labels) |
| `since` | Lower bound on `created_at` (epoch seconds, inclusive). Uses the `created_at` index |
| `q` | Partial match search (up to 200 characters, 422 when longer; leading and trailing spaces are removed, ignored when empty): run id, `graph_id`, and top-level string values of the input. ASCII case-insensitive; `%`, `_`, and `\` are literal characters. It cannot use an index, so it reads in sort order and stops when `limit` is filled. Team names and conversation titles are not searched (they belong to other features and databases, so that is the client's job) |

### Run counts per project (`GET /runs/project-counts`)

`ProjectCounts` (root run counts in total, without a project, and per project). In an assembly with record spaces, it counts the app database together with the record databases of registered projects that are not unregistered. With `?source=app`, only the app database is counted (for showing the records left in the app).

## Install

```bash
pip install agent-console-mod-runs
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-runs
```

## Minimal usage

It turns on with only definition reading (`definitions.lookup`). Without preparers (team rules), it runs with engine validation only and warns.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Graph
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_runtime import Registries
>>> from agent_console_mod_runs import RUNS_STARTER, SERVER_WARNINGS, module
>>> from agent_console_mod_runs.testing import local_definitions_module
>>> root = Path(tempfile.mkdtemp())
>>> paths = Paths(base_dir=root, workspace=root / "ws", state=root / "state")
>>> assembly = assemble(
...     [module, local_definitions_module()],
...     base=BaseServices(paths=paths, registries=Registries()),
... )
>>> [(r.id, r.state.value) for r in assembly.report]
[('local-definitions', 'active'), ('mod-runs', 'active')]
>>> sorted(i.code for source in assembly.ports(SERVER_WARNINGS) for i in source())
['runs.storage_memory', 'team.rules_unavailable']
>>> starter = assembly.port(RUNS_STARTER)
>>> graph = Graph.model_validate({"id": "g", "name": "g", "nodes": [{"id": "x", "type": "nope"}]})
>>> [i.code for i in starter.check(graph)]
['unknown_node_type']

```

A pre-run preparer is an object with `check` (issues to add after the engine issues) and `prepare` (allowed interactions and interaction settings). When another module provides one through `runs.preparers`, it is used for both validation and runs. When it has the optional method `preflight(graph, services) -> ErrorInfo | None` (`RunPreflight`), it is called on run start (regular, resume, conversation turn) after the blocking issue check, and when it returns an error, no run is created and that error is returned as it is (code, text, `details`, `fix`; the status comes from the code) (`RunPreflightError`). It is not called for child runs.

```python
>>> from agent_console_contracts import Issue
>>> from agent_console_modkit.testing import fake_module
>>> from agent_console_mod_runs import RUN_PREPARERS, RunPreparation
>>> class NeedsNodes:
...     def check(self, graph, engine_issues, services, *, strict):
...         return [] if graph.nodes else [Issue(severity="error", code="x.empty", message="빈 팀")]
...     def prepare(self, graph, services):
...         return RunPreparation()
>>> rules = fake_module(
...     "my-rules", kind="link", provides=[RUN_PREPARERS],
...     on_build=lambda ctx: ctx.provide(RUN_PREPARERS, NeedsNodes()),
... )
>>> assembly = assemble(
...     [module, local_definitions_module(), rules],
...     base=BaseServices(paths=paths, registries=Registries()),
... )
>>> starter = assembly.port(RUNS_STARTER)
>>> [i.code for i in starter.check(Graph.model_validate({"id": "g", "name": "g"}))]
['x.empty']
>>> sorted(i.code for source in assembly.ports(SERVER_WARNINGS) for i in source())
['runs.storage_memory']

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Provides | `runs.starter` | `RunService` (`start_run`, `check`, `check_project`, `engine_issues`, `load_graph`, `cancel`, `current_run`, `shutdown`, `resume`) |
| Provides | `runs.reader` / `runs.events` | The store's run and event repositories (read) |
| Provides | `interactions.port` | `InteractionService` (`list`, `get`, `pending`, `respond`) |
| Provides | `secrets.redact` | `(str) -> str` |
| Provides | `runs.move_hook` | `ConversationRunMove` (`busy`, `prepare`): when a conversation is moved to a project record database, its runs move in the same operation (only when there is an app database). Old runs in the app database use `POST /runs/move-to-project` |
| Provides (multi) | `server.warnings` / `server.attributes` | `team.rules_unavailable`, `runs.storage_memory` / `{"recovered_runs": n}` |
| Topic | `runs.event` / `interactions.updated` | `RunEvent` (everything that was saved) / `Interaction` |
| Required | `definitions.lookup` | `get(kind, id).document`, `get_version(kind, id, hash).content` |
| Optional (multi) | `runs.preparers` / `runs.services` / `runs.resume_handlers` | `RunPreparer` / `RunServiceProvider` / `ResumeHandler` |
| Optional | `workspace.settings` / `secrets.rules` | Whether suspected-value masking is on, and the rules |

## Backend readiness and connection test

| Route | Response | Notes |
| --- | --- | --- |
| `GET /backends/status` | `BackendReadiness[]` | Static checks of all registered backends. Backends without the capability have `state: unknown` |
| `GET /backends/{id}/status` | `BackendReadiness` | 200 even without the capability (`unknown`); only an unknown id returns 404 |
| `POST /backends/{id}/probe` | `BackendProbeResult` | Body `BackendProbeRequest{timeout_s?}` (optional). Without the capability, 409 `backend.probe_unsupported` (`details.backend`) |

The module does not know backend ids or status names; it only passes the registry to the ac-runtime `BackendReadinessService`. Responses have
`Cache-Control: no-store` and are not recorded in run history or events. Response text is sent after masking the values of environment variables whose names look like secrets
(the rules of the `secrets.rules` port, or the ac-secret-rules default rules without it), resolved `secret://` values, and suspected value patterns
(`readiness.build_check_redactor`). The server log keeps only the backend id, ok, reason, and duration.

## Backend account sign-in

Starts and completes the sign-in to an execution backend account (for example a Claude subscription) from the app screen. The module does not know backend ids or sign-in methods;
it only passes the registry to the ac-runtime `BackendLoginService` (optional capabilities `login` and `logout`). When the setting
`backend_login.enabled` (on by default) is turned off, the routes below do not exist.

| Route | Response | Notes |
| --- | --- | --- |
| `POST /backends/{id}/login` | 201 `BackendLoginSession` | Body `BackendLoginStartRequest{method_id?, timeout_s?}` (optional). 409 `backend.login_unsupported`, `backend.login_busy` (`details.session_id`), or a code the backend rejects with (for example `backend.subscription_auth_disabled`). Errors during startup give a session with `phase: failed` |
| `GET /backends/login/current` | `BackendLoginSession` or 204 | The session in progress (one for the whole server) |
| `GET /backends/login/{sid}` | `BackendLoginSession` | Polling = heartbeat. A finished session returns 404 `backend.login_session_not_found` after `retain_s` |
| `POST /backends/login/{sid}/input` | 202 | Body `BackendLoginInput{text}` or `{key}`. Over 4 KB returns 413; when input cannot be accepted, 422 (`details.reason`). The value never appears in responses, logs, or errors |
| `DELETE /backends/login/{sid}` | `BackendLoginSession` | Cancel (ends the child process); a finished session stays as it is |
| `POST /backends/{id}/logout` | `BackendLogoutResult` | 409 `backend.logout_unsupported`; 409 `backend.login_busy` while the same backend is signing in |

All of these have `Cache-Control: no-store` and sit behind the local token, Origin, and Host checks. Nothing is recorded in run history, events, or WS. Response
text is masked like the readiness responses, and in addition the input values that entered the session (and their fragments of 5 or more characters) are masked. The server log keeps only the session id,
backend id, method id, phase, reason, and duration. The shutdown hook cancels the session in progress.

## Settings (`modules.options.mod-runs`)

| Key | Default | Description |
| --- | --- | --- |
| `runtime.max_concurrency` | null | Limit on the number of nodes running at the same time |
| `runtime.cancel_grace` | 2.0 | Seconds to wait after cancel |
| `runtime.event_queue_size` | 10000 | Subscriber queue size of the event bus |
| `runtime.shutdown_timeout` | 10.0 | Maximum seconds to wait for run cleanup on shutdown |
| `backends.<id>` | {} | Values passed to the backend's `from_options` hook (the backend defines the keys) |
| `working_directory` | base_dir | The agents' project folder |
| `run_files_dir` | `runs` | Folder for run bundle files (relative to the state folder) |
| `min_redact_chars` | 4 | Secret values shorter than this are not masked in records |
| `backend_probe_timeout_max_s` | 20 | Maximum wait in seconds for the backend [Test connection] (the request `timeout_s` is capped at this value) |
| `backend_login.enabled` | true | Backend sign-in and sign-out routes for the app screen (none when off) |
| `backend_login.timeout_s` / `timeout_max_s` | 300 / 900 | Default sign-in time / request limit (seconds) |
| `backend_login.heartbeat_s` | 30 | Cancel when polling stops for this long (seconds) |
| `backend_login.retain_s` | 60 | How long a finished session can still be read (seconds) |
| `backend_login.screen_max_lines` | 40 | Maximum lines of the response `screen` |
| `resume_origin` | `resume` | The `origin` of resume runs that no handler took |
| `activity_limit` | 100 | Default number of agent activity items |
| `observe_event_prefixes` | null | Event type prefixes that the *Observe* tab of the run detail collects (`GET /observe-event-prefixes`). null = the package default data (`data/observe_event_prefixes.json`, `hook.` and `mcp.`); a list = that list (spaces, empty values, and duplicates cleaned up); `[]` = observe tab off (runs and event storage do not use this value, so they keep working) |
| `issue_fixes_file` | null | Fix button table for run errors (JSON). null = the package default data (`data/issue_fixes.json`: `child_resume{label, role}`, the [Open top-level run] button when resuming a child run is rejected (409), role `runs`, id = root run). A relative path is relative to the settings file folder; when the file is missing or `child_resume` is empty, there is no button (`load_child_resume_fix`, `child_resume_fix_of`) |

The observe tab prefix table also works without a server (a replacement file has the same JSON shape `{"prefixes": [...]}`).

```python
>>> from agent_console_mod_runs import (
...     DEFAULT_OBSERVE_EVENT_PREFIXES, load_observe_event_prefixes, observe_event_prefixes_of,
... )
>>> DEFAULT_OBSERVE_EVENT_PREFIXES
('hook.', 'mcp.')
>>> load_observe_event_prefixes('{"prefixes": ["otel.", "otel.", " "]}')
('otel.',)
>>> observe_event_prefixes_of([])
()

```

The integrated server does not read the old top-level `runtime`, `backends`, and `working_directory`; it refuses them with an error that points to the new location (`settings.removed_key`).

## Standalone run

```bash
python -m agent_console_mod_runs [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_definitions_module` (a file store in the workspace). Run history is in `<state>/console.sqlite3`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

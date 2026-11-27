# agent-console-server

The Agent Console server. It loads the settings, sets up the host base services (registries, database, plugin
loaders, extension points), **assembles the modules (`agent-console-modkit`)** (the installed feature and link module
entry points), and serves FastAPI REST (`/api/v1`) and WebSocket (`/ws`). The server passes the modules to `assemble`
and only attaches the routers, WS topics, and error maps it gets back. It does not know feature names.
By default the web runs as a **separate process** (CORS + token). When you turn on `web.serve_static` (optional, off by
default), one server also serves the web build (see "Single process" below).
Business logic (validation, runs, team meaning, chat, usage, import rules) lives in the packages and modules. This app
only assembles them and handles the transport layer.

## Install

```bash
uv sync --all-packages          # inside the workspace
uv pip install ./apps/server    # standalone
```

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `fastapi` | REST and WS routing, OpenAPI | Uses the Pydantic contract models directly as request and response models | Starlette alone: OpenAPI and body validation would have to be written by hand |
| `uvicorn` | ASGI server | The standard FastAPI runner, with WS support | hypercorn |
| `websockets` | uvicorn WS implementation | The default uvicorn WS backend | wsproto |
| `ruamel-yaml` | Reads `agent-console.yaml` (safe loader) | The same library as the store | PyYAML |
| `pydantic`, `starlette` | Settings models, middleware | The server imports them, so they are declared as direct dependencies | — |
| Agent Console packages used directly | `agent-console-contracts`, `registry`, `secret-rules`, `modkit[host]` | Contract models, registries, secret rules, module assembly, security middleware, host extension points | — |
| Plugins that are only installed | `agent-console-resources-core`, `nodes-core`, `delegation-host`, `backend-claude-sdk[login]`, `backend-fake-agent`, log sources `logs-claude` and `hook-probe` | Default resource kinds, nodes, delegation strategies, execution backends (including the subscription sign-in PTY), log sources. The server does not import them; they come in through entry points only | — |
| Feature and link modules | `agent-console-mod-*` and `agent-console-link-*` (the tables in "Module assembly") | Install dependencies only. The server does not import them and assembles them through the entry point `agent_console.server_modules` (enforced by import-linter). Leave out modules you do not need when installing, or turn them off in the settings | — |
| `httpx` (dev) | `TestClient` | Required by the FastAPI test client | — |

CORS is handled inside the security middleware instead of the Starlette `CORSMiddleware`: a preflight request must
pass the Host check first, and error responses from the security checks (401, 403, 413) must also carry the allowed
origin headers so that the web can read them.

## Minimal usage

```python
from agent_console_server import create_app, load_settings, serve

settings = load_settings()  # agent-console.yaml + AGENT_CONSOLE_* environment variables
app = create_app(settings)  # ASGI app (the parts are assembled in the lifespan)
serve(settings)  # runs uvicorn (blocks)
```

```bash
python -m agent_console_server --config agent-console.yaml --port 8765 --disable-module mod-exports
```

There is one command line, `main(argv, *, prog=, modules=)`. `python -m agent_console_server` and
`agent-console serve` (apps/cli) take the same options: `--config/-c`, `--host`, `--port`, `--workspace`,
`--allow-origin ORIGIN` (repeatable, appended after `security.allowed_origins` from the settings, `merge_origins`),
`--open/--no-open`, `--enable-module`, `--disable-module`, and the options that installed modules declare with
`SettingsCompat.flags` (the default modules declare none today). A settings error writes `<prog>: …` to standard error
and exits with code 2.

The server starts with an empty workspace. Users create agents and teams themselves or bring them in with an import
(`mod-imports`).

## Module assembly

`create_app` assembles the modules installed through the entry point `agent_console.server_modules`
(`installed_modules()`; tests pass `create_app(modules=[...])`) with
`agent_console_modkit.assemble(modules, settings.modules)`. **The server does not know feature names** (the
import-linter contract "server app uses only modkit and base packages" and `tests/test_agent_console_server_assembly.py`).
Link module routers are attached first, so that their fixed sub-paths are not hidden by the parameter paths of
feature modules.

The host base services also come from what installed packages announce through modkit extension points: the registry
bundle factories (`agent_console.host_registries`) and plugin loaders (`agent_console.host_plugin_loaders`) →
`load_host_plugins`, the database factory (`agent_console.host_database`) → `open_host_database`, and secret
resolution (environment variable `secrets.env_prefix` → the secret providers of the bundle) → `secret_resolver`.
Removed settings keys, module environment variables, and module command-line options are handled by each module's
`settings_compat` declaration (`settings_compat()`, `flag_overrides()`). `GET /health` returns 200 only after the module
start hooks have finished (503 `not_ready` before that and after shutdown).

Installed modules come from the entry point `agent_console.server_modules`; their web roles are the `web_roles` of
`/modules`. The packages are in `packages/py/modules/` and `packages/py/links/`. Each module's settings live under
`modules.options.<module id>` (the keys are in each module README). The ports each module requires, may use, and
provides are listed in its README and reported at run time by `GET /api/v1/modules` (`requires`, `provides`).

### Feature modules

| Module id | Package | Routes and WS | Web roles |
| --- | --- | --- | --- |
| `mod-architecture` | [`ac-mod-architecture`](../../packages/py/modules/ac-mod-architecture/README.md) | `/architecture/…` (profiles, profile check, projection) | `architecture` |
| `mod-chat` | [`ac-mod-chat`](../../packages/py/modules/ac-mod-chat/README.md) | `/conversations…` (conversations, turns, messages, queue), WS `conversation:` | `conversations` |
| `mod-definitions` | [`ac-mod-definitions`](../../packages/py/modules/ac-mod-definitions/README.md) | `/agents`, `/graphs` (CRUD, duplicate), `/settings`; in-process topic `definitions.saved` | `definitions:agent`, `definitions:graph`, `settings` |
| `mod-exports` | [`ac-mod-exports`](../../packages/py/modules/ac-mod-exports/README.md) | `/exporters`, `/exports/*` | `exports` |
| `mod-i18n` | [`ac-mod-i18n`](../../packages/py/modules/ac-mod-i18n/README.md) | `/i18n`, `/i18n/{lang}` (message catalogs) | `i18n` |
| `mod-imports` | [`ac-mod-imports`](../../packages/py/modules/ac-mod-imports/README.md) | `/resources/import/*` | `imports` |
| `mod-logs` | [`ac-mod-logs`](../../packages/py/modules/ac-mod-logs/README.md) | `/logs…` (sources, classifiers, collection, events, sessions, timeline, totals, handoffs, taxonomy, dashboard templates, schema), WS `logs` | `logs` |
| `mod-memory` | [`ac-mod-memory`](../../packages/py/modules/ac-mod-memory/README.md) | `/memory/…` (scope kinds, scopes, tags, entries, versions, retention, export, import, copy), WS `memory.changed` | `memory` |
| `mod-projects` | [`ac-mod-projects`](../../packages/py/modules/ac-mod-projects/README.md) | `/projects…` (CRUD, folder browse, check, and pick, copy plan and apply, copied items, legacy plan, manifest reset) | `projects` |
| `mod-resources` | [`ac-mod-resources`](../../packages/py/modules/ac-mod-resources/README.md) | `/resources…` (CRUD, content, files), `/resource-types`, `/merge-strategies` | `definitions:resource` |
| `mod-runs` | [`ac-mod-runs`](../../packages/py/modules/ac-mod-runs/README.md) | `/runs…`, `/interactions`, descriptors (`/node-types`, `/edge-types`, `/backends`, `/delegation-strategies`, `/interaction-kinds`), `/agents/{id}/activity`, resume, backend status, sign-in (`backend_login`), WS `run:` and `interactions` | `runs` |
| `mod-sdd` | [`ac-mod-sdd`](../../packages/py/modules/ac-mod-sdd/README.md) | `/sdd/…` (info, specs, check, tasks, plan, trace, syntax, import, export, templates), WS `sdd.changed` | `sdd` |
| `mod-usage` | [`ac-mod-usage`](../../packages/py/modules/ac-mod-usage/README.md) | `/usage` (`?parts=`), `/usage/sources` | `usage` |
| `mod-versions` | [`ac-mod-versions`](../../packages/py/modules/ac-mod-versions/README.md) | `{collection}/versions…` | `versions` |
| `mod-wiki` | [`ac-mod-wiki`](../../packages/py/modules/ac-mod-wiki/README.md) | `/wiki/…` (info, changes, wikis, pages, link graph, lint, scan, wiki rules), WS `wiki.changed` | `wiki`, `wiki:rules` |

### Link modules

| Module id | Package | Routes and WS | Web roles |
| --- | --- | --- | --- |
| `link-chat-runs` | [`ac-link-chat-runs`](../../packages/py/links/ac-link-chat-runs/README.md) | — | `conversations:runs` |
| `link-definitions-resources` | [`ac-link-definitions-resources`](../../packages/py/links/ac-link-definitions-resources/README.md) | — | — |
| `link-definitions-teams` | [`ac-link-definitions-teams`](../../packages/py/links/ac-link-definitions-teams/README.md) | Usages, effective settings, run plan, bundle preview | `definitions:teams` |
| `link-exports-teams` | [`ac-link-exports-teams`](../../packages/py/links/ac-link-exports-teams/README.md) | — | — |
| `link-logs-architecture` | [`ac-link-logs-architecture`](../../packages/py/links/ac-link-logs-architecture/README.md) | `GET /logs/architecture`, `GET /logs/events/{uid}/architecture` | `logs:architecture` |
| `link-logs-runs` | [`ac-link-logs-runs`](../../packages/py/links/ac-link-logs-runs/README.md) | `GET /runs/{id}/logs` | `logs:runs` |
| `link-logs-trace` | [`ac-link-logs-trace`](../../packages/py/links/ac-link-logs-trace/README.md) | `GET /logs/sessions/{session}/trace` | `logs:trace` |
| `link-logs-usage` | [`ac-link-logs-usage`](../../packages/py/links/ac-link-logs-usage/README.md) | — | — |
| `link-memory-runs` | [`ac-link-memory-runs`](../../packages/py/links/ac-link-memory-runs/README.md) | — | `memory:runs` |
| `link-projects-memory` | [`ac-link-projects-memory`](../../packages/py/links/ac-link-projects-memory/README.md) | — | — |
| `link-projects-records` | [`ac-link-projects-records`](../../packages/py/links/ac-link-projects-records/README.md) | — | — |
| `link-projects-runs` | [`ac-link-projects-runs`](../../packages/py/links/ac-link-projects-runs/README.md) | — | — |
| `link-projects-sdd` | [`ac-link-projects-sdd`](../../packages/py/links/ac-link-projects-sdd/README.md) | — | — |
| `link-projects-wiki` | [`ac-link-projects-wiki`](../../packages/py/links/ac-link-projects-wiki/README.md) | — | — |
| `link-runs-sdd` | [`ac-link-runs-sdd`](../../packages/py/links/ac-link-runs-sdd/README.md) | — | — |
| `link-runs-teams` | [`ac-link-runs-teams`](../../packages/py/links/ac-link-runs-teams/README.md) | `POST /graphs/{id}/validate` | `runs:team-rules` |
| `link-runs-trace` | [`ac-link-runs-trace`](../../packages/py/links/ac-link-runs-trace/README.md) | `/runs/{id}/trace`, `/runs/handoffs` | `runs:trace` |
| `link-runs-usage` | [`ac-link-runs-usage`](../../packages/py/links/ac-link-runs-usage/README.md) | — | `usage:tokens` |
| `link-wiki-runs` | [`ac-link-wiki-runs`](../../packages/py/links/ac-link-wiki-runs/README.md) | — | `wiki:runs` |

- Subscribing to an unknown WS topic gives `error{reason: unknown_topic}`.
- Turning off one module at a time: `tests/test_agent_console_server_module_matrix.py` (every installed module ×
  startup, status, the remaining API, 404).
- When `link-chat-runs` is off (or `mod-runs` is missing), listing and creating conversations and the queue still work;
  only sending a message returns 409 `feature_unavailable{module: mod-chat, port: chat.turn_launcher}`. Without the
  definitions module, creating a conversation returns 409 (`port: definitions.lookup`). When `mod-chat` is off, the
  conversation routes return 404 and `link-chat-runs` is `unsatisfied`.
- `GET /server-info` is a host route. It collects warnings from `server.warnings` (plain-text secret scan,
  `team.rules_unavailable`, in-memory storage warnings, and so on) and attributes from `server.attributes`
  (`recovered_runs`).
- When `mod-definitions` is off, the definition ports are missing, so `mod-imports`, `mod-exports`, `mod-versions`,
  `mod-resources`, `mod-runs`, and the `link-*` modules that need them are `unsatisfied`; `mod-usage` works with external
  sources only (token totals `[]`). `mod-chat` stays on and shows only the conversation list.
- When `mod-runs` is off, the run routes and descriptors return 404, `link-runs-*` and `link-chat-runs` are
  `unsatisfied`, and definition CRUD and the conversation list work as before.
- When `mod-projects` is off, `/projects…` returns 404 and `link-projects-*` are `unsatisfied` (runs still record and
  filter by `project_id`; only the project layer, that is the project folder and project settings, is gone). When
  `mod-logs` is off, `/logs…` returns 404 and `link-logs-*` are `unsatisfied`.
- When `mod-i18n` is off, `/i18n…` returns 404, the web uses only its own message catalogs, and server text stays as the
  original.
- Turning off a link: `link-definitions-resources` → definitions are saved without resource checks;
  `link-definitions-teams` → its routes return 404, and the entry names and usage counts in lists are null;
  `link-exports-teams` → exports contain only the chosen items, without automatic dependencies; `link-runs-teams` →
  runs use engine validation only (`team.rules_unavailable` warning; there are also no node services, so agent nodes
  report `agent.lookup_unavailable`), the validate route returns 404, and the validation summary in lists is null;
  `link-runs-trace` → the flow and handoff routes return 404; `link-runs-usage` → token totals are `[]`;
  `link-logs-runs` → logs contain no platform runs and `/runs/{id}/logs` returns 404; `link-logs-trace` → the session
  flow route returns 404; `link-logs-usage` → there is no `local-logs` usage source. The other link modules describe
  what turns off in their own README.
- The plugin registries (nodes, edges, backends, resource kinds, usage sources, import sources, export formats, …) are
  loaded **once** by the host in `create_app` (`agent_console_modkit.load_host_plugins`; each module package provides
  its loaders through an entry point) and passed to every module as the base service `registries`.

- Host routes (always present, whatever modules are on): `GET /health`, `GET /bootstrap`, `GET /modules`
  (`ModuleInfo[]`, no token needed), `GET /server-info`, `/ws` multiplexing, the security middleware, and static
  serving (optional).
- Turning modules on and off: the administrator setting `modules{enabled, disabled, bindings, options}` and the
  command-line options `--enable-module ID` and `--disable-module ID` (`apply_module_flags`; they take precedence over
  the settings, and when both name the same id, turning off wins). Routes of a module that is off are not registered
  (404).
- Status: `active | disabled | unsatisfied | failed | conflict` (`module_info` turns the modkit `ModuleReport` into the
  contract `ModuleInfo`). `ModuleInfo.requires` = required + optional ports.
- When an optional port is missing inside a module that is on, the module raises `raise ctx.unavailable(PORT)` (modkit
  `FeatureUnavailableError`) for the affected operation, and the server turns it into 409 `feature_unavailable` with
  `details = FeatureUnavailableDetails{module, port}`.
- A failing start hook fails server startup (`Assembly.start(fail_fast=True)`; modules that already started are stopped
  in reverse order).
- Feature exceptions → contract errors: modules use their own `error_map` (modkit `ErrorReply`, including `details` and
  headers). The app-level `register_error_handlers` holds the common handlers (store errors, engine errors, and so on);
  for the same exception type, the app-level handler wins (the contract body is the same). Conversation errors
  (`ChatError`) are handled only by the error map of `mod-chat`.

## Assembly order and shutdown

Creating the app (`create_app`): registries (nodes, edges, backends, delegation strategies, interaction kinds =
`load_registries`, secret providers, resource kind plugins + `<workspace>/resource-types/*.yaml`, usage sources, import
sources, export formats, `plugins.modules`) → module assembly (build). The load report is `plugins` in
`GET /server-info`.

Startup (lifespan, module start hooks in assembly order): `mod-definitions` (legacy lineage, plain-text secret scan) →
… → `mod-runs`: **cleanup of runs the previous process left unfinished** (`recover_unfinished_runs`: the run becomes
`interrupted` and pending interactions become `expired(interrupted)`; this is the first thing the module does) →
backend administrator settings (`from_options`) → `mod-chat` (conversation and queue store = the host database handle,
run connection `ChatService.connect`) → `link-chat-runs` (chat queue restart policy `chat.queue_after_restart`). Other
feature modules: `mod-versions` (applies the retention count to everything), `mod-usage` background work (pruning
observations).

Shutdown (reverse order): `link-chat-runs` stops taking items from the queue and waits **first** for
`runs.starter.shutdown()` (runs still running are recorded as interrupted; the time limit is
`modules.options.mod-runs.runtime.shutdown_timeout`, after which the remaining runs are force-canceled and the cleanup
records are awaited), then `mod-chat` cleans up its chat watchers. The `mod-runs` stop hook only waits for the same
cleanup again (it runs once). The host closes the database handle last.

Starting a run (`POST /runs`, shared with chat turns = `RunService.start_run` of `mod-runs`): engine graph validation
→ pre-run preparers (`runs.preparers`: when `ac-teams.team_rules_apply` is set, `link-runs-teams` runs
`validate_team`; duplicate meanings are removed with `merge_validation`) → refusal if there is a blocking issue
(`blocks_run`) → preparer `prepare` (`prepare_run`: grants and interaction settings) →
`GraphRuntime.start(conversation_id=, services=node services (+ SESSIONS for a chat turn), interaction_grants=, interaction_settings=)`.
Without preparers (`link-runs-teams` off), runs use engine validation only and `GET /server-info` shows the
`team.rules_unavailable` warning.
Node services (`runs.services`, `link-runs-teams`): `AGENT_LOOKUP`, `WORKSPACE_SETTINGS`, `WORKING_DIRECTORY`,
`RESOURCE_LOOKUP` (port `resources.lookup`), `RUN_FILES_ROOT = <workspace>/.state/runs`, `DEFAULT_BACKEND`.
`plugins.modules` is loaded after the plugin loaders into the same bundle (`load_host_plugins`) and goes through each
registry's validator and `plugins.enabled` and `plugins.disabled` (keys that are off are `disabled`). The reports of
left-out items carry a reason (`LoadReport.reason`), and names in `plugins.disabled` that appear in no report show up as
a `plugins.unknown_disabled` warning (or `plugins.disabled_distribution` and similar codes with `details`) in
`GET /server-info` `warnings`.

## REST (`/api/v1`)

| Area | Routes |
| --- | --- |
| Readiness | `GET /api/v1/health` → `HealthResponse{status:"ok", server_version, contracts_version}` (no token needed, no secrets. 200 means the server is ready to take requests) |
| Modules | `GET /modules` → `ModuleInfo[]` (in id order, no token needed, no secrets) |
| Bootstrap and info (host) | `GET /bootstrap`, `GET /server-info` (warnings = the modules' `server.warnings`; attributes = binding and source + the modules' `server.attributes`, such as `recovered_runs`) |
| Descriptors (`mod-runs`; resource kinds and merge strategies from `mod-resources`) | `GET /node-types`, `POST /node-types/{id}/ports`, `GET /edge-types`, `GET /backends`, `GET /backends/{id}/models`, `GET /delegation-strategies`, `GET /interaction-kinds`, `GET /resource-types`, `GET /merge-strategies` |
| Agents | `GET/POST /agents`, `GET/PUT/DELETE /agents/{id}`, `GET /agents/{id}/usages`, `GET /agents/{id}/effective-settings`, `GET /agents/{id}/activity?limit=` (RunEvent[], newest first) |
| Teams | `GET /graphs?validate=` (each summary has `validation{blocks_run, error_count, warning_count, codes}`, cached per workspace revision; null when `validate=false`), `POST /graphs`, `GET/PUT/DELETE /graphs/{id}`, `POST /graphs/{id}/duplicate {id,name}` (201 VersionedGraph, 409), `POST /graphs/{id}/validate` (`link-runs-teams`), `GET /graphs/{id}/plan` (TeamPlanSummary), `GET /graphs/{id}/nodes/{node}/effective-settings`, `GET /graphs/{id}/nodes/{node}/bundle-preview` (BundlePreview{bundle, warnings}) |
| Team drafts (not saved) | `POST /graphs/plan {graph}` (TeamPlanSummary), `POST /graphs/effective-settings {graph, node_id}` (EffectiveSettings), `POST /graphs/bundle-preview {graph, node_id}` (BundlePreview). Secrets are masked the same way as for the saved routes |
| Runs (`mod-runs`; flow and handoffs from `link-runs-trace`) | `POST /runs`, `GET /runs?graph_id=&conversation_id=&agent_id=&status=&limit=`, `GET /runs/handoffs` (same filters), `GET /runs/{id}`, `POST /runs/{id}/cancel`, `GET /runs/{id}/events?actor=&type_prefix=&since_seq=`, `GET /runs/{id}/trace`, `GET /runs/{id}/resume-options`, `POST /runs/{id}/resume` |
| Interactions (`mod-runs`) | `GET /interactions?status=&conversation_id=&limit=` (newest first), `GET /runs/{id}/interactions`, `POST /runs/{run}/interactions/{id}/respond {response}` (200, 404, 409 `interaction_closed`, 422) |
| Chat | `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}`, `GET /conversations/{id}/turns?before=<run_id>&limit=`, `POST /conversations/{id}/messages` (202 Run or `{queued: true, id, position, text}`, 409 `conversation_busy`), `GET /conversations/{id}/queue`, `DELETE /conversations/{id}/queue/{queued_id}` (204) |
| Resources | `GET /resources?type=`, `POST /resources`, `GET/PUT/DELETE /resources/{id}` (ETag; PUT requires If-Match), `GET /resources/{id}/usages`, `GET/PUT /resources/{id}/content` (text content + ETag, If-Match; on 412 the current ETag) |
| Resource files | `GET /resources/{id}/files` (ResourceFile[] in path order), `GET /resources/{id}/files/{path}` (content + ETag; `text/plain` for text formats, otherwise `application/octet-stream`), `PUT …/files/{path}` (body = bytes) and `DELETE …/files/{path}`: If-Match = the resource `version_hash` (missing 428, different 412), response = the definition as stored + the new ETag. Writes work only when the kind descriptor has `content.multi_file` (otherwise 422 `resource.not_multi_file`). A path rule violation is 400; going over the total limit (`modules.options.mod-definitions.max_content_bytes`) is 413 |
| Import (`mod-imports`) | `GET /resources/import/sources`, `POST /resources/import/preview {source}` (candidates + `warnings`, such as `import.skipped_link` for links that were skipped), `POST /resources/import {source, items}`: the source is only read |
| Export (`mod-exports`) | `GET /exporters` (ExporterDescriptor[]), `POST /exports/plan` (ExportRequest → ExportPlan, no writes; with `root` and `subdir`, create, skip, and conflict are computed for that folder), `POST /exports/archive` (zip response `application/zip` + `Content-Disposition`, nothing is written to disk), `GET /exports/roots` (**token required**, ExportRootInfo[]; empty means folder writes are off; when `modules.options.mod-exports.expose_paths=false` (defaults to the `security.expose_paths` value when omitted), path is an empty string), `POST /exports/write` (ExportWriteRequest → ExportResult, `on_conflict` defaults to fail → 409 `already_exists` with `details.paths`). Unknown format, root, or definition: 404; wrong kind, options, or path: 422 (`details.issues`, path relative to the request: `/items/0/kind`, `/options/…`, `/subdir`); when the format reports an error-level warning, archive and write return 422 |
| Usage (`mod-usage`) | `GET /usage?parts=windows,tokens` (omitted = all; parts that were not requested are null; with `windows` only, run history is not read), `GET /usage/sources` |
| Settings | `GET/PUT /settings` |
| Versions (all kinds, `mod-versions`) | `{collection}` = `/agents/{id}`, `/graphs/{id}`, `/resources/{id}`, `/settings` (the table is the settings data `modules.options.mod-versions.collections`): `GET {collection}/versions`, `GET …/versions/{hash}` (content = as stored), `GET …/versions/{a}/diff[/{b}]` (DefinitionDiff; b omitted = current; secret positions have `secret:true` and the value `***`; content shows only sha256 in `content_changes`), `GET …/versions/{hash}/files[/{path}]` (404 when there is no content snapshot; `text/plain` for text, otherwise `application/octet-stream`), `POST …/versions/{hash}/restore {message?}` (saves a new version; If-Match is required when the definition exists, 428/412; a deleted definition is restored without it; the same pre-save checks apply → 422; response DefinitionVersion + ETag; default message `restored from <hash>`) |
| Message catalogs (`mod-i18n`) | `GET /i18n` (`I18nInfo`: languages with `sources`, `complete`, `missing`, plus `default_language`, `fallback_language` and `source_language`), `GET /i18n/{lang}` (`MessageCatalog`; `en-US` matches `en`; `ETag` + `Cache-Control: no-cache`, `If-None-Match` → 304; 404 `i18n.unknown_language`) |
| Projects, logs, memory, specs, wiki, architecture map | `/projects…` (`mod-projects`), `/logs…` (`mod-logs`), `/memory/…` (`mod-memory`), `/sdd/…` (`mod-sdd`), `/wiki/…` (`mod-wiki`), `/architecture/…` (`mod-architecture`). The full route lists are in each module README (see the module tables above) |

- Fixed paths (`/runs/handoffs`, link modules) match before `{id}` paths (feature modules): the host attaches the link
  module routers first (`agent_console_modkit.host.include_routers`). `/resources/import/*` (a module router) does not
  overlap the resource `{id}` paths in method and depth.
- Every 4xx is `ErrorResponse{error{code, message, details}}`. 422 has `details.issues`. 412 has the current version in
  the `ETag` header.
- **Definition responses are the stored document as written** (GET, POST, and PUT of agents, teams, resources, and
  settings, the agent list, and `VersionedGraph.graph`). Omitted keys are also absent from the response; explicit null,
  empty lists, and values equal to the default stay as they are ("omitted = inherited"). Values with defaults and
  sources filled in come from `.../effective-settings`. `GET /settings` returns `{}` when there is no file (no ETag).
  PUT of a GET result does not grow the file. `response_model` is kept only for the OpenAPI document.
- **Resource pre-save check**: `POST /resources` and `PUT /resources/{id}` are refused with 422 `validation_failed`
  when the kind check (`agent_console_resources.validate_resource`) has an error issue (for example
  `resource.plain_secret`: a plain value in MCP `env` or `headers`). `details.issues[].path` is a JSON Pointer relative
  to the resource document (`/config/env/API_KEY`), and the message contains no value. Unknown kinds are not blocked.
  This check is the `DefinitionChecker` that `link-definitions-resources` provides through the port
  `definitions.checks`.
- **Attachment override check**: when agents (`POST/PUT /agents`), teams (`POST/PUT /graphs`: team layer, node layer,
  resource links), and common settings (`PUT /settings`: `agent_defaults`) are saved, the `config_override` of each
  resource attachment is shallow-merged onto the resource config and checked against the kind
  (`ac-teams.attachment_issues`). An error is 422 `validation_failed`, with the path relative to the attachment
  (`/resources/0/config_override/env/API_KEY`). When the `ref` resource does not exist, the schema is unknown, so the
  suspected-secret rules (`ac-secret-rules`, the same rules as ac-imports + the settings `secrets.extra_*`) apply: a match
  is 422 `resource.override_secret_suspected`, otherwise it is saved with a warning only
  (one `DefinitionChecker` from `link-definitions-resources` serves both REST and version restore).
- **Masking for display**: `GET .../effective-settings` (agents and nodes) and `GET .../bundle-preview` replace values
  that are not `secret://` at the `x-secret` positions of the resource kind config schema with `***` (a safety net for
  data saved before the checks).
- **Secret rules**: assembled by `mod-definitions` (`WorkspaceState`, `SecretRuleCheck`, `PlainSecretScan`; the logic
  is in `ac-secret-rules`).
  - The common settings `secrets.extra_key_names` and `extra_value_patterns` only **add** to the default rules. Patterns
    go through the `ac-safe-regex` check: a dangerous or invalid regular expression makes `PUT /settings` return 422
    (`secret.invalid_rule`, path `/secrets/extra_value_patterns/<i>`).
  - `secrets.redact_suspected_in_logs` (default true): the runtime `SecretResolver(extra_redact=)` replaces suspected
    values with `[REDACTED]` just before run history (events, Run, NodeRun) and interactions are saved. With false, the
    original is kept (for debugging). The setting takes effect when a run starts.
  - Plain-text scan: at startup and in `GET /server-info` (cached), resources, agents, teams, and settings are scanned,
    and `secret.plain_found` (warning, `details{kind, id}`, path relative to the definition document, no value) is
    added to `warnings`. It combines the plain-text issues of the save checks (`resource.plain_secret`,
    `resource.override_secret_suspected`) with a whole-document suspicion check. The cache is dropped when a definition
    is saved as a new version (topic `definitions.saved`, including writes from every module) and when one is deleted.
    Raw GETs are not masked.
  - For declarative resource kinds, plain text at schema positions with `x-secret: true` is refused by the general rule
    (`resource.plain_secret`).
- `mod-chat` stores the chat queue in the server database (table `chat_queue`). After a server restart,
  `link-chat-runs` handles it according to the workspace setting `chat.queue_after_restart`. Without a database the
  queue is kept in memory and the `chat.storage_memory` warning is raised.

## WebSocket `/ws?token=`

Topics: `run:<id>` (`mod-runs`; replay from `since_seq`, then live), `conversation:<id>` (`mod-chat`; the current summary
right after subscribing, then `conversation.updated`), `interactions` (`mod-runs`; right after subscribing, the pending
list one by one as `interaction.updated`, then each change), and the module topics listed in the module tables (`logs`,
`memory.changed`, `sdd.changed`, `wiki.changed`). The modules that are on decide the topics (an unknown topic gives
`error{reason: unknown_topic}`). An unknown message type gives `error{code: bad_request}`.

## Public API

| Name | Description |
| --- | --- |
| `load_settings(config_path=None, *, environ=None, cwd=None, overrides=None, compat=None) -> ServerSettings` | Precedence: overrides (command line) > environment variables > settings file > defaults. `compat` = the module settings compatibility declarations (None means the installed modules). Raises `ConfigError` (values are not put in the message) |
| `settings_compat(modules=None)`, `SETTINGS_COMPAT_CONTEXT` | The modules' `SettingsCompat` declarations (`ServerSettings.model_validate(..., context={SETTINGS_COMPAT_CONTEXT: …})`) |
| `flag_overrides(values, compat=None)` | Values of command-line options declared by modules (`{"echo-tag": [...]}`) → settings overrides. `ConfigError` when no module declares the option |
| `create_app(settings=None, *, environ=None, token=None, modules=None) -> FastAPI` | `environ` = the environment that secret providers, backends, and modules (such as HOME for imports) read (default `os.environ`). `modules` = the modules to assemble (None means the installed entry points). `app.state.assembly` = the assembly result |
| `installed_modules(group=MODULES_GROUP) -> list[Module]` | Server modules installed through entry points (read failures are logged as warnings) |
| `apply_module_flags(settings, *, enable=(), disable=()) -> ServerSettings` | A copy with `--enable-module` and `--disable-module` applied |
| `module_info(report) -> ModuleInfo` | modkit report → contract model |
| `serve(settings=None, *, environ=None, token=None, opener=None, modules=None)` | Runs uvicorn. The token is never logged. When ready, it logs the ready line, and when `web.open.enabled` is set it calls `opener(url)` (or `build_opener(web.open)` when none is given) |
| `build_opener(web_open, *, browser=None, spawn=None) -> Opener` | Runs the `web.open.command` command when set (without a shell, `{url}` replaced), otherwise opens the default browser (`webbrowser.open`). The browser and subprocess are injected |
| `RemovedKey`, `SETTINGS_REMOVED_KEY`, `ConfigError.code`, `ConfigError.removed` | When a removed old key is still present, `load_settings` raises `ConfigError(code="settings.removed_key", removed=[RemovedKey{old, new, message}])`. The message gives the reason and the new location. Removed keys come only from module declarations (`SettingsCompat.removed`) |
| `build_openapi(app)` | The OpenAPI document (components = the contract JSON Schema `$defs`) |
| `server_version() -> str` | The server version = the version in the installed metadata of `agent-console-server` (`pyproject.toml` `project.version`; `0.0.0` without metadata). The `server_version` of `/health`, `/bootstrap`, and `/server-info` and the OpenAPI `info.version` are this value. The contract version (`contracts_version`) is separate |
| `QueryRedactingFilter`, `install_log_redaction` | Masks secret-like query values in logs |
| `SecurityPolicy`, `TOKEN_HEADER`, `TOKEN_QUERY`, `WS_CLOSE_UNAUTHORIZED` (4401), `WS_CLOSE_FORBIDDEN` (4403), `API_PREFIX`, `WS_PATH` | Security and path constants (the security middleware, token, `/health`, WS multiplexing, and log masking come from `agent-console-modkit[host]`) |

## Settings file `agent-console.yaml`

Lookup order: `--config` / `load_settings(path)` → `AGENT_CONSOLE_CONFIG` → `agent-console.yaml` in the current folder.
Relative paths are relative to the settings file folder (or the current folder when there is no settings file).

```yaml
host: 127.0.0.1               # a non-loopback address requires security.allow_remote: true
port: 8765
workspace: .agent-console      # definition YAML folder (declarative resource kinds in <workspace>/resource-types)
database: null                 # default <workspace>/.state/console.sqlite3
log_level: info
plugins:
  enabled: null                # entry point names (shared by all groups). null = everything installed
  disabled: []                 # names to leave out (all groups, wins over enabled). Unknown names become a server-info warning
  modules: []                  # plugins that are not installed, as `pkg.mod:attr` (register(registries))
security:
  token: null                  # empty = random at each start
  allow_remote: false
  allowed_hosts: []            # extra Host values (loopback + the bound port are always allowed)
  allowed_origins: []          # origins allowed for CORS and bootstrap (for example http://localhost:5173, the web dev server)
  expose_paths: true           # false removes the absolute workspace path from GET /server-info (also the default for export root paths)
  max_request_bytes: 1048576
  max_ws_message_bytes: 1048576
  max_ws_subscriptions: 256
secrets: {env_prefix: "", min_redact_chars: 4, providers: {}}   # secret resolution (host base service). min_redact_chars is also the mod-runs default. providers = secret provider name → its options (no secret values)
web:
  serve_static: false          # optional. When on, serves the web build folder as an SPA (single process)
  static_dir: null             # web build folder (for example apps/web/dist). Empty = the build bundled in the package
  open:
    enabled: false             # open the web screen when ready (serve --open/--no-open overrides it)
    url: null                  # address to open ({host} and {port} are replaced). Empty = the server address when serve_static is on
    command: null              # command to run instead of the browser (for example [msedge, "--app={url}"])
    wait_seconds: 30           # maximum seconds to wait for the readiness signal
modules:                       # server modules on and off (read-only in the web; serve --enable-module/--disable-module wins)
  enabled: null                # null = every installed module. A list = only those
  disabled: []                 # turned off after enabled (for example [mod-usage])
  bindings: {}                 # the chosen module when several modules provide the same port {port: module id}
  options:                     # module id → that module's settings (validated by each module's settings_schema; keys in each module README)
    mod-usage:
      retention_seconds: 2592000   # how long usage observations are kept (seconds). null = never deleted
      prune_interval_seconds: 3600
      rollup_run_limit: 500        # number of recent runs used for the GET /usage token totals
      source_timeout_seconds: 10
    mod-imports:
      project_dir: null        # where the project `.claude/` and `.mcp.json` are. Empty = the settings file folder (does not follow the run folder)
      options: {}              # source factory name → options (for example claude: {mapping: {...}})
    mod-exports:
      roots: []                # roots allowed for folder writes [{id, label, path}]. Empty = archive (zip) only
      home: null               # home folder for protected_in_home. Empty = HOME or USERPROFILE
      protected_in_home: [.claude] # folders under home that are never written (even when registered as a root)
      protected: []            # other folders that are never written
      options: {}              # format name → factory options (for example claude-dir: {mapping: {...}, layout: {...}})
      expose_paths: true       # whether GET /exports/roots shows absolute paths
    mod-versions:
      max_per_definition: null # versions kept per definition (null = all). Applied on save and at startup
    mod-definitions:
      max_content_bytes: 10485760  # total content file size of one definition (such as a resource) in bytes (null = no limit). Over it: 413
    mod-runs:
      working_directory: null  # run folder of agents (WORKING_DIRECTORY service). Default base_dir
      run_files_dir: runs      # run bundle file folder (relative to the state folder)
      runtime: {max_concurrency: null, cancel_grace: 2.0, event_queue_size: 10000, shutdown_timeout: 10.0}
      show_hidden_backends: false  # shows backends for development and tests (descriptor ui_hints.hidden, such as fake-agent). Environment variable AGENT_CONSOLE_SHOW_HIDDEN_BACKENDS
      backends:                # backend id → values passed to that backend's from_options hook (keys in each backend README)
        claude-agent-sdk: {models: [], allow_command_hooks: false, allow_subscription_auth: true}  # subscription by default (at your own responsibility)
        fake-agent: {models: [], echo_hooks: false}
      backend_login: {enabled: true, timeout_s: 300}  # backend sign-in from the app screen (see "Backend sign-in" below)
      model_discovery: {enabled: true, ttl_s: 3600, failure_ttl_s: 60, timeout_s: 20, disabled_backends: []}  # fills the model field with the models the backend account can use (no model call)
    mod-i18n:
      default_language: en     # language when neither the screen setting nor the browser language decides it
      fallback_language: en    # language for text the chosen language lacks
      source_language: ko      # language the server source text is written in (null = unknown)
      catalog_dirs: []         # folders with <language>.json catalogs (relative to the settings file folder, applied after package catalogs)
      disabled_catalogs: []    # package catalog ids to leave out
```

**Removed keys**: module settings live only under `modules.options.<module id>`. Top-level keys such as `usage`,
`imports`, `exports`, `versions`, `resources`, `runtime`, `backends`, and `working_directory` are not read. When one is
still present, the server does not start and reports a settings error that gives the new location
(`settings.removed_key`, for example
`usage: The settings key usage is no longer read. Move it to modules.options.mod-usage`).
Settings errors, help text, and startup messages in the terminal are in English. Text in API responses is not
translated by the server; the web shows it in the chosen language through the message catalogs (`mod-i18n`).
Each module declares its removed keys with `SettingsCompat.removed` (`RemovedSetting(old, new=...)`); the server has
no table of its own.
Passing another setting's value as a default happens only in the host settings (no warning, and only when the new
location has no value): `security.expose_paths: false` → `mod-exports.expose_paths`, `secrets.min_redact_chars` →
`mod-runs.min_redact_chars`.
Modules do not pass defaults to each other: when omitted, `mod-imports.project_dir` is the host `paths.base_dir` (the
settings file folder) and does not follow `mod-runs.working_directory`. When omitted, `mod-exports.home` is HOME or
USERPROFILE.
`modules.options.mod-imports.home` (importing the user-wide `~/.claude`) is a removed key. Even with a null value, if
the key is present the server does not start and reports a settings error with the reason (`settings.removed_key`).
The only import source is the `.claude/` folder of the project folder.
The environment variables `WORKING_DIRECTORY` and `MAX_CONCURRENCY` go to their new location
(`modules.options.mod-runs.*`).

When settings of the deleted presets feature (top-level `presets`, `modules.options.mod-presets`) are still present,
the server does not start and reports the settings error "The presets feature was removed" (`settings.removed_key`,
declared by `mod-definitions`). Any other unknown key (such as the old `console`) is a general settings error (the host
settings use `extra="forbid"`).
`console` and `default_entry` left in the workspace `settings.yaml` are user data, so they are kept as unknown keys
(no error).

Environment variables (prefix `AGENT_CONSOLE_`, empty values are ignored): `CONFIG`, `HOST`, `PORT`, `WORKSPACE`,
`DATABASE`, `WORKING_DIRECTORY`, `LOG_LEVEL`, `TOKEN`, `WEB_DIR`, `MAX_CONCURRENCY`, `SECRET_ENV_PREFIX`; booleans
(1/true/yes/on) `ALLOW_REMOTE`, `SERVE_STATIC`, `OPEN`; comma-separated lists `PLUGINS_ENABLED`, `PLUGINS_DISABLED`,
`PLUGIN_MODULES`, `ALLOWED_HOSTS`, `ALLOWED_ORIGINS`. (`WORKING_DIRECTORY` and `MAX_CONCURRENCY` go into
`modules.options.<id>` of the module that declares them, through the module's `settings_compat` declaration.)

## Single process: one server for API, WS, and web

When the server also serves the web build, everything has the same origin, so `allowed_origins` and CORS settings are
not needed. This is off by default, and while it is off the server works without knowing about the web.

```bash
pnpm --filter @agent-console/web build                     # creates apps/web/dist (each time you pull new code)
AGENT_CONSOLE_SERVE_STATIC=1 AGENT_CONSOLE_WEB_DIR=apps/web/dist \
  uv run agent-console serve --open                        # opens http://localhost:8765/
```

To keep the same in the settings file: `web: {serve_static: true, static_dir: apps/web/dist, open: {enabled: true}}`.

Static folder path base: **relative paths in `web.static_dir` and `AGENT_CONSOLE_WEB_DIR` are relative to the folder of
the settings file** (or to the current folder where `serve` was started when there is no settings file). A value given
through the environment variable uses the same base, so a settings file outside the repository
(`--config ~/console/agent-console.yaml`) together with `AGENT_CONSOLE_WEB_DIR=apps/web/dist` looks for
`~/console/apps/web/dist`. If the location is unclear, use an **absolute path**.
When the folder does not exist, the build bundled in the package is used, and when that is missing too, a guide page
is shown.
To open in an installed PWA window or another browser, use `web.open.command` (for example `[msedge, "--app={url}"]`);
to open a separate web server address, use `web.open.url`.

- Readiness signal: scripts, shortcuts, and desktop shells wait until `GET /api/v1/health` returns 200. The server log
  also gets a `Ready: <URL>` line (with the actual port when the port is 0).
- Opening happens once, after the server is ready. When there is no address to open (static serving off + no `url`) or
  opening fails, only a warning is logged and the server keeps running.
- Static serving does not take over `/api/…` and `/ws` (unknown API paths return a JSON 404). Without a build, a guide
  page is shown.

## Backend sign-in (`mod-runs`)

You sign in to and out of execution backends from the app screen (on by default). The default backend
`claude-agent-sdk` starts `claude auth login` as a PTY subprocess and relays the sign-in address and code entry to the
screen. Claude Code CLI writes the credentials to its own location, and **the server never receives or stores
tokens.** The code you enter does not appear in responses, logs, or errors. For backends without sign-in support, the
routes return 409.

- Routes: `POST /backends/{id}/login` (201 session), `GET /backends/login/current`, `GET /backends/login/{sid}`
  (polling = heartbeat), `POST /backends/login/{sid}/input`, `DELETE /backends/login/{sid}` (cancel),
  `POST /backends/{id}/logout`. Status checks are `GET /backends/status` and `GET /backends/{id}/status`; the
  connection test is `POST /backends/{id}/probe`.
- Settings `modules.options.mod-runs.backend_login`: `enabled` (default true; off removes the routes), `timeout_s` and
  `timeout_max_s` (300 and 900), `heartbeat_s` (30), `retain_s` (60), `screen_max_lines` (40). The command arguments
  and screen text rules are in the backend administrator settings (`backends.claude-agent-sdk.login`; the keys are in
  the `ac-backend-claude-sdk` README, "Subscription sign-in").

## Security

- The default bind address is 127.0.0.1. Other addresses only with `security.allow_remote: true`.
- Host: loopback names + the bound port, or `allowed_hosts` (blocks DNS rebinding) → otherwise 403 `forbidden`. The
  same applies to preflight requests.
- CORS: `Access-Control-Allow-Origin` (+ `Expose-Headers: ETag`) only for origins **listed** in `allowed_origins`.
  Allowed headers: `X-Console-Token`, `If-Match`, `Content-Type`. A preflight from an origin outside the list is 403.
- Origin: change requests and `GET /bootstrap` accept only the same origin or `allowed_origins`. For `/bootstrap`,
  `Sec-Fetch-Site: cross-site` is accepted only for a listed origin.
- Token: POST/PUT/PATCH/DELETE (including interaction responses) require `X-Console-Token` → otherwise 401. WS uses
  `?token=`.
- Body size: over `max_request_bytes` → 413.
- Import: `~/.claude` and the project `.claude/` are only read. Plain secrets of MCP servers are not stored; they are
  replaced with `secret://` references.
- Export: the default is a zip response (nothing is written to the server disk). Folder writes go only under roots
  registered in `modules.options.mod-exports.roots`; path escapes, links, and protected locations (such as
  `~/.claude`, even when registered as a root) are refused. The output gets a final check with `ac-secret-rules`, and
  values that look like plain secrets are masked.
- Secrets: the token is never logged. 500 responses do not contain internal messages. Bundle previews and plugin error
  text are masked with `SecretResolver.redact`. There is no API that runs shell commands.

## Tests

```bash
uv run pytest apps/server/tests
```

Shared helpers are in the public submodule `agent_console_server.testing` (temporary settings
`make_settings(tmp_path, options={module id: settings}, **host keys)`, app client, test graphs, WS helpers). This
module uses `fastapi.testclient`, so **it imports only when `httpx` is installed**. `httpx` is not a runtime
dependency of the server but a development dependency (dev group), so to use it outside the repository install both,
as in `pip install agent-console-server httpx` (otherwise `ModuleNotFoundError: httpx`).
Checks that read the generated TS contracts or the example settings at the repository root are in the repository
`tests/integration/`.
The interaction integration tests use real SQLite + the engine + the fake backend to cover waiting → response →
completion, concurrent responses, restart cleanup, and shutdown order.

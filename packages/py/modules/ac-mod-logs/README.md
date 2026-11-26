# agent-console-mod-logs

Logs feature module (`mod-logs`). It collects and indexes logs through log source and classifier plugins (in the background and on demand),
and serves queries and notifications through the `/logs…` REST routes and the WS topic `logs`.

- **It does not know feature names or source names.** Sources and classifiers come from the host registry bundle (`log_sources`, `log_classifiers`),
  and that bundle is filled from entry points by this package's host plugin loader (entry point `agent_console.host_plugin_loaders` = `logs`).
  Without the bundle (standalone run), it reads the entry points directly.
- **It turns on by itself.** There are no required ports. When an optional port is missing, only that part is off.
  - No `workspace.settings` → default settings (the source descriptors' `default_enabled`, the default classification scheme)
  - No `secrets.rules` → the index is not masked, with the warning `logs.redaction_unavailable`
  - No `logs.sources` → plugin sources only
- **Originals are only read.** Collection is done by `LogIngestor` of `agent-console-logs`, which opens files read-only.
- The server app (`apps/server`) does not know this module's name. When installed, it comes in through its entry point.

## Ports, topics, and routes

| Kind | Name | Shape |
| --- | --- | --- |
| Provides | `logs.query` | `LogQueryPort` (list, list rows (`iter_event_rows`, JSON rows without models), detail, sessions, timeline, totals, handoffs, token samples, classification scheme, query context) |
| Provides | `logs.ingest` | `LogIngestPort` (`add_runtime_source`, `request_scan(source_ids, ref_hint=)`, `scan`) |
| Provides | `server.warnings` | `logs.storage_memory`, `logs.redaction_unavailable`, `logs.source_failed`, `logs.unknown_classifier` |
| Optional (multi) | `logs.sources` | `RuntimeLogSource` (attributes `source` and `classifier`; for example `testing.RuntimeSource`) |
| Optional | `workspace.settings` | `() -> WorkspaceSettings` (`logs.*`, `secrets.redact_suspected_in_logs`) |
| Optional | `secrets.rules` | `() -> SecretRules` (`redact_value`) |
| Optional (multi) | `logs.source_defaults` | `() -> {source id: bool}`: the default for sources without `enabled` in the settings (for example, `link-logs-usage` turns it on when this computer has Claude Code logs). An `enabled` written by the user wins, and the settings file is not changed (`apply_source_defaults`). Without it, the descriptor's `default_enabled` |
| Optional | `projects.folders` | Project folders registered in the app (`registered`, `archived`, `project_for`). The scope is all registered projects as one, and sources that understand scope (`claude-code-jsonl`) read only the records of these folders (including subfolders). Unregistered projects are not read again, but their index entries stay. The session `project_id`, the filter `project`, and the totals dimension `project` are `project_for(cwd)` (registration id). The old grouping setting `logs.projects` is not read; info `settings.ignored_key`. Without the port, there are treated as being no registered projects, those sources read nothing, and the warning `logs.no_projects` asks you to add or register a project first. When records outside the scope are skipped in the `roots` setting, `logs.out_of_scope`. To use it in a standalone run, `--with mod-projects`; in tests, `testing.project_folders_module`. Sources also receive the host path `workspace` (the app workspace) in the context `paths` (the app run session root `workspace_roots` of `claude-code-jsonl`) |
| Optional (multi) | `logs.scope_kinds` | `LogScopeKind` (`id`, `resolve(value) -> LogScope{sessions, run_ids}`): the filter `scope=<id>:<value>`. Without it, `scope` returns 422 |
| Optional (multi) | `logs.filter_predicates` | `LogFilterExtension` (`fields`, `build(values, context) -> predicate`): the names appear in the filters of `GET /logs/schema`, and the list, sessions, timeline, totals, handoffs, and archive follow them. Without it, those names return 422. When names collide, only the first one is used (with a warning log) |
| Topic | `logs.ingested` | `LogsIngestedPayload{source_ids, count, max_seq}` |
| WS | `logs` | `logs.ingested` messages |
| Web role | `logs` | The logs screen |
| Lineage | `logs` | `storage.BRANCH` (version table `alembic_version_logs`) |

Routes (under `/api/v1`; 404 when the module is off):
`GET /logs/sources`, `GET /logs/classifiers`, `POST /logs/scan` (202, body `{source_ids?}`),
`GET /logs/events?<LogFilter>`, `GET /logs/events/{uid}`, `GET /logs/sessions?<LogFilter>`,
`GET /logs/sessions/{session}/timeline?<LogFilter>`, `POST /logs/aggregate`, `GET /logs/handoffs?<LogFilter>`,
`GET /logs/taxonomy`, `GET /logs/dashboard-templates`, `GET /logs/schema`,
`GET /logs/archive?<LogFilter>&format=json|html&tz=<IANA>` (attachment), and
`POST /logs/index/purge` (empty the index, below).
The base filters include `thread` (several values), `scope` (`<kind>:<value>`), and `max_seq` (up to this seq).
Unknown filters, dimensions, metrics, time zones, and scope kinds return 422 `validation_failed` (`details.path`, `details.issues[].code = logs.invalid_query`).
The project filter `project=~ungrouped` means logs that are in no registered project folder. The project of a session summary fills only `project_id` (registration id; the name comes from `GET /projects`).

### Emptying the index: `POST /logs/index/purge`

Body `LogPurgeRequest{sources?, categories?, before?, rescan=true, dry_run=true, all=false}` (a model inside the module; unknown keys and empty lists return 422),
response `LogPurgeResponse{dry_run, events, usage, cursors, agents}` (rows deleted, or rows that would be deleted with dry_run). Both models are outside the contract, so
OpenAPI carries them only as inline schemas (`routes.PURGE_BODY_SCHEMA`, `PURGE_RESPONSE_SCHEMA`). The semantics are those of
`agent_console_logs.purge_index`. **dry_run is the default**, so nothing is deleted unless you pass `"dry_run": false`. Without a body, the whole index is
counted. With `rescan`, the cursors of the sources in range are deleted too, so the next collection (`POST /logs/scan` or the background collection) indexes again with the current
classification rules. It runs inside the collection lock after any running collection finishes, and it does not touch the original files. To actually delete without a range (source, category, time)
(`"dry_run": false`), the confirmation `"all": true` is required (without it, nothing is deleted and the request returns 422 with `details.path =
"all"`, the same safeguard as the CLI `--all`). When the index does not support purging, 400 `logs.purge_unsupported`. In the service, use
`LogsService.purge(...)` (async). To change the index file without a server, use `agent-console logs purge` (apps/cli).

```bash
# Delete the Claude Code request bodies of an old index (api-request-blob, category meta) and collect again
curl -X POST .../api/v1/logs/index/purge -d '{"sources":["claude-code-jsonl"],"categories":["meta"]}'   # count
curl -X POST .../api/v1/logs/index/purge -d '{"sources":["claude-code-jsonl"],"categories":["meta"],"dry_run":false}'
curl -X POST .../api/v1/logs/scan -d '{"source_ids":["claude-code-jsonl"]}'
```

## Administrator options (`modules.options.mod-logs`)

| Key | Default | Meaning |
| --- | --- | --- |
| `scan_interval_seconds` | 30 | Background collection interval in seconds. 0 means no repeated collection |
| `startup_scan` | true | Collect once right after startup (separately from the interval) |
| `scan_budget_bytes` | 8,000,000 | Maximum bytes read from one source in one collection |
| `batch_size` | 500 | Number of events per transaction |
| `retention_days` | null | Delete index events older than this (the originals stay). null = forever |
| `index_path` | null | Index into a separate SQLite file (the module applies the same lineage itself). null = the host database |
| `max_detail_bytes` | 80,000 | Upper limit for detail and raw in detail responses |
| `timeline_limit` | 5000 | Number of events in one timeline response |
| `dashboard_templates_dir` | null | Dashboard template folder. null = the package default (`data/dashboard_templates`) |
| `archive_max_events` | 5000 | Maximum number of events in an archive (only the first part when exceeded, `truncated`) |
| `archive_max_bytes` | 20,000,000 | Upper limit on the total JSON bytes of archive events |
| `archive_file_prefix` | `agent-console-logs` | Start of the archive file name (`<prefix>-<UTC time>.json\|html`) |
| `archive_title` | `Agent Console 로그 보관본` | HTML title of the archive |
| `session_title_rules` | null | Session title ranking rules `[{tag, pick: first\|last}]` (from the top; the first rule with a candidate). null = the `agent-console-logs` default data, `[]` = no title |
| `base_taxonomy_file` | null | Base classification scheme YAML file. null = the `agent-console-logs` default data (`default_taxonomy.yaml`); a path = that file (when missing, a warning and an empty scheme); `false` or an empty string = no base scheme (only the workspace setting `logs.taxonomy` is applied) |

An archive (`/logs/archive`) contains the events in the filter range (bodies up to `max_detail_bytes`), sessions, lines, evidence links, and the effective classification scheme
(`limit` and `cursor` are not used). `format=json` (default) is `LogArchive` v1, and `format=html` is HTML without scripts
(`agent_console_logs.render_archive`; times use `tz` or the server's local time); both are sent as attachments. When there are masking rules,
the export masks once more with the current rules (in case the rules changed after collection). Unknown `format`, `tz`, and filter names return 422.

Relative paths are relative to the host `base_dir` (the settings file folder). Dashboard templates are default data. One file is
one `LogDashboard`, every widget has `options.w` and `h`, and the query filters have no time range. It still works when the folder is emptied or deleted.

## Install

```bash
pip install agent-console-mod-logs
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-logs
```

| Dependency | What | Why | Alternative |
| --- | --- | --- | --- |
| `agent-console-logs` | `LogIngestor`, `SqliteLogIndex`, `MemoryLogIndex`, queries, default plugins | Collection, indexing, and queries live in the library | — |
| `agent-console-modkit[host]` | Module interface, host, standalone run | The common kit of all server modules | — |
| `agent-console-store` | Lineage runner (`upgrade`), definition file store (`settings.yaml` in a standalone run) | The same approach as the host | Calling alembic directly |
| `fastapi` | Router | The same web framework as the host | — |
| `ruamel-yaml` | Reading dashboard templates (YAML data) | The workspace YAML standard | PyYAML |
| `sqlalchemy` | Engine | The same type as the host `DatabaseHandle.engine` | — |

## Minimal usage

Use only the service, without a server: collect v1 jsonl files in a temporary folder into an in-memory index and query them.

```python
>>> import asyncio, json, tempfile, time
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogRegistries
>>> from agent_console_logs.testing import MemoryLogIndex
>>> from agent_console_mod_logs import LogsService

>>> folder = Path(tempfile.mkdtemp())
>>> rows = [{"schema_version": 1, "category": "input", "title": "안녕", "session": "S"},
...         {"schema_version": 1, "category": "llm", "title": "답", "session": "S"}]
>>> _ = (folder / "a.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}]}
... )
>>> registries = LogRegistries()
>>> _ = registries.load()
>>> service = LogsService(MemoryLogIndex(), registries, settings=lambda: settings, clock=time.time)
>>> asyncio.run(service.scan()).new_events
2
>>> [(s.session, s.events) for s in service.sessions(LogFilter())]
[('S', 2)]

```

Assembled as a module, it gets the REST routes (the settings come through the `workspace.settings` port).

```python
>>> from fastapi.testclient import TestClient
>>> from agent_console_contracts import WorkspaceSettings
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app
>>> from agent_console_mod_logs import module
>>> from agent_console_mod_logs.testing import static_settings_module
>>> workspace = WorkspaceSettings.model_validate({"logs": settings.model_dump(exclude_unset=True)})
>>> assembly = assemble(
...     [module, static_settings_module(workspace)],
...     ModulesConfig(options={"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}}),
... )
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> with TestClient(create_host_app(assembly, policy=policy)) as client:
...     client.headers["X-Console-Token"] = "t" * 32
...     print(client.post("/api/v1/logs/scan").json()["new_events"])
...     print([e["title"] for e in client.get("/api/v1/logs/events").json()["items"]])
2
['안녕', '답']

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Standalone run

```bash
python -m agent_console_mod_logs [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_settings_module` (the `settings.yaml` of the workspace folder). Turn on the sources to read
in `logs.sources` of that file. The index is `console.sqlite3` in the state folder (lineage `logs`). To mask suspected secrets as well,
add `--with mod-definitions` (when installed).

## Storage layer

- **Lineage `logs`**: package data `storage/migrations/versions/logs_0001_index.py` (tables) and `logs_0002_scope_indexes.py` (`thread`, `run_id`, `session` + `seq` indexes), version table `alembic_version_logs`.
  It is applied only when the module is on, and rollback (`downgrade`) works only per lineage.
  It is not added to `ac-store.MODULE_OWNED_TABLES`, which is a list only for the legacy migration.
- **Index location**: the host database by default. With `index_path`, the same lineage is applied directly to that SQLite file and used.
  Without a database, `MemoryLogIndex` (`LogStorage.kind == "memory"`, warning `logs.storage_memory`).
- The index implementation and queries are in `agent_console_logs.sqlite` of `agent-console-logs`.

```python
from agent_console_mod_logs import open_log_storage

# applies the lineage to a separate file and opens it
storage = open_log_storage(None, index_path="logs.sqlite3")
open_log_storage(None).kind  # "memory" when there is neither a database nor a path
```

## Public API

| Name | Description |
| --- | --- |
| `module` / `LogsModule` / `MODULE_ID` / `WEB_ROLES` | Server module (entry point `agent_console.server_modules`) |
| `base_taxonomy_of` | Option `base_taxonomy_file` → base classification scheme (the value passed to `LogsService(base_taxonomy=)`) |
| `LogsService` | Collection schedule (`scan`, `request_scan`, `run_periodic`, `start`, `stop`) + queries (`parse_filter`, `extensions`, `events`, `iter_event_rows`, `event`, `sessions`, `timeline`, `aggregate`, `handoffs`, `token_samples`, `taxonomy`, `schema`, `dashboard_templates`, `sources`, `classifiers`) |
| `LogsModuleSettings` | Administrator options |
| `LogRedaction` | Masks suspected secrets right before storage (with the port value) |
| `LOGS_QUERY`, `LOGS_INGEST`, `SERVER_WARNINGS`, `LOG_SOURCES`, `LOG_SCOPE_KINDS`, `LOG_FILTER_PREDICATES`, `WORKSPACE_SETTINGS`, `SECRET_RULES`, `LOGS_INGESTED`, `LOGS_TOPIC` | Ports, topics, WS topic |
| `LogQueryPort`, `LogIngestPort`, `RuntimeLogSource` | Port protocols (structural types) |
| `load_dashboard_templates`, `parse_dashboard` | Reading dashboard templates |
| `plugins.load_plugins`, `plugins.bundle_registries` | Host plugin loader |
| `standalone.main` | Standalone entry point |
| `storage.BRANCH`, `open_log_storage`, `LogStorage` | Lineage, opening the index |
| `testing.local_settings_module`, `static_settings_module`, `runtime_sources_module`, `RuntimeSource`, `query_extensions_module` (imitates registration) | Modules for standalone runs and tests |

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

## Removed keys in source settings

When a key that the source settings schema marks with `deprecated: true` (for example the old `project_roots` of `claude-code-jsonl`) is still in the settings,
it is not read, and the info issue `logs.ignored_key` (`details.source`, `details.key`, `server.warnings`) is raised. The key names come from the source schema
data, and this module does not know any source-specific keys. Server startup is not blocked.

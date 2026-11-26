# agent-console-mod-memory

Shared memory feature module (`mod-memory`). It plugs the feature library
`agent-console-memory` (store, scope kinds, cleanup rules, export and import) into the server. People view, edit, and delete entries
through REST and the web screen, and the runs link (`link-memory-runs`) builds agent tools through the port `memory.service`.
It does not know about runs or logs (memory works without runs).

| What | Details |
| --- | --- |
| REST | `GET /memory/scope-kinds`, `GET /memory/scopes?kind=`, `GET /memory/tags?scope=&include_archived=`, `GET·POST /memory/entries`, `GET·PUT·DELETE /memory/entries/{id}` (`PUT` requires `If-Match`; `DELETE ?purge=true` deletes permanently, 204), `POST /memory/entries/{id}/move·archive·unarchive·restore?version=`, `GET /memory/entries/{id}/versions[/{v}]`, `POST /memory/retention/plan·apply`, `POST /memory/settings/check`, `GET /memory/export?scope=` (zip), `POST /memory/import?policy=skip\|overwrite\|rename&dry_run=` (body = zip), and `POST /memory/copy` (copy between spaces, `MemoryCopyRequest` → `MemoryCopyResult`). Every route except the settings check chooses the space with `?project=<id>` (the library when omitted) |
| WS | Topic `memory.changed` (message `memory.changed`, no content: scope, key, id, version, action, author kind, and space `space` (null = library)) |
| Errors | `not_found` (404), `already_exists` (409, `details.entry_id`), `version_conflict` (412, `details.current_version`), `version_required` (428), `feature_unavailable` (409, no space provider), `project.not_found` (404), and the provider exception `code` (for example `project.folder_missing`, or `project.memory_unavailable` when the project memory database cannot be opened; when the exception has a `reason`, `details.reason`), `memory.invalid_key`, `memory.too_large`, and `memory.secret_rejected` (422, without values or content fragments), `validation_failed` (422, a wrong query or not a zip) |
| Provided ports | `memory.service` (shape `MemoryServicePort`: `store`, `catalog()`, `settings()`, `limits`, `toolkit(access, context, ...)`), `server.warnings` (`memory.storage_memory`, `memory.search_fallback`, `memory.settings_invalid`) |
| Optional ports | `workspace.settings` (the user settings section `memory`; defaults without it), `memory.spaces` (space name → `{store, context}`, provided by `link-projects-memory`; without it, only the library. When it has the optional method `existing() -> list[str]`, the automatic cleanup covers those spaces too) |
| Storage | Lineage `memory` (`memory_0001`, version table `alembic_version_memory`, scopes `app` and `memory`; the link that opens project memory databases finds it by the scope `memory` and applies it). By default the host database file; with the option `store_path`, that file (the same lineage is applied); without a database, process memory + a warning |
| Administrator options | `modules.options.mod-memory.{store_path, retention_interval_seconds, full_text_search, busy_timeout_seconds, max_entry_bytes, max_entries_per_scope, max_total_bytes, max_key_chars, max_tags, max_tag_chars, preview_chars, max_page_size, max_tag_list, max_search_results, query_hash, query_hash_salt_env, max_import_archive_bytes, max_import_files, max_import_file_bytes, max_import_total_bytes}` |
| User settings | The workspace settings `memory` (contract `MemorySettings`: `include_default_scope_kinds`, `scope_kinds`, `secrets`, `max_versions_per_entry`, `retention.rules`, `retention.auto{library, projects, exclude_projects}`). Broken parts are left out, the rest is used, and the problems are reported as warnings |
| Plugins | Entry point `agent_console.memory_scope_kinds`. The host plugin loader (`memory` of `agent_console.host_plugin_loaders`) reads them into the `memory_scope_kinds` extension of the host bundle |
| Web role | `memory` (the memory screen, the sidebar item, and the data of the *Memory* settings section require this role) |

- Scope kinds, tags, and key names are all data. An empty workspace has only the package's default scope kinds and no entries.
- The package default for cleanup rules is an empty list (nothing is deleted or archived automatically). The automatic cleanup applies only the saved rules
  every `retention_interval_seconds` (default 3600; 0 = off).
- The targets of the automatic cleanup are chosen with the user setting `memory.retention.auto`. When omitted, it is
  `{library: true, projects: true, exclude_projects: []}` (both the shared library and projects). One cycle goes through the shared library, then the
  spaces returned by `existing()` of the `memory.spaces` provider (`link-projects-memory` returns only enabled registrations whose memory file already
  exists; it does not create new files). A failure in a space is only logged and skipped. The author of the resulting
  versions is `system` (`label` = rule id).
  - How to turn it off: everything = the administrator option `modules.options.mod-memory.retention_interval_seconds: 0`.
    Only the shared library = `memory.retention.auto.library: false`; all projects =
    `memory.retention.auto.projects: false`; only some = `memory.retention.auto.exclude_projects:
    [<registration id>, ...]`. When `link-projects-memory` is off, only the shared library is cleaned.
  - Without HTTP: `run_retention_cycle(service)` → `RetentionCycleResult{results, failed}`.
- Memory content can be read by other agents as if it were instructions (it is not a security boundary). Narrow write permissions with the access settings of the
  `memory` resource, and let people correct entries on the screen.
- When the module is off, the routes above return 404 and the lineage is not applied (when the other database modules are off too, no database file is created).

## Dependencies: what, why, alternatives

- In-house: `agent-console-memory` (store, search, cleanup, export), `agent-console-conditions` (cleanup
  rule operators), `agent-console-modkit` (module, host), `agent-console-registry` (registries),
  `agent-console-store` (lineage runner, host database, reading `settings.yaml` in a standalone run).
- External: FastAPI and pydantic (common to server modules), SQLAlchemy and Alembic (lineage `memory`). No new external dependencies.

## Install

```bash
pip install agent-console-mod-memory
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-memory
```

## Minimal usage: the service without a server

```python
>>> from agent_console_contracts.memory import MemoryScopeRef, MemoryWriteRequest
>>> from agent_console_memory import InMemoryMemoryStore, MemoryQuery
>>> from agent_console_mod_memory import MemoryService

>>> changes = []
>>> section = {"include_default_scope_kinds": False,
...            "scope_kinds": {"notes": {"label": "노트", "id": "{/project_id}"}}}
>>> service = MemoryService(
...     InMemoryMemoryStore(), section=lambda: section, on_change=changes.append
... )
>>> [k.kind for k in service.scope_kinds().kinds]
['notes']
>>> entry = service.create(MemoryWriteRequest(
...     scope=MemoryScopeRef(kind="notes", id="p1"), key="결정/api", content="v2 사용"))
>>> (entry.version, entry.created_by.kind, [c.op for c in changes])
(1, 'user', ['create'])
>>> [i.key for i in service.entries(MemoryQuery(text="v2")).items]
['결정/api']

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Viewing memory in logs and the architecture map (example data)

The run events `memory.<op>` left by the runs link (`link-memory-runs`) are mapped by the platform run log map
(`memory.*` in `run_event_map.yaml` of `ac-link-logs-runs`) to the category `memory`, the document marker
`{kind: memory, path: <scope kind>/<scope id>/<key>, action: read|written|removed|searched}`, and the evidence
`tool_use_id` and `memory_scope` (scope kind). Calls with an unknown scope (no permission and so on) have no document marker.
Deleting is `removed` (`deleted` is a file change word and would also match the Workspace cell of the default architecture map).

The default architecture map profile has no Memory cell. To see one, add a profile to the workspace settings. Below is an example
that duplicates the default profile (`profile` of `GET /architecture/profiles/agent-architecture`) and adds only a cell, an edge, and coverage
(`...` is the rest of the duplicated content). This data is not kept in the repository; users add it themselves.

```yaml
architecture:
  profiles:
    with-memory:
      title: Agent architecture + memory
      # ... duplicate canvas, zones, error_when, source_priority, cells, edges, and coverage of the default profile as they are ...
      cells:
        # ... default cells ...
        memory:
          label: Memory
          description: Shared memory reads and writes
          x: 810
          y: 730
          zone: runtime
          tone: gold
          metrics: [count, errors]
          group_by: /correlation/memory_scope      # group by scope kind
          when: {all: [{path: /category, op: eq, value: memory}]}
      edges:
        # ... default edges ...
        - id: memory_access
          from: dispatch
          to: memory
          label: Memory access
          kind: observed
          style: request
          points: [[1054, 610], [1030, 610], [1030, 730], [906, 730]]
          label_at: [968, 730]
          metrics: [count, errors]
          when: {all: [{path: /category, op: eq, value: memory}]}
      coverage:
        # ... claude-code-jsonl stays as it is ...
        platform-runs:
          cells: [sdk, api, rules, context, llm, dispatch, hook, tools, mcp, result, delegation,
                  subagents, response, memory]
```

- Category names are data too. When you rewrite the whole `memory.*` rule in the log setting `logs.sources[id=platform-runs].config.event_map`
  and change it to `category: notes`, change the `value` of the condition above to `notes` as well.
- To turn the rule off, write `"memory.*": {}` in the same place. Memory events become the category `other` (title = type name), and
  the Memory cell shows 0. Other logs are unchanged.
- Cell count = the number of memory events of that run = the number of rows in the event table when you click the cell (the repository integration test
  `test_integration_memory_cell_57r16.py` checks this with the same data).

## Standalone run

```bash
python -m agent_console_mod_memory --config standalone.json --port 0
```

Without `--with`, a small settings module (`local-settings`) that reads the workspace `settings.yaml` is attached.
Write user settings in the `memory` section of that file. Entries are kept in `console.sqlite3` in the state folder (lineage `memory`).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

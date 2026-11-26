# agent-console-mod-usage

Agent Console usage feature module. It plugs the usage library `agent-console-usage` into the server.

- Routes: `GET /usage` (`?parts=windows,tokens`; omitted = everything; parts not requested are null) and `GET /usage/sources`.
- `parts=windows` only collects from the sources. It does not read run history (token totals), which keeps it cheap for shell status indicators.
- Provided ports: `usage.service`, `server.warnings` (runtime source id collisions `usage.source_conflict`, and saved source settings that do not
  match that source's `config_schema` `usage.source_config_invalid`, severity warning, `path` = the location in the settings document),
  and `definitions.checks` (multi, `UsageSettingsCheck`). No required ports (it turns on by itself).
- Pre-save check (`definitions.checks`): when the common settings (kind `settings`) are saved, `usage.sources[i].config` is checked against
  the `config_schema` of the sources available now (plugins + runtime). When it is wrong, an error issue makes the saving side (`mod-definitions`
  `PUT /settings`, `mod-versions` revert) reject the request with 422 `validation_failed`
  (`details.issues[].path`, for example `/usage/sources/0/config/budgets/local_five_hour`). Values and the schema text are not
  included. Sources that do not exist at save time (link off, not installed) cannot be validated and pass; when such a source appears,
  the problem shows up in `server.warnings` and in the `error` of `GET /usage/sources`.
- Optional ports (when missing, only that part is off): `usage.event_query` (run event queries), `usage.token_rollups` (token totals;
  without it, `rollups = []`), `workspace.settings` (turning sources on and their settings), and `usage.sources` (multi, runtime usage
  sources `UsageSource`, for example `local-logs` of `link-logs-usage`).
- Runtime sources: source id = descriptor `id`. The port list is read again on every request (link modules are built after
  this module). When an id collides with a plugin (registry) source, the plugin wins; when runtime sources collide with each other, the module that
  connected first (module id order) wins. A dropped id shows up as `server.warnings` `usage.source_conflict` (`details.source`).
  Turning them on and their settings work like plugin sources (`usage.sources[{id, enabled, config}]`).
- Automatic enabling: sources not listed in `usage.sources` are on when their descriptor is `auto_enable` and not `test_only`
  (`agent_console_usage.auto_enabled`). With empty settings, `run-events`, `statusline-file`, and `local-logs` are on, and `fake` is off.
- Setup snippets: `descriptor.setup_snippets` of `GET /usage/sources` are sent with the placeholders filled in. `{output_path}` =
  the absolute path of the file that source reads (the source's `setup_values`); `{agent_console_cmd}` = the absolute path of the option `agent_console_command` (default
  `agent-console`) found in the injected `PATH` and in the folder of the Python that runs the server (`resolve_command`; when it cannot be found, the name as it is). `last_received_at` is in the same response.
- Storage: this module owns the observations `usage_observations` (`agent_console_mod_usage.storage`). They are built on the engine of the host database handle
  (`BaseServices.database`, for example `agent_console_store.SqliteDatabase`), and the migration lineage
  `usage` (package data `storage/migrations/versions`) is applied only when the module is on. The table is exactly the one legacy 0002
  created (no changes). Without a database handle, only recording and cleanup are off. **Legacy is never downgraded**: to roll back, roll back only the `usage` lineage
  (`SqliteDatabase.downgrade_branch`). When legacy is downgraded to 0002 or below, `usage_observations` disappears, but the version table
  `alembic_version_usage` remains, so the table is not created again on the next start.
- Settings `modules.options.mod-usage` (the old top-level `usage` points to the new location with a `settings.removed_key` error): `retention_seconds`,
  `prune_interval_seconds`, `rollup_run_limit`, `source_timeout_seconds`, and `agent_console_command`.
- Web role: `usage`.

## Install

```bash
pip install agent-console-mod-usage
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-usage
```

## Minimal usage

`parts` is a comma-separated list, and unknown names are ignored.

```python
>>> from agent_console_mod_usage import parse_parts
>>> sorted(parse_parts(["windows,future"]))
['windows']
>>> sorted(parse_parts(None))
['tokens', 'windows']

```

When the module is assembled, the report service comes through the `usage.service` port. Without the token totals port, `rollups` is an empty list.

```python
>>> import asyncio
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_usage import USAGE_SERVICE, module
>>> service = assemble([module]).port(USAGE_SERVICE)
>>> report = asyncio.run(service.report(["tokens"]))
>>> report.windows is None, report.rollups
(True, [])

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

Standalone run (the same modkit host, 127.0.0.1 by default). Observations accumulate in `console.sqlite3` in the state folder:

```bash
python -m agent_console_mod_usage [--config PATH] [--port 0] [--check]
```

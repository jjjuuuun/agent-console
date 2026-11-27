# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-logs`, so the web app can show the module description, log settings,
  default dashboard template titles and the `logs.ignored_key`, `logs.out_of_scope` and `logs.purge_unsupported`
  issues in English (data only, no API change).
- The notice about the old `logs.projects` is found with the contract helper
  `ignored_settings_keys(settings, section="logs")` instead of attribute access (`LogSettings.projects`). Even after
  the field is removed in contract 0.15.0, there is no issue when the key is absent, and info `settings.ignored_key`
  when it is present (same as now). Session summaries fill only `project_id` (the old `project` is null).
- Fixed: moved waiting for collection to `agent_console_modkit.WorkGate` (`DEFAULT_STOP_WAIT` =
  `DEFAULT_WORK_WAIT`). When `run_periodic` is canceled (server shutdown), it blocks new collections, waits for thread
  collection in progress and then re-raises the cancellation. The assembler does this before the stop hooks, so it
  finishes before the record space pool closes.
- Fixed: `LogsService.stop()` waits for thread collection and purging in progress to finish (limit `stop_wait`,
  default `DEFAULT_STOP_WAIT` 30 seconds, with a warning beyond that). After stopping, new collections return an empty
  report without calling sources, and `start()` opens them again. The collection thread finishes before the module stop
  hook closes the index.
- The value shape of `projects.folders` is `ProjectFoldersLike` = `registered`, `archived_folders` and `project_for`
  (the old `current` is removed). The query context has `project_for` (cached per query), which feeds the session
  `project_id`, the filter `project=<registration id>`, the aggregation dimension `project` and `token_samples`
  (log-based usage). The old `logs.projects` is not read and gives info `settings.ignored_key`
  (`details.key = logs.projects`). `testing.project_folders_module(registered, archived)` (id to a folder or list) and
  `StaticProjectFolders`.
- `POST /logs/index/purge` body `all`: actually purging without a scope requires `all: true` (422 without it). Indexes
  that do not support purging give 400 `logs.purge_unsupported` (`LogPurgeUnsupportedError`).
- Server administrator option `base_taxonomy_file` (replaces the default classification; `false` or an empty string
  turns it off) and `base_taxonomy_of`. The module passes it to `LogsService(base_taxonomy=)`.
- Optional multi port `logs.source_defaults` (defaults for sources without `enabled` in the settings; the settings file
  is not changed), `apply_source_defaults` and `collect_source_defaults`.

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Storage layer (`storage`: lineage `logs`, `open_log_storage`).
- Registered the module descriptor (provides `logs.query`, `logs.ingest` and `server.warnings`; optional
  `logs.sources`, `workspace.settings` and `secrets.rules`; web_roles `logs`; lineage `logs`) and the entry points
  (`agent_console.server_modules` `mod-logs`, `agent_console.host_plugin_loaders` `logs`). `LogsService` (background
  and manual collection, collection scheduling, retention cleanup, queries), 12 REST routes under `/logs…`, WS `logs`
  and the topic `logs.ingested`, injected masking of suspected secrets, source failure warnings, dashboard templates
  (two in package data), server administrator options (`LogsModuleSettings`), and standalone runs (`standalone.main`,
  `local-settings` without `--with`).
- `GET /logs/archive?<LogFilter>&format=json|html&tz=` (an attachment with `Content-Disposition`),
  `LogsService.archive`, and the server administrator options `archive_max_events`, `archive_max_bytes`,
  `archive_file_prefix` and `archive_title`.
- Server administrator option `session_title_rules` (null = the ac-logs default data).
- `POST /logs/index/purge` (body `LogPurgeRequest`, response `LogPurgeResponse`; models inside the module, dry_run
  true by default) and `LogsService.purge` (`purge_index` inside the collection lock).

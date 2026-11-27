# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-definitions`, so the web app can show the module description, definition
  store settings and the `definitions.versions_memory` and `secret.invalid_rule` issues in English (data only, no API
  change).
- `PRESETS_REMOVED_REASON` is in English (`The presets feature was removed. Delete this key from the settings file`);
  the host prints it to the terminal when it refuses to start.
- `server.warnings` also reports the old top-level `default_backend` of the common settings (not read since 1.1.0) as
  info `settings.ignored_key`, with `details = {key: "default_backend", replacement: "agent_defaults.backend"}` and
  the message `RENAMED_SETTINGS_MESSAGE`. New location table `RENAMED_SETTINGS_KEYS` (old key to new location; it also
  finds keys that are not yet in the contract `IGNORED_SETTINGS_KEYS`, and overlaps are reported once) and the
  optional arguments `ignored_settings_issues(..., renamed=, renamed_message=)`. Server start, reads and saves are not
  blocked, and the key is not removed from the file.
- `server.warnings` reports old top-level keys of the common settings (`settings.yaml`), meaning the contract
  `IGNORED_SETTINGS_KEYS` without dots (currently `projects`), as info `settings.ignored_key` (`details.key`, message
  `IGNORED_SETTINGS_MESSAGE`). Reads, saves and server start are not blocked. Keys below a section (`logs.projects`)
  are reported by `mod-logs`, which reads that section. `ignored_settings_issues(settings, *, message=)` is public.
- Pre-save checks in a space (`?project=`) call the optional check method `space_issues(space, kind, document)`
  (`SpaceDefinitionCheck`). Checks without it use `issues` as now.
- Team lists in a space (`?project=`) also fill the `validation` summary. The optional method
  `space_summaries(space, graph_ids, lookup=)` (`SpaceGraphValidationSource`) of the `graphs.validation` provider is
  called; without it, null as now (the library `summaries` is not called). Optional argument
  `DefinitionService(space=)`.
- Optional port `graphs.session_summary` (contract 0.13.2; `GraphSessionSummarySource.session_summary(graph)`,
  `GRAPH_SESSION_SUMMARY`). When present, it fills `session_summary` of `GET /graphs` rows (both library and space
  lists). Null when absent or when the provider raises. Optional argument `DefinitionService(session_summary=)`.
- Contract 0.13.1: `build_rules` passes the setting `secrets.weak_key_names` (null = the default data
  `DEFAULT_WEAK_KEY_NAMES`, an empty list = off, otherwise that list) to `SecretRules(weak_key_names=...)`. The
  pre-save check blocks invalid names with `secret.invalid_rule` (`/secrets/weak_key_names/<i>`), and invalid names in
  hand-edited files are dropped with a warning log (location only). Added `weak_name_problems`.
- Optional port `definitions.kind_contributions` (`KIND_CONTRIBUTIONS` = the kit `DEFINITION_KIND_CONTRIBUTIONS`).
  Contributed kinds with `library=True` are added to the library store (at build time and once more in the startup
  hook, `register_contributed_kinds` and `DefinitionFileStore.contributed`). Library requests for `library=False`
  kinds are unknown kinds and give 404. Contributions with the same name as a default kind are skipped with a warning
  log. Without contributions, the kind list is the same as before.
- Optional port `definitions.spaces` (space name to definition store, `ac-store.DefinitionSpaces`). Agent and team
  routes take `?project=<space>` (list, read, create, save, delete, duplicate). Without the port, `?project=` requests
  give 409 `feature_unavailable`, an unknown space gives 404 `project.not_found`, and requests without the query use
  the library as before. Plain-text secret rejections on space writes give 422 with `details.issues` (field
  locations), and folders that cannot be written give 409 `project.config_readonly`. `validation` in space lists is
  null. Added `SavedDefinition.space` (default None). **Breaking change**: the `service` of `build_router(service)`
  takes a space name (`Callable[[str | None], DefinitionService]`).
- Removed the presets feature. The leftover settings keys `presets` and `modules.options.mod-presets` are declared as
  `RemovedSetting`, so the host refuses to start with a "The presets feature was removed" error
  (`PRESETS_REMOVED_REASON`). Dropped the development dependency `agent-console-mod-presets`.
- Moved `LazyVersionRepository` and `versions_for` to `ac-store` (this module's `store` re-exports them, same
  behavior).
- Removed read compatibility for the old top-level `resources` (a `settings.removed_key` error points to the new
  location).

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Moved the definition store assembly, agent, team and common settings CRUD, secret rules and plain-text checks out of
  `apps/server`. Provided ports `definitions.store`, `definitions.lookup`, `workspace.settings`, `secrets.rules`,
  `definitions.checks` (secret rule checks for common settings) and `server.warnings` (plain-text checks), and the
  topic `definitions.saved`. The plain-text check cache is dropped on `definitions.saved` and deletes (replacing the
  write request middleware), and generation comparison and assignment happen inside a short state lock. Version
  history uses the host database handle (legacy), or memory without it. Settings `max_content_bytes` (formerly
  `resources.*`) and `plain_secret_issue_codes`.
- When version history falls back to memory because there is no database handle, a `definitions.versions_memory`
  warning is added to `server.warnings`.

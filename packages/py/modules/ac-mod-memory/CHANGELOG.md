# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-memory`, so the web app can show the module description and settings and
  the `memory.invalid_request` issue in English (data only, no API change). Log lines are now in English.
- Contract 0.15.0 (memory 1.3.0): fills `MemoryChanged.space` of WS `memory.changed` (a space service sends its own
  space name, the registration id; the library sends null). When a space provider exception has a string `reason`, it
  is put in the error response `details.reason` (for example `project.memory_unavailable`).
  `MemorySpaceError(reason=)`.
- `search_query_hasher` uses the shared `query_hasher_from_env` (same behavior).
- Server administrator options `query_hash` (`hmac` by default, `sha256` or `off`) and `query_hash_salt_env` (the name
  of the salt environment variable) for `query_sha256` in agent search events. The default changed from unsalted
  sha256 to HMAC with a random salt per process. `search_query_hasher(cfg, environ)`.
- Fixed: when automatic cleanup overlaps with server shutdown, it ends without waiting or processing the remaining
  stores. `run_retention_cycle(should_stop=)` and `RetentionCycleResult.stopped`,
  `run_retention_periodically(gate=, stop_wait=)` (when canceled, it closes the `WorkGate`, waits for the store in
  progress to finish and then re-raises the cancellation; the assembler does this before the stop hooks, so it
  finishes before the space pool and stores close), and the stop hook also waits for the cleanup thread before closing
  the store.
- After the shared library, automatic cleanup on the server also processes the spaces returned by the optional method
  `existing()` of the `memory.spaces` provider (targets = the user setting `memory.retention.auto`; failures per space
  are logged and skipped; nothing is opened when there are no rules). `run_retention_cycle`,
  `RetentionCycleResult` and `retention_targets`, `MemorySpaceServices.existing()` and
  `MemoryService.existing_spaces()`, and the port shape `MemorySpacesListing`. Settings parsing: `retention.auto` is
  validated field by field (invalid fields give `memory.settings_invalid` and the default; rules are kept).

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Shared memory server module. REST `/memory/*` (scope kinds, scopes, tags, entry CRUD, versions, cleanup, settings
  checks, export and import), the WS topic `memory.changed`, the user settings section `memory` (read except for the
  broken parts), the lineage `memory` (`memory_0001`), the storage location (host database file, `store_path`, or
  memory with a warning), the cleanup schedule, the port `memory.service`, the host plugin loader for memory scope
  kinds, server administrator limit options, and standalone runs.
- Optional port `memory.spaces` (space name to store plus context switching), REST `?project=<id>` (entries, scopes,
  tags, versions, cleanup, export and import, scope kinds; 409 `feature_unavailable` without a provider, 404
  `project.not_found` for an unknown space, provider exception `code` passed through), and `POST /memory/copy`
  (`MemoryCopyRequest` to `MemoryCopyResult`, 400 for the same space). `MemoryService.space(name)`, `copy`,
  `context_overrides` and `effective_context`, `MemorySpaceServices`, and the errors `MemorySpaceError`,
  `MemorySpacesUnavailable` and `UnknownMemorySpace`. Added `memory` (`MEMORY_DB_SCOPE`) to the scopes of the lineage
  `memory` so the link module that opens project memory databases can find it. `build_router(service)` is unchanged
  (spaces come from the service's `space`).

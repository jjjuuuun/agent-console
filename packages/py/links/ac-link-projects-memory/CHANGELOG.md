# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-projects-memory`, so the web app can show the link module description and settings in English (data only,
  no API change). Log lines are now in English.
- Contract 0.15.0: the error code of `MemoryDbUnavailable` changed from `feature_unavailable` to the new contract code
  `project.memory_unavailable` (409). The exception has a `reason` (`REASON_NO_MIGRATIONS`, `REASON_MIGRATE_FAILED`,
  `REASON_SHUTTING_DOWN`), and the memory module puts it in the response `details.reason`. When the module is turned
  off, it is still `feature_unavailable`.
- When `memory.sqlite3` does not exist, viewing alone (GET list, search, scopes, tags) does not create it: the store is
  provided as `DeferredMemoryStore`, which creates the file and upgrades the lineage on the first write. After the file
  exists, reopening provides the SQLite store directly. Without a lineage, opening raises `MemoryDbUnavailable` as
  before.
- Fixed: `ProjectMemoryPool.shutdown()` (called by the module stop hook) closes the pool; after that `open` raises
  `MemoryDbUnavailable` (without opening the file), `existing()` returns an empty list, and `is_shut` is set. The
  cache is `agent_console_store.OpenCache` (shared with the record space pool). `close_all()` only closes (the pool
  can be opened again).
- Optional port `projects.lookup` and `ProjectMemoryPool.existing()` (an optional `memory.spaces` method: registration
  ids that are not archived, have a folder, have a writable config folder and already have `memory.sqlite3`; it
  creates nothing and lists the targets of automatic cleanup on the server). `testing.folder_spaces_module` also
  provides `projects.lookup` (a list) (`archived` and `listing` arguments, `ListedProject`).

## 0.1.0

- First release: provides `memory.spaces`. It opens `memory.sqlite3` in the project folder and upgrades its lineage
  (scope `memory`), sets the context `project_id` to the folder id, caches open stores (limit and idle time), protects
  read-only folders, and uses the `DELETE` journal on network drives.

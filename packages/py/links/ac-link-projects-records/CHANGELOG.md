# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-projects-records`, so the web app can show the link module description and settings in English (data only,
  no API change). Log lines are now in English.
- `RecordsSpacePool.batch()` (`BatchRecordsSpaces`): spaces opened inside the block are not evicted by the limit
  (`max_open_spaces`); the pool is trimmed when the outermost block ends. This stops walks (usage totals) from
  reopening the whole least recently used cache every time when there are more projects than the limit. README
  settings table.
- Description of `session_archive.dir`: the `.gitignore` template follows this name (`mod-projects.sessions_dir`
  inherits it).
- Cleanup: moved the open handle cache to `agent_console_store.OpenCache` (shared with the memory space pool, same
  behavior).
- Fixed: `RecordsSpacePool.shutdown()` (server shutdown, called by the module stop hook) closes open handles, and
  after that `open` returns a `link_disabled` handle that does not open files. Handles received before shutdown are
  `link_disabled` too. Previously, even after the pool closed first in the shutdown order, the background log
  collection thread opened new spaces and connections were left behind. `close_all()` still only closes (the pool can
  be opened again).

## 0.1.0

- First release: the port `records.spaces` (space name to a project record database handle, with a limit and idle
  closing), `host_id`, and pending files for failed writes with rewriting.
- Contract 0.13.1: `ARCHIVE_FAILED_CODE` uses the contract document constant
  `KnownIssueCodes.RECORDS_SESSION_ARCHIVE_FAILED` (same value).

# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-memory`, so the web app can show the default memory scope kinds and the
  `memory.import_*` issues in English (data only, no API change).
- The search query hasher (`query_hasher`, `QueryHasher`, `QueryHashModes`, `QUERY_HASH_MODES`) moved to the base
  package `agent-console-query-hash` and is re-exported (same public names, the same objects the wiki uses). Added
  `query_hasher_from_env`. Search queries are encoded with `surrogatepass` (unpaired surrogates hash without an
  exception).
- `query_hasher(mode, salt=)`, `QueryHasher`, `QueryHashModes`, `QUERY_HASH_MODES` and
  `MemoryToolkit(query_hash=)`: the default for `query_sha256` in search events changed from unsalted sha256 to
  HMAC-SHA256 with a random salt (`sha256` gives the old value, `off` leaves it out).
- `WriteBudget` is a re-export of `agent-console-write-budget` (the same object the wiki uses).
  `MemoryToolkit(write_budget=)` accepts the protocol `WriteBudgetLike`.

## 0.1.0

- `DeferredMemoryStore`: a store wrapper that opens on first use (without a store, reads see empty memory; the first
  `write` calls `open_store()`; policies are passed through; optional capabilities `scan_entries` and `count_tags`;
  it does not reopen after closing). Passes the contract suite.
- Moved the zip import safety checks (paths, symbolic links, encryption, zip bomb limits) to `ac-safe-zip` (one set of
  rules shared with the wiki import). The public API, reason codes and `TooLargeError.limit` values are unchanged
  (`unsafe_archive_path` is re-exported).
- First release: the store protocol `MemoryStore` and `InMemoryMemoryStore` (versions, `if_version` conflicts,
  ordering of concurrent writes, soft delete, hard delete, revert, archive, move, search), the write policy (key
  rules, limits, injected secret checks `reject` and `redact`), scope kinds (package default data
  `data/default_scope_kinds.yaml`, merging, origin, turning off, id template resolution, entry point loader), the
  access decision `allowed`, the tool set `MemoryToolkit` (four tools, reason codes, event payloads without content or
  search queries), and `testing` (fake clock, samples, store contract suite).
- SQLite store submodule `sqlite`: `open_sqlite_memory_store` and `SqliteMemoryStore` (tables `memory_entries`,
  `memory_versions`, `memory_tags` and `memory_stats` plus the FTS5 trigram table `memory_search`; writes with
  `BEGIN IMMEDIATE` and busy retries; substring search for queries under three characters or without FTS5; hard
  delete also removes version, tag and search rows; `warnings()`), the table definitions `sqlite.schema`, and the
  scale measurement tools `testing.build_scale_store` and `WorkCounter`. Added the dependency `sqlalchemy`.
- Cleanup rules and export or import: `retention_plan`, `apply_retention`, `compile_retention_rules`,
  `retention_issues` and `retention_subject` (no default rules, pinned entries excluded, first matching rule wins,
  compiled through `ac-conditions`, the applied version has `system` and `label` = rule id), `export_markdown`,
  `write_markdown_archive` and `import_markdown` (`skip`, `overwrite`, `rename`, `dry_run`, rejection of path attacks,
  zip bombs and secrets, `MemoryTransferLimits`, `MemoryTransferCodes`, `InvalidArchiveError`), entry scanning
  `iter_entries`, `SearchableStore` and the optional store capability `EntryScanner`
  (`InMemoryMemoryStore.scan_entries`), and the samples `testing.sample_entry` and `sample_entry_summary`.
- Copy between stores `copy_memory` (filter `MemoryCopyFilter`, conflicts `skip`, `overwrite` and `rename`, scope id
  rewriting `remap`, archive state kept, secret rejections by the target policy reported as `issues`, no content,
  independent after copying) with `matches_filter`, `remap_scope` and `copy_author`.
  `ScopeKindCatalog.unresolvable()` (the same list, a copy that does not resolve scopes). SQLite store `journal`
  (`WAL` by default or `DELETE`, `sqlite.JOURNAL_MODES`).

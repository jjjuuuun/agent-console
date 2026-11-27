# Changelog

## Unreleased (0.2.0)

- Internal log messages are now in English (the default `label` of `SpaceLocator` is `record`).
- Added `DefinitionKind.open_role` (default `None`, the store does not read it): the web route role of the screen that
  opens an item of the kind. The default kinds `graph`, `agent` and `resource` use `definition:<kind>`. The copy
  dialog kind list (`CopyKindInfo.open_role`, contracts 0.16.0) uses it. Additions only, no table changes.
- Added `diff_versions(store, kind, id, from_hash, to_hash=None, *, secret_paths, mask)`, which compares two versions
  of one definition and returns the contract `DefinitionDiff` (document changes as JSON Pointers, content files by
  sha256). Also exported `SECRET_MASK`, `SecretPaths` and the `VersionDiffSource` protocol. The calculation moved here
  from `ac-mod-versions` `VersionService.diff` so that `ac-mod-sdd` can share it without importing another module. The
  caller decides which locations are secret.
- New dependency `agent-console-settings` (document diff). Consumer range: `agent-console-store>=0.2,<0.3`.
- Optional capability `BatchRecordsSpaces` (a `batch()` block; spaces opened inside it are not evicted by the open
  handle limit) and `RecordsStores.batch()` (that block when the port has the capability, otherwise an empty block).
  For walks that read several projects in turn. Additions only.
- The `-n` collision suffix now uses `numbered_id` from `agent-console-numbered-id`, and `numbered_id` and `NoFreeId`
  are re-exported (`agent_console_store`, `agent_console_store.ids`). `unique_id` and the record database backup
  names use it (same behavior). New dependency `agent-console-numbered-id`.
- `DefinitionKind.title` (display name of the kind, default None, not read by the store). The default kinds `graph`,
  `agent`, `resource` and `settings` have values. Additions only, no table changes.
- Batched reads across runs: `RunRepository.list_node_runs_many(run_ids)` and
  `EventRepository.list_many(since, type_prefixes=)` (run id to result; runs that do not exist have no key; the same
  results as calling `list_node_runs` or `list` per run). SQLite runs one query per `RUN_BATCH_SIZE` (200) runs
  (avoids N+1 in usage token totals). Additions only, no table changes.
- `slug_id`, `unique_id` and `SLUG_MAX_CHARS` (name to a new definition id; the copies in `ac-sdd` and `mod-wiki`
  moved here with the same rules). `DefinitionKind.reserved_ids` (words that must not be used as ids of that kind,
  not read by the store; the copy plan reads it). No table changes.
- `OpenCache[V]` and `CacheShut` (a cache of open values by name: least recently used order, idle time, limit,
  rejection of inserts after `shutdown()`). Shared by the project record and memory space pools. Additions only, no
  table changes.
- Fixed: while the first-open hook of `RecordsStores` (`on_open`, restart recovery) is running, other threads opening
  the same space wait until it finishes (limit `open_wait`, default `DEFAULT_OPEN_WAIT` 30 seconds; reentry from the
  same thread inside the hook does not wait; when the first opener's hook returns false, the waiting side calls it
  again). When log collection opened a space right after startup, the first request read the state before recovery
  (`running`). `engine` and `read_engine` of a closed `RecordsDb` report `folder_missing` instead of `corrupt` (the
  same reason as for writes). Additions only, no table changes.
- `SpaceLocator` (record id to the space that holds it: known spaces, then registered space ids up to a limit, then
  the host; remembers where it found it), `DEFAULT_LOCATE_LIMIT` and `DEFAULT_LOCATE_REMEMBER`. Locating
  conversations (`mod-chat`) and runs (`mod-runs`) share it. Additions only, no table changes.
- Fixed: the alembic `command.*` calls of `migrate.upgrade`, `downgrade` and `upgrade_on` are serialized with one
  in-process lock. Alembic swaps module-global proxies (`context`, `op`) while running, so several threads upgrading
  at the same time (even different databases) failed with `KeyError: 'script'` (on server restart, the upgrade in the
  module startup hook overlapped with a background task opening a project record database, and uvicorn failed to
  start with exit 3). No public API changes.
- Server follow-up: `RunRepository.page(conversation_id=, agent=, root_run_id=)` (the same meaning as `list`), and each
  returned run has `has_children` filled (whether it has direct children, counted for all page rows at once with the
  index `ix_runs_parent`, no N+1). Contract 0.13.2 (`Run.has_children`). Additions only, no table changes.
- Events: `EventRepository.list(node=)` (events whose `node_path` contains that node id; the first position uses the
  `node_id` column index, nested graphs use `json_each`), and cross-source cursors `page_across_sources`,
  `SourcePage`, `encode_source_cursor` and `decode_source_cursor` (`<source>.<store cursor>`). Additions only, no
  table changes.
- `RunRepository.page(cursor, limit, project_id, root_only, status, graph_id, labels) -> (items, next_cursor)` (the
  cursor is opaque and ordered by `created_at` and `id` descending), `descendants(root_run_id)`, root run `labels`
  projected into the table `run_labels` (lineage `runs_0004`; `save` rewrites and `delete` removes them; without the
  table they are filtered from `doc`), and the public `InvalidCursor`, `MAX_PAGE_LIMIT`, `encode_cursor` and
  `decode_cursor`. Additions only.
- `RecordsMove`, `MoveSpec`, `MoveDependent`, `run_moves`, `MoveVerifyError` and `MovePartialError` (table-level
  moves: copy, verify, delete the source, and roll back the target on failure). Additions only, no table changes.
- `RecordsStores` (project id to a bundle of stores on the record database, with a first-open hook),
  `RecordsUnavailable.project_id` and `details()`.
- `DefinitionKind.library` (true by default; false means a kind that is not kept in the library space, for extension
  kinds) and `DefinitionKind.with_summary_fields(*fields)`. No store behavior changes.
- Space selection `spaces` (`DEFINITIONS_SPACES_PORT`, `DefinitionSpaces`, `SpaceStores`, `UnknownSpace` 404
  `project.not_found`, `SpacesUnavailable` 409 `feature_unavailable`), the version store on the record database
  `RecordsVersionRepository` (reads through `read_engine`, writes through `writable_engine`), the optional protocol
  `VersionWriteCheck.ensure_writable` (`ObservedVersionRepository` forwards it inward), and `StoreError.field_issues()`:
  `store_error_body` fills `details.issues` of `validation_failed` (an empty list by default, same as before).
- `BaseDefinitionStore.kind_info(name) -> DefinitionKind` (information about a registered kind, for opening a project
  copy space with the same kind). Additions only.
- `open_records_db`, `RecordsDb` and `inspect_records` (open a project record database: missing, current, behind
  (back up, then upgrade), ahead (read only), corrupt, read-only), `RecordsHandle`, `RecordsSpaces`,
  `RECORDS_SPACES_PORT`, `RecordsState`, `RecordsUnavailable`, `is_network_fs` and `can_write_path`,
  `migrate.upgrade_on` and `script_revisions`, and `create_sqlite_engine(journal_mode=None, timeout=)`. No changes to
  existing behavior or tables.
- `DefinitionKind.portable` and `is_portable` (kinds that can live in a project copy space; not singletons or
  `settings`), the pre-write hook `WriteGuard` (`write_guard=`, `FileDefinitionStore` and
  `InMemoryDefinitionStore`), and public YAML tools (`load_yaml_text`, `dump_yaml`, `merge_into`, `wrap_value`,
  `to_plain`, `atomic_write_bytes`). No changes to existing behavior or tables.
- `LazyVersionRepository` and `versions_for(database)` (moved from `ac-mod-definitions`). Store instances that share
  one workspace (the definitions and projects modules) use the same version store.
- The `summary_fields` of the default kinds graph, agent and resource include the scope field `project`
  (`SCOPE_FIELD`, public). It is put in the summary `extra` only when it has a value. `list_graph_summaries` fills
  `GraphSummary.project`.

## 0.1.0

- Run history lineage `runs` (owned by `ac-mod-runs`). `RunRepository.list(root_run_id=)` (all descendants under a
  root), `InteractionRepository.list(root_run_id=)` (based on `root_run_id or run_id`), `call` added to the NodeRun
  key (in memory and SQLite), and `Run.root_run_id`, `parent_node_id`, `NodeRun.call`, `invoked_by` and
  `Interaction.root_run_id` stored as columns (only when present). `schema.runs_lineage_metadata` and
  `runs_lineage_active`, and four run history tables added to `MODULE_OWNED_TABLES`. The legacy migrations 0001 to
  0003 are unchanged.
- Moved the conversation and chat queue stores (`ConversationRepository`, `QueueRepository`, `QueuedItem`,
  `QueueCounts`, SQLite and in memory, `conversations` and `queue` of `SqliteStorage`/`InMemoryStorage`) to
  `ac-mod-chat/storage` (removed from the public API). Tables and migrations 0001 to 0003 are unchanged, and
  `conversations` and `chat_queue` were added to `MODULE_OWNED_TABLES`.
- `DefinitionStore.delete(..., expected_version=)` (If-Match for deletes; `VersionConflict` when different).
- `SqliteDatabase` (database handle: upgrades for legacy and each module lineage, a version table per lineage),
  `MigrationBranchLike` and `migrate.upgrade(versions=, version_table=)`. The `usage_observations` store
  (`storage.usage`, `UsageObservationRepository`) and its table definition moved to `ac-mod-usage/storage` (tables and
  migrations 0001 to 0003 unchanged). `schema.MODULE_OWNED_TABLES` and `include_object`.
- `ObservedVersionRepository` (a callback for each version record, used for the save notification
  `definitions.saved`; no store code or schema changes).
- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.

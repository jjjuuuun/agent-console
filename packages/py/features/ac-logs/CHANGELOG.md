# Changelog

## Unreleased (0.2.0)

- Diagnostic event titles (`로그 형식 해석 실패`, `로그 분류 실패`) are in the message catalog `en`.
- `LogEventDraft.text_templates` (`/title` or `/summary` → `TextTemplate` list, contracts 0.16.1
  `LogEvent.text_templates`, `logs` 2.1.0): source template + values of a title or summary that mixes in values. The core
  masks the templates with the same `redact` as the field and keeps only entries whose filled text equals the stored
  (masked, cut) field; the event carries them in `LogEvent.text_templates` (memory and SQLite indexes, no table change —
  the field is in the event body). Requires `agent-console-contracts>=0.16.1,<0.17`. Consumer range:
  `agent-console-logs>=0.2,<0.3`.
- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs` `ac-logs`, so
  the web app can show the default log categories, dashboard fields and the built-in log sources and classifiers in
  English (data only, no API change).
- `open_existing_log_index` error messages are in English (`log index file not found: …`,
  `log index tables are missing: …`); tools print them to the terminal.
- Session summaries (`list_sessions`, in both the memory and SQLite indexes) no longer fill the old
  `LogSessionSummary.project` (`LogProjectRef`) and fill only `project_id` (the field is to be removed in contract
  0.15.0). The project field of the log archive HTML is `project_id` (the same value as now). The session checks in
  the public test kit `testing` look only at `project_id`, so external index implementations do not have to fill
  `project`. The reserved filter value `UNGROUPED_PROJECT` (`~ungrouped`) is unchanged.
- Moved path globs to the base package `agent-console-path-glob` (`glob_match` and its rules unchanged, new
  dependency).
- The default classification data has the category `wiki` (only a label, not added to `order`).
- Optional row-level prefilter for extension filters: `RowPredicate`, `RowCheckedPredicate`, `row_check_of`,
  `EVENT_ROW_FIELDS`, `EventRow` and `RowCheck`. The SQLite index asks the column values first through `ac_row_ok`
  and reads the body only for rows it cannot decide (same results). Example: `testing.FieldFilter(row_check=True)`.
- When a SQLite value list for IN has more than 500 values, a `json_each` subquery is used (one bind variable), so
  even 40,000 values stay under the default variable limit (32,766). The `category` and `agent`/`from`/`to` filters
  use the same path.
- Breaking change: the session project is the registered project id. `QueryContext.projects` (the old grouping rules)
  and `ungrouped_label` are replaced by `QueryContext.project_for` (cwd to registration id) and
  `query_context(project_for=)`. `project_of` looks only at `project_for` (not `repo_root`). Session summaries have
  `project_id` (the old `project` is filled with the same id and deprecated). Removed the old grouping functions
  `resolve_project`, `group_projects`, `project_base` and `DEFAULT_UNGROUPED_LABEL` (`UNGROUPED_PROJECT` means the
  session belongs to no registered project). The old setting `logs.projects.git_worktrees` is not read.
- `ProjectFolders` = `registered`, `retained` (kept: not read again, but the index is kept) and `project_for`, with
  `contains(path)` and `with_retained()`. Removed the old `current` and `select(scope)`. When the collector decides
  whether to clean up units outside the scope, retained folders count as in scope, and when a scope is set it does not
  read `.git` for a cwd outside the registered folders.

## 0.1.0

- `parse_log_filter` keeps an empty value (`name=`) of an extension filter as the single value `""` (an unnamed
  group, `arch_group=`). Empty values of built-in fields are still dropped.
- First release: log source and classifier protocols and registries, `JsonlFileSource`, `LogIngestor`, the
  `LogIndex` protocol, query semantics (`query`), `testing.MemoryLogIndex` and a contract test suite, the built-in
  plugins `normalized-v1` and `mapped-jsonl`, and the default classification `default_taxonomy.yaml`.
- `JsonlFileSource` detects rotation (a head fingerprint `state.jsonl_head` plus a content generation
  `state.jsonl_generation`, giving `RawRecord.generation` and `identity_for(generation=)`; with the default 0 the
  identity is unchanged), fixes an undercount of `read_bytes` when rereading a shrunk file, and has a file symbolic
  link policy (links outside the root are skipped, the same real file is read once). The existing public API is
  unchanged; only keyword arguments and fields with defaults were added.
- The registry name constants `LOG_SOURCES_EXTENSION` and `LOG_CLASSIFIERS_EXTENSION` are exported from the package
  top level (so the host plugin loader uses the extensions with the same names in the bundle).
- Fixed `LogRegistries(sources=, classifiers=)` replacing an empty registry with a new one because it is falsy (it
  now checks `is not None`). Loading into empty extensions of the host bundle relies on this.
- Offline archive: `build_archive` (`LogArchive` v1, filter scope, event count and byte limits, export masking),
  `filter_to_params`, `render_archive` (HTML without scripts; a CSP blocks scripts and external resources) and
  `escape_html`.
- `LogEventDraft.summary` (optional, default None). When a classifier provides it, that plain text is the list
  summary (with the same masking and length limit); otherwise detail (or raw) is turned into a string as before.
- Lone surrogates (U+D800 to U+DFFF, broken UTF-16 originals) are replaced with U+FFFD by `build_record` in every
  string field (inside body and original, including tags, correlations, token samples and line information), so
  collection does not stop on SQLite write or serialization failures. `build_archive` and `render_archive`
  (`escape_html`) have the same protection. Public function `scrub_surrogates`.
- Session title ranking rule data (`SessionTitleRule`, `QueryContext.session_title_rules`,
  `data/default_session_title_rules.yaml`, `query_context(session_title_rules=)`, `pick_session_title`), the hidden
  category `meta` in the default classification, and query plan tests for paired queries using the index.
- Indexes `(session, seq)`, `(thread, seq)` and `(run_id, seq)` (replacing the old index on `run_id` alone;
  `open_log_index` updates the indexes of an existing file, and the server uses the `mod-logs` revision `logs_0002`).
  Unpaired events skip copying `duration_ms`. Scale measurement tools `testing.build_scale_index`,
  `CountingPredicate`, `read_all_pages`, `time_best` and `perf_strict`.
- Index purging: `purge_index` and `reset_index` (scope `PurgeScope`, result `PurgeResult`, optional capability
  `PurgeableLogIndex`; the `LogIndex` protocol is unchanged), `MemoryLogIndex.purge` and `SqliteLogIndex.purge`,
  `sqlite.open_existing_log_index` that opens only an existing index, and the contract suite
  `testing.PurgeContractTests`.

# agent-console-logs

The log analysis core. It collects logs from several tools into the same structure (normalized events) and queries them.

- **Sources and classifiers are extension points.** Register log sources (entry point `agent_console.log_sources`) and
  classifiers (`agent_console.log_classifiers`) to use them. The built-in `normalized-v1` and `mapped-jsonl` are also just
  the first implementations that come in through entry points. This package does not know specific tool formats (Claude Code and others).
- **Sources are only read.** Sources open files only through the injected `open_read`. This package has no path that writes sources.
- **Classifiers are stateless per row.** Grouping responses, pairing calls, and durations are computed at query time from explicit ids.
- **Tokens are counted once per response.** For each (source, thread, message_id), the one sample with the largest output.
- **The code does not interpret category names.** Display names, hiding, and errors (`tone: danger`) are classification taxonomy data
  (`data/default_taxonomy.yaml` + setting `logs.taxonomy`). It works even with an empty taxonomy.
  The default taxonomy has a hidden category `meta` (`visible: false`, records internal to a format; hidden only in the timeline).
- **Session title priority is data.** `QueryContext.session_title_rules` (a list of `SessionTitleRule(tag, pick=first|last)`)
  is checked from the top, and the first rule with candidates wins. The default is `data/default_session_title_rules.yaml` (the last
  `session_title.renamed` > the last `session_title.generated` > the first `session_title`); if the file is missing or empty,
  `DEFAULT_SESSION_TITLE_RULES` (the first `session_title`). Change it with `query_context(..., session_title_rules=)`.
- The `duration_ms` pairing query for lists and timelines in the SQLite index uses the (`thread`, `call_id`) index `ix_log_events_thread_call` (query plan test).
- Used without the server or the web app. It does not import fastapi or starlette.

## Installation

```bash
uv sync --all-packages                              # inside the workspace
uv pip install ./packages/py/features/ac-logs       # standalone (with contracts and registry)
```

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `agent-console-contracts` | `LogEvent`, `TokenSample`, `LogSettings`, descriptors, DTOs | Single source of contracts | — |
| `agent-console-registry` | Registry, entry point loading | Every extension point uses the same registration method | — |
| `jsonschema` | Validates source and classifier settings against `config_schema` and fills defaults | The validator already used in the workspace | Dynamic pydantic models |
| `ruamel-yaml` | Reads the default taxonomy (YAML package data) | The workspace YAML standard | PyYAML |
| `sqlalchemy` | SQLite index (`agent_console_logs.sqlite`, Core) | The workspace store standard; takes the engine of the server database handle as is | The standard `sqlite3` directly (weak schema sharing and portability) |

## Minimal usage

Collect v1 jsonl in a temporary folder into an in-memory index and query it.

```python
>>> import json, tempfile
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex

>>> folder = Path(tempfile.mkdtemp())
>>> rows = [
...     {"schema_version": 1, "category": "llm", "title": "답변", "session": "S", "thread": "main",
...      "message_id": "m1", "usage": {"input_tokens": 10, "output_tokens": 3}},
...     {"schema_version": 1, "category": "llm", "title": "답변(이어짐)", "session": "S",
...      "thread": "main", "message_id": "m1", "usage": {"input_tokens": 10, "output_tokens": 8}},
...     {"schema_version": 1, "category": "error", "title": "실패", "session": "S"},
... ]
>>> _ = (folder / "events.jsonl").write_text(
...     "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
... )

>>> registries = LogRegistries()
>>> _ = registries.load()                       # entry point X5·X6
>>> index = MemoryLogIndex()                    # in real use, the SQLite index
>>> ingestor = LogIngestor(index, registries)   # redact=, environ=, open_read= can be injected
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}]}
... )
>>> ingestor.scan(settings).new_events
3
>>> ingestor.scan(settings).new_events          # incremental: 0 when nothing changed
0

>>> ctx = query_context(settings)               # taxonomy (settings data); projects through project_for=
>>> [e.title for e in index.query_events(LogFilter(), ctx).items]
['답변', '답변(이어짐)', '실패']
>>> session = index.list_sessions(LogFilter(), ctx)[0]
>>> (session.events, session.errors, session.tokens.output)   # tokens of the same response m1 counted once
(3, 1, 8)

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Public API

| Group | Names |
| --- | --- |
| Sources, classifiers, drafts | `LogSource`, `SourceRef`, `Cursor`, `RawRecord`, `ReadResult`, `LogSourceContext`, project scope `ProjectFolders` (`registered`, `retained`, `project_for`; scope = all registrations as one; unregistered folders are not read again and their index is kept), `ScopedLogSource` (given `LogIngestor(projects=…)`, units outside the scope are skipped for sources that implement `in_scope`, and if units outside the scope are already indexed, that source's index is cleared and read again: `scope_skipped`, `scope_purged`. Units for which `JsonlFileSource.accepts` is false do not have their context read at discovery), `JsonlFileSource` (+`JSONL_CONFIG_SCHEMA`), `LogClassifier`, `ClassifyContext`, `LogEventDraft`, `AgentInfo`, convention tags `TAG_TOOL`, `TAG_SESSION_TITLE`, `TAG_DIAGNOSTIC`, `DIAGNOSTIC_META_KEY` |
| Registries and collection | `LogRegistries` (`load()` → `{"log_sources": [LoadReport], "log_classifiers": [...]}`; registry names `LOG_SOURCES_EXTENSION` and `LOG_CLASSIFIERS_EXTENSION` = the extension names in the host bundle), `LogIngestor` (`scan`, `sources`, `add_runtime_source`), `source_enabled` |
| Index | The `LogIndex` protocol, `IndexRecord`, `IndexBatch`, `BatchResult`, `StoredCursor` |
| Clearing the index | `purge_index(index, *, sources=None, categories=None, before=None, rescan=True, dry_run=False) -> PurgeResult`, `reset_index(index, *, dry_run=False)`, scope `PurgeScope`, optional capability `PurgeableLogIndex` (`purge(scope, dry_run=)`; the in-memory and SQLite indexes have it) |
| Reading rows | `query_event_rows(index, flt, ctx) -> LogEventRowPage` (`rows`, `next_cursor`), `iter_event_rows(index, flt, ctx, on_page=)` (to the end, `on_page(row count)` per page), `page_rows(read, flt, on_page=)` (page read function → rows), optional capability `LogEventRowReader` (methods `query_event_rows` and `iter_event_rows`; the in-memory and SQLite indexes have it), `event_row(event)`, `complete_event_row(data, seq=)`, types `LogEventRow`, `PageCallback` |
| SQLite index | `agent_console_logs.sqlite`: `SqliteLogIndex(engine)`, `open_log_index(path)` (standalone, `create_all`), `open_existing_log_index(path)` (existing indexes only; creates no files or tables), `create_log_engine`, tables `log_metadata`, `log_events`, `log_bodies`, `log_search`, `log_tags`, `log_links`, `log_corr`, `log_agents`, `log_cursors`, `log_usage` |
| Queries | `LogFilter` (including `thread`, `scope`, `max_seq`, `extra`), `parse_log_filter(extra=)`, `LogQueryError(path)`, `QueryContext` (`scope`, `predicates`, `extra_names`), `query_context`, `require_refined`, `query_schema(extra_filters)`, `DIMENSIONS`, `METRICS`, `FILTER_FIELDS`, submodule `query` (pure functions for query semantics) |
| Query extensions | `LogScopeKind` (`id`, `resolve(value) -> LogScope`), `LogScope` (union of sessions and run_ids), `LogFilterExtension` (`fields`, `build(values, LogFilterContext) -> EventPredicate`), the bundle `LogQueryExtensions` (`collect`, `parse`, `refine`, `schema`, `skipped`), row-based prefiltering (optional) `RowPredicate`, `RowCheckedPredicate`, `row_check_of`, `EVENT_ROW_FIELDS`, `EventRow`, `RowCheck` |
| Pure functions | `bounded`, `event_uid`, `identity_for`, `build_record`, `link_events`, `pair_durations`, `merge_taxonomy`, `load_default_taxonomy`, `git_worktree_root` (the old grouping `group_projects` and `resolve_project` were removed; session projects use `QueryContext.project_for`), `block_windows`, `rolling_totals`, `sum_samples`, `glob_match`, `json_pointer`, `scrub_surrogates`, `dirty_surrogates` (lone surrogates → U+FFFD, and the check; `build_record` applies it to every string) |
| Archives | `build_archive` (`LogArchive` v1: filter scope, `max_events`, `max_bytes`, `redact`, `ARCHIVE_VERSION`, `DEFAULT_ARCHIVE_MAX_EVENTS`, `DEFAULT_ARCHIVE_MAX_BYTES`), `filter_to_params`, `render_archive` (script-free HTML, `DEFAULT_ARCHIVE_TITLE`), `escape_html` |
| Test support | `testing.TableScopeKind`, `testing.FieldFilter` (examples and fakes), `testing.MemoryLogIndex`, `testing.LogIndexContractTests` (other index implementations inherit it), `testing.PurgeContractTests` (clearing semantics), `testing.RecordingOpen`, `no_writes_under`, `tree_digest` (watching for writes to sources, hashing) |

## SQLite index

`SqliteLogIndex` passes the same contract test suite as `MemoryLogIndex` (`LogIndexContractTests`),
and tests check on random data that every query answers the same as `MemoryLogIndex`.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_logs import IndexBatch, LogFilter, QueryContext
>>> from agent_console_logs.sqlite import open_log_index
>>> from agent_console_logs.testing import make_record
>>> path = Path(tempfile.mkdtemp()) / "logs.sqlite3"
>>> index = open_log_index(path)               # standalone use: creates the tables itself (create_all)
>>> index.write(IndexBatch(records=[make_record("llm", title="안녕", session="S")])).inserted
1
>>> index.close()
>>> [e.title for e in open_log_index(path).query_events(LogFilter(), QueryContext()).items]
['안녕']

```

- Inside the server, the tables are created by the migration lineage `logs` of `ac-mod-logs` (`create_all` is for standalone use only).
  The `ac-mod-logs` tests check with `compare_metadata` that the two shapes are the same.
- Large columns are split off. `log_events` has only narrow columns used for filtering, sorting, and aggregation; the body JSON (`log_bodies.body`), raw data (`heavy`),
  and search strings (`log_search`) are kept separately. Lists, session summaries, and aggregates read only narrow rows.
- The same uid is inserted only once (`INSERT ... DO NOTHING`), and writes start with `BEGIN IMMEDIATE` so they do not interleave with other
  processes. seq is `AUTOINCREMENT`, so it is never reused after deletes (safe for keyset cursors).
- Tokens are one row in `log_usage` per (source, thread, message_id); when the same key comes again, it is replaced only when the output is greater or equal.
- Limits: the query `q` scans `log_search` (hundreds of ms at 100,000 events). The session list is aggregated per query.

### Clearing the index

The index never rewrites the same uid. So even when classification defaults change (for example, excluding raw request bodies), events already inserted
stay as they are. `purge_index` deletes the events in a scope (sources, categories, time, all ANDed) and their dependent rows, and with `rescan=True` (default)
it also deletes the cursors of the sources in scope (all sources if none) so the next collection reads the sources from the beginning. Remaining events have the same uid and are not
inserted again; only the deleted ones come back under the current rules. Source files are not touched.

```python
>>> from agent_console_logs import purge_index, reset_index
>>> index = open_log_index(":memory:")
>>> _ = index.write(IndexBatch(records=[make_record("llm"), make_record("blob", source="s")]))
>>> purge_index(index, categories=["blob"], dry_run=True)       # count only
PurgeResult(dry_run=True, events=1, usage=0, cursors=0, agents=0)
>>> purge_index(index, sources=["s"], categories=["blob"]).events
1
>>> reset_index(index).events                                     # everything (including cursors and agents)
1

```

- Token samples are deleted when their key (source, thread, message_id) matches an event being deleted and no remaining event. Without a category condition,
  samples matching the source and time conditions are deleted too. Agent display rows are deleted when there are no category or time conditions (a whole source).
- Empty lists are rejected (`ValueError`; "no condition" is None). seq continues (refreshes based on seq in the web app never go backward).
- On the server, `POST /api/v1/logs/index/purge` (`ac-mod-logs`, dry_run by default); on the command line, `agent-console logs purge`.

### Reading rows (without models)

Callers that read a whole scope only to judge and aggregate (for example the architecture map) do not need event models. `iter_event_rows` gives the same list
as JSON rows (dicts). A row is the same as `model_dump(mode="json", by_alias=True)` of the `LogEvent` on the same page (the list
shape: `detail` and `raw` are None, keys use contract aliases such as `from`). The SQLite index fills only defaults into the stored body JSON
and skips validation and dumping (optional capability `LogEventRowReader`). `iter_event_rows` reads only the body strings per page and builds rows
one at a time (it does not hold a page's row dicts all at once, so memory and GC pressure stay low on large scopes). Indexes without the capability
dump the `query_events` results. Treat rows as read-only.

```python
>>> from agent_console_logs import event_row, iter_event_rows
>>> index = open_log_index(path)
>>> rows = list(iter_event_rows(index, LogFilter(), QueryContext()))
>>> rows[0]["title"], rows[0]["from"], rows[0]["detail"]
('안녕', [], None)
>>> rows == [event_row(e) for e in index.query_events(LogFilter(), QueryContext()).items]
True
>>> index.close()

```

## Query extensions: scope kinds and filter extensions

The filter `scope=<kind>:<value>` and extension filter names come in through registration. `LogQueryExtensions` reads the filters
(`parse`) and resolves them before the query (`refine`), putting the union of sessions and run_ids (`QueryContext.scope`) and event judge
functions (`QueryContext.predicates`) into the query context. Index implementations see only the resolved context (a differential test checks that in-memory and SQLite results
are the same). Without registrations the context is unchanged, and passing an unresolved `scope` or extension filter to an index raises
`LogQueryError`.

- Scope: the event's session or run_id must be in the union. Token samples must have their session in it, or the same response key as an event in the run_id
  scope.
- Extension judgements and `max_seq` are event-only filters (samples are filtered by the response keys of matching events). SQLite calls the judgements as
  connection-only SQL functions, so pages, cursors, and aggregates stay the same, but the body JSON is read for each candidate row.
- **Row-based prefiltering (optional capability)**: when a judge function has `row_fields` (index column names from
  `EVENT_ROW_FIELDS`) and `check_row(row) -> True | False | None` (`RowPredicate`, default implementation
  `RowCheckedPredicate`), SQLite asks with column values first and reads the body into a `LogEvent` only for rows with `None` (unknown)
  to judge them. Definite values must equal the judge function's values (the in-memory index always uses the judge function).
  `testing.FieldFilter(..., row_check=True)` is an example.
- When a value list (filter values, scope sessions, run_ids) exceeds 500 values, SQLite expands one JSON array with `json_each`
  (one bind variable, so even tens of thousands of values do not hit the variable limit).

```python
>>> from agent_console_logs import IndexBatch, LogQueryExtensions, QueryContext
>>> from agent_console_logs.testing import FieldFilter, MemoryLogIndex, TableScopeKind, make_record
>>> index = MemoryLogIndex()
>>> _ = index.write(IndexBatch(records=[
...     make_record("tool_call", tool="Bash", session="S1"),
...     make_record("tool_call", tool="Read", session="S1"),
...     make_record("llm", session="S2", run_id="r1"),
... ]))
>>> ext = LogQueryExtensions.collect(
...     [TableScopeKind("run", {"r1": ([], ["r1"])})],     # scope kind
...     [FieldFilter("only_tool", "tool")],                # filter extension
... )
>>> flt = ext.parse({"only_tool": "Bash"})
>>> [e.tool for e in index.query_events(flt, ext.refine(flt, QueryContext())).items]
['Bash']
>>> flt = ext.parse({"scope": "run:r1"})
>>> [e.session for e in index.query_events(flt, ext.refine(flt, QueryContext())).items]
['S2']
>>> from agent_console_logs import RowCheckedPredicate, row_check_of
>>> fast = RowCheckedPredicate(
...     lambda e: e.tool == "Read", lambda row: row["tool"] == "Read", frozenset({"tool"})
... )
>>> sorted(row_check_of(fast)[0])
['seq', 'tool']
>>> [e.tool for e in index.query_events(ext.parse({}), QueryContext(predicates=(fast,))).items]
['Read']

```

## Collection rules (the same as agent_bench `_ingest`)

- Reading continues from a byte offset cursor. The budget of one collection per source is `budget_bytes` (default 8 MB), and the rest is
  read in the next collection.
- An unfinished last line is held back, and read with `scan(final=True)`.
- If a file becomes smaller than the cursor, it is read again from the beginning. Thanks to identity, nothing is duplicated.
- **Rotation detection**: a sha256 fingerprint of the read head (up to 4 KB, up to complete lines) and of the first line is kept in the cursor `state.jsonl_head`.
  If the head differs at the next collection (a larger new file with the same name, the same size with different content, and so on), the file is read from the beginning and
  the content generation (`state.jsonl_generation`, `RawRecord.generation`) goes up. The generation is part of the default identity
  (`{source}:{ref}@{generation}:{offset}`), so new lines at the same position are not discarded as overlapping old lines. Reading the same generation again
  gives 0 duplicates. Old cursors without a fingerprint keep reading on.
- **Limitation**: a file with the same size and the same first 4 KB that changed only after that is not detected (if size and mtime are also the same, it is not even
  read). When a file shrinks, it is treated as the same file truncated only when the fingerprint of the head (the first line, if the file is shorter) matches,
  and the generation is kept (0 duplicates through identity). If it differs or cannot be checked (shorter than the first line, old cursors without fingerprints), it is treated as new content
  and the generation goes up. In that case, a file rewritten with the same content can produce duplicate events (chosen over data loss; tokens are
  counted once by the message_id rule).
- **Symbolic links**: folder links are not followed. File links are read only when their real location is inside that root, and links pointing outside
  the root are skipped (left out of `discover`, and `resolve` refuses them too). When several paths point to the same real file,
  only one is produced (non-link paths first, then by name).
- Lines that fail to parse or classify are not dropped but kept as diagnostic events (`source = "diagnostic"`, category `error`, tag `diagnostic`).
- Event batches and cursors are written in the same `write` call (one transaction). Unchanged files are not read.
- identity: draft `identity` → tool events (`TAG_TOOL` + `call_id`) `tool:{source}:{thread}:{call_id}:{stage}` →
  `{source}:{ref}[@{generation}]:{offset}[:{index}]` (the generation only for rotated files). uid = `sha256(identity)[:24]`.
- `repo_root`: when the cwd's `.git` is a worktree marker file, the main repository path (read-only, cached per collection).
  With the setting `logs.projects.git_worktrees: false`, it is not computed.

## Offline archive

`build_archive` packs the events matching a filter (with bodies), session summaries, threads, evidence links, and the taxonomy into `LogArchive` v1
(agent_bench `LogStore.export`). `render_archive` draws it as one **script-free** HTML page (agent_bench
`render_archive` embedded the web JS). It opens without a network, and external resources and scripts are blocked with
`Content-Security-Policy`.

- Scope: the filter as is (`limit` and `cursor` are not used; it goes to the end). Session summaries are counted with the same filter.
- Size: `max_events` (default 5000), `max_bytes` (total event JSON, default about 20 MB), `max_detail_bytes` (the body of one event).
  Beyond that, only the first part is included with `truncated = True` (the HTML shows a notice).
- Masking: the index copy was masked at collection. With `redact`, titles, summaries, bodies, raw data, session titles, and filter values are masked once more with the current rules.
- HTML: `<meta charset="UTF-8">`, a Korean font list (with system font fallbacks), `word-break: keep-all`; bodies, raw data, and long summaries are
  collapsed in `<details>`, and every value is escaped (`&<>"'`, U+2028 and U+2029 → numeric references, control characters → U+FFFD).
  Category names, colors, and emphasis come from the archive's taxonomy data (errors are shown for `tone: danger` categories).

```python
>>> from agent_console_logs import IndexBatch, LogFilter, QueryContext, build_archive, render_archive
>>> from agent_console_logs.testing import MemoryLogIndex, make_record
>>> index = MemoryLogIndex()
>>> _ = index.write(IndexBatch(records=[
...     make_record("llm", title="<답변>", session="S", detail={"text": "본문"}),
...     make_record("llm", title="다른 세션", session="T"),
... ]))
>>> archive = build_archive(index, LogFilter(session=("S",)), QueryContext(), exported_at=0.0)
>>> [(e.title, e.detail) for e in archive.events], archive.truncated
([('<답변>', {'text': '본문'})], False)
>>> page = render_archive(archive)
>>> "&lt;답변&gt;" in page, "<script" in page, "다른 세션" in page
(True, False, False)

```

## Default plugins

| id | Source | Classifier settings |
| --- | --- | --- |
| `normalized-v1` | `roots`, `include` (default `**/*.jsonl`), `exclude`; off by default | `default_actor` (default `controller`). Required `schema_version: 1`, `category`, `title`; reserved keys ignored; actor = actor → thread → `default_actor` |
| `mapped-jsonl` | Same as above | `fields` (field → JSON pointer), `defaults` (default `{category: other}`), `value_maps`, `correlation`, `usage`, `skip_if_missing` |

A new source implements `LogSource` (inheriting `JsonlFileSource` for files), and a new classifier implements `LogClassifier`;
put their names in the entry points of `pyproject.toml`. Sources that read data from other modules are added with
`LogIngestor.add_runtime_source(source, classifier=...)`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

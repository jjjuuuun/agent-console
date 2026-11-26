# agent-console-link-logs-architecture

Logs and architecture map link module. It projects the scope events of the log index (`logs.query`) onto architecture map
profiles (`architecture.catalog`) and adds architecture map filters to the event table.

- `GET /logs/architecture?<log filters>&profile=` → `ArchitectureView` (an architecture map that is complete enough to draw).
  The log filters are the filters of `GET /logs/schema` as they are (`session`, `thread`, `scope`, `max_seq`, and so on).
- `GET /logs/events/{uid}/architecture?profile=` → `ArchitectureMembership` (the cells, edges, and groups the event matched).
- Filter extensions `arch`, `arch_group`, and `arch_sources`: add the `selector` of an architecture map result to the event list query
  as it is. When you pass the same scope filters and the `max_seq` of the result, the table total equals the `count` of that cell.
- Web role `logs:architecture`. When this link is off, the routes return 404 and `arch` is an unknown filter (422). The logs and
  architecture map modules keep working.

## What is passed in (no names in code)

| Value | Where it comes from |
| --- | --- |
| Cells, edges, conditions, source priority | The profile (`architecture.catalog`, user data) |
| Error categories | The query context `query_context().error_categories` (categories with `tone: danger` in the classification scheme) |
| Source kinds | The source id as it is (source id = registration name). The `source_kinds` setting changes it |
| Token samples | `logs.query.token_samples` (same scope filters) |

## Result cache, incremental reads, and incremental projection

For each scope (filter), the link remembers the event summaries it read, the token samples, the match results per profile, the running totals, and the projection result.

- Scope events are read as JSON rows, not models. When `logs.query` has the optional capability `iter_event_rows` (`LogRowReader`,
  which `mod-logs` has), that is used; otherwise the `events` results are dumped to rows (the result is the same).
- New rows are matched against every remembered profile (key) when they are read, added to the running totals per cell and edge (`ArchitectureTally`), and then
  dropped. A scope keeps only the event summaries (`LIGHT_FIELDS`: seq, source, uid, thread, response id, time, duration) and the match results.
  When a new profile arrives for a scope that was already read, the same scope is read again and matched against that profile only (if the second read differs,
  it starts over).
- On the next call it reads only after the last `seq` (keyset cursor) and matches and totals only the new events. When there are no new events and (profile,
  source kinds, `max_seq`) are the same, it returns the projection result as it is. When `max_seq` is before the end of the scope, the events up to it are
  projected at once from the summaries.
- One query for the scope total (`total`) checks that the remembered scope is still valid. When it differs (the scope kind now covers more sessions,
  grouping settings changed, retention cleanup ran), it reads again from the start.
- The `arch` filter looks at the match results in this cache first (events in a scope that was drawn are not matched again).
- When the scope events exceed `max_scope_events` (a `mod-architecture` administrator value), the request fails with 422
  `architecture.scope_too_large`.

Matching uses list events (without `detail` and `raw`). So a profile condition that looks at the body (`/detail/...`) does not
match (the architecture map and the table filter must see the same shape for the counts to agree).

## Install

```bash
pip install agent-console-link-logs-architecture
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-logs-architecture
```

## Minimal usage

Without a server, draw an architecture map from one index and a profile, then filter the event table with a cell's selector.

```python
>>> from agent_console_architecture import parse_profiles_document
>>> from agent_console_link_logs_architecture import ArchitectureFilter, LogArchitectureViews
>>> from agent_console_link_logs_architecture.testing import IndexLogQuery, StaticCatalog
>>> from agent_console_logs import IndexBatch
>>> from agent_console_logs.testing import MemoryLogIndex, make_record
>>> profiles = parse_profiles_document('''
... profiles:
...   flow:
...     cells:
...       ask: {when: {all: [{path: /category, op: eq, value: input}]}}
...       work: {when: {all: [{path: /category, op: eq, value: tool}]}, group_by: /tool}
... ''')
>>> index = MemoryLogIndex()
>>> _ = index.write(IndexBatch(records=[
...     make_record("input", session="s1"),
...     make_record("tool", session="s1", tool="Read"),
...     make_record("tool", session="s1", tool="Grep"),
...     make_record("tool", session="s2", tool="Read"),
... ]))
>>> filters = []
>>> query = IndexLogQuery(index, filters=lambda: filters)
>>> catalog = StaticCatalog(profiles)
>>> views = LogArchitectureViews(query, catalog)
>>> filters.append(ArchitectureFilter(catalog, views.cache))
>>> view = views.architecture({"session": "s1"})
>>> [(c.id, int(c.metrics["count"].value or 0)) for c in view.cells]
[('ask', 1), ('work', 2)]
>>> work = view.cells[1]
>>> page = query.events(query.parse_filter(
...     {"session": "s1", "arch": work.selector.arch, "max_seq": view.max_seq}))
>>> [e.tool for e in page.items]
['Read', 'Grep']

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Ports and settings

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `logs.query` | `query_context`, `parse_filter`, `events` (keyset pages, `with_total`), `event`, `token_samples`, and `iter_event_rows` when present (optional capability `LogRowReader`) |
| Required | `architecture.catalog` | `catalog() -> ProfileCatalog`, `operators()`, `max_scope_events` |
| Provides | `logs.filter_predicates` | `ArchitectureFilter` (`arch`, `arch_group`, `arch_sources`) |
| Provides | `architecture.profile_checks` | `UnlistedPathCheck`: when a profile condition path is under an `unlisted_paths` prefix, warning `architecture.condition_path_unlisted`. The receiving `mod-architecture` adds it to the list `issues`, the detail `problems`, and `POST /architecture/profiles/check` |

Settings `modules.options.link-logs-architecture`:

| Key | Default | Meaning |
| --- | --- | --- |
| `source_kinds` | `{}` | Source id → profile source kind. Sources not listed use their id as it is |
| `cache_scopes` | `8` | Number of scopes to remember (0 = no cache, start over every time) |
| `cache_events` | `100000` | Upper limit on the total number of events across remembered scopes (when exceeded, the least recently used scopes are dropped first) |
| `cache_profiles` | `4` | Number of match results (profile keys) to remember per scope. Editing a profile creates a new key, so when exceeded the least recently used ones are dropped first |
| `page_size` | `1000` | Page size for reading scope events from the index (1 to 10000) |
| `unlisted_paths` | `["/detail", "/raw"]` | Event path prefixes that are not in the list body. The architecture map sees only list events, so the profile check warns about conditions under these prefixes (empty list = no warnings) |

## Standalone run

```bash
python -m agent_console_link_logs_architecture [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_logs_module` (an empty in-memory index) and `testing.local_catalog_module` (the package's
default profiles). To use real logs and profiles, start it with `--with mod-logs --with mod-architecture`.

## Test helpers (`agent_console_link_logs_architecture.testing`)

`click_targets`, `selector_params`, `click_count_mismatches` (checks that click counts agree; also usable against HTTP list
queries), `LogArchitectureHarness` (index + query + profiles + architecture map + filter), `random_records`,
`IndexLogQuery`, and `StaticCatalog`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

Measurements (50,000 events: first call, cache hit, incremental) are in `tests/test_agent_console_link_logs_architecture_scale.py`
(numbers with `-s`; wall-clock assertions only when `AGENT_CONSOLE_PERF=strict`).

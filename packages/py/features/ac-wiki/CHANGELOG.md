# Changelog

## Unreleased (0.2.0)

- Added the freshness window `WikiRepository(freshness_seconds=)` (default `0.0` = list the page folder on every read,
  unchanged behavior). Above 0 the repository keeps one snapshot (page listing, link index, listing issues, history
  summaries) and does not list the folder again until the window has passed since the last check (a clock that goes
  back counts as expired). When the listing is unchanged after the window, the built index is kept. Writes, deletes,
  moves, restores, imports, history records and `scan()` drop the snapshot at once; write decisions, previews and
  moves always check the current files; `view()` rebuilds when the viewed page's file differs from the snapshot.
  Concurrent reads check once. New public API: `WikiRepository.page_files()`, `WikiRepository.invalidate()` and
  `WikiRepository.index(fresh=)`. `check_page_path` and `page_path_for_file` remember paths that passed (rejections
  are checked again every time). Consumer range: `agent-console-wiki>=0.2,<0.3`.
- The README has a "Limitations" section: the race window between the check and `os.replace` for path-based writes
  (Windows), and the default `hmac` search query hash giving the same value only within one process. No behavior
  changes.
- `neighborhood(index, center, depth=None)` and `WikiRepository.graph(depth=None)` (contract 0.15.0, wiki 1.3.0)
  return every cell connected to the center without a depth limit (the cell count limit, `truncated` and `total` are
  unchanged). The response `WikiGraph.depth` carries the applied depth (null when there is no center or no limit).
  Integer depths behave as before.
- First index speed. Optional `WikiPages` capability `reading()` (a continuous read context): with the fd method,
  `LocalWikiPages` checks the real path of the base folder and walks down to the root once instead of per file, and
  reuses the fd of the same folder. File reads no longer `lstat` first (opening with `O_NOFOLLOW` plus `fstat` gives
  the same rejection). The list received through `read_pages(files=)` is not listed again, and
  `WikiRepository.list_pages`, `view` and `lint` list the folder only once per request (filling in times uses the same
  list). Results and rejection rules are the same.
- `WikiIssueCodes.UNKNOWN_TITLE_SOURCE` and `REDACTED_CONTENT` became aliases of the contract 0.14.11 (`common`
  1.16.0) `KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE` and `WIKI_REDACTED_CONTENT` (values and public names unchanged).
  The event status `WikiEventStatus` is unchanged (`secret_rejected` plus a reason code).
- The markdown link rule also reads reference links (`[text][name]`, `[name][]`, `[name]` plus a definition
  `[name]: path`). They are included in the graph, backlinks and renames (the path in the definition line is fixed
  once). `ParsedLink.reference` (the definition name key) and the internal `scan_inline(text, references)`.
- Unknown values in the syntax `title_sources` report a warning `wiki.unknown_title_source` (`/title_sources/<i>`,
  and `/syntax/...` in rule checks). Previously they were skipped without an issue.
- Blocking rewrites of masked content: when the new content of an existing page newly contains a masked secret
  marker, `compose_write` raises `WikiRedactedContentError` (`wiki.redacted_content`, `details.lines`), and the tool
  returns the same reason code (event status `secret_rejected`). When a read result has masked spots, a notice line
  is added (`tool_text.yaml` `read_redacted`). New public `WikiSecretPolicy.reused_redactions`, `redaction_marks` and
  `WikiIssueCodes` (candidate contract codes).
- `WikiToolkit(query_hash=)`: the default for `query_sha256` in search events changed from unsalted sha256 to
  HMAC-SHA256 with a random salt per bundle (`query_hasher("sha256")` gives the old value, `off` leaves it out).
  `query_hasher`, `query_hasher_from_env`, `QueryHasher`, `QueryHashModes` and `QUERY_HASH_MODES` are re-exports of
  `agent-console-query-hash`.
- Page globs use `agent-console-path-glob`, and the write limit `WriteBudget` uses `agent-console-write-budget`
  (re-exported; `WikiWriteBudget` = `WriteBudgetLike`). Same behavior.

## 0.1.0

- `LocalWikiPages` blocks link swaps (TOCTOU: a folder replaced by a link after the check and before opening). On an
  OS that supports directory fds, it opens each level with `O_NOFOLLOW` while walking down and reads, writes, deletes,
  moves and lists relative to that fd; on Windows it checks again after opening (link and real path plus `fstat`
  identity). New optional argument `within` (the base folder that must contain the root; a root that is a link
  pointing inside it is allowed). When the root itself is a link, listing follows it too (the same as reads and
  writes).
- Agent tool set: `WikiToolkit` (seven tools: search, read (sections), list, links, write (replace, append, section,
  template), move and delete; per-wiki access, `wiki.denied` and `wiki_unavailable`, reason codes, events without
  content, result masking and maximum length, `WriteBudget`), instructions `instructions()` and `wiki_instructions`,
  message data `data/tool_text.yaml` (`WikiToolText`), and the section functions `section_span` and
  `replace_section`.
- Published the write modes: `compose_write`, `PageComposition` and `WIKI_WRITE_MODES` (the `write` tool uses the
  same function), the exception `WikiSectionNotFoundError` (`wiki.not_found`, `reason=section_not_found`; tool reason
  codes are the same as before), and `wiki_failure` and `WikiFailure` (store exceptions to event status and reason
  code).
- SQLite history store: `sqlite.SqliteWikiHistory` (tables `wiki_page_versions` and `wiki_blobs`, shared blobs,
  atomic `record`, `prune` removes orphan blobs, space-wide `changes`), the revision folder of the lineage `wiki`
  `sqlite.MIGRATIONS_DIR` and `BRANCH_NAME` (`wiki_0001`), and the optional dependency `sqlite`.
- Store, rules, checks and history: `merge_rules`, `check_rules`, `load_wiki_rules` and `definition_kinds`, write
  decisions `check_write`, `WikiSecretPolicy` and the wiki write check plugin `WikiWriteCheck`, the check `lint`
  (including a second look at write rules), the template `render_page_template`, the history plugin `WikiHistory`,
  `InMemoryWikiHistory` and `WikiHistoryContractTests`, `WikiRepository` (write, preview, move, delete, revert,
  `scan`), `export_zip` and `import_zip`, `read_pages(cache=)`, `WikiIndex.resolve_page` and `link_views`, eight
  exceptions, and `WikiPageNotFoundError.has_history`.
- Search index plugin: the `WikiSearchIndex` protocol, `ScanSearchIndex`, `sqlite.SqliteFtsSearchIndex` (FTS5
  trigram, with `unicode61` and scan fallbacks plus `degraded`), incremental updates by hash, masked secret fragments
  plus UTF-16 `marks`, the plugin loader `load_search_plugins`, and the contract suite `WikiSearchContractTests`.
- First release: wiki syntax data (package defaults, layer merging, origin, turning off, compiling), page parsing
  (front matter, title sources, tags, aliases, headings, raw link positions, excluding code blocks and inline code),
  the link index (resolution order, case, backlinks, broken links with suggested paths to create, external links,
  schemes, orphans, title collisions), graph neighborhoods, renames that change only link targets, link insertion
  text, building decision subjects, search highlighting, page file access (`WikiPages`, `LocalWikiPages`,
  `read_pages`), and test tools (`MemoryWikiPages`, `WikiPagesContractTests`).
- Contract 0.14.1 follow-up (no code change): the default mode of `WikiSecretPolicy()` reads the contract
  `WikiSettings` default, so `system` is now `reject` as well (stronger security). Suspected secret values in content
  that the app writes on your behalf, such as by a wiki edit node, are rejected.
- Contract 0.14.2 follow-up: merged rule items have `applies_to`, `path` and `title`; `lint()` skips failures of a
  single page (`partial`, `skipped`, issue `wiki.lint_failed`) and reports the enabled check names
  (`enabled_checks`); graph scheme cells have `scheme_target`.

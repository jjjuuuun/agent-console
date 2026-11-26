# agent-console-wiki

The core Agent Console wiki library. It does not know the server, runs, or projects, and handles only **page sources (Markdown files)**,
the contract models (`agent_console_contracts.wiki`), and injected page file access (`WikiPages`).

- **Link syntax is data.** The package default (`data/default_syntax.yaml`: the `[[target|label]]` pattern, relative-path Markdown
  links, front matter roles, title source order, extensions, case, default check severities) → the user setting `wiki.syntax` → the wiki
  rule `syntax` (in the wiki's rule order) override each other in turn. None means "inherit" and an empty list means "none at this layer". First-level object
  values (`front_matter`, `lint`) are overridden per key inside them; everything else is replaced as a whole. The provenance of each value (`default`, `settings`,
  `rules:<id>`) is kept in `EffectiveWikiSyntax.sources`. Turn off the default syntax with `WikiSettings.include_default_syntax:
  false`로 끈다(링크 0개 + `wiki.syntax_missing`).
- **The code knows the meaning of only three things**: front matter roles (`title`, `tags`, `aliases`; which front matter key is data), the default
  checks (`broken_link`, `orphan`, `duplicate_title`; on/off and severity are data), and link target lookup (`path`, `title`,
  `alias`, `relative_path`; order and use are data). Link patterns, front matter keys, folder names, and wiki names are not in the code.
- **Files are the source.** `parse_page` computes front matter, title, tags, aliases, headings, and raw link positions, and `build_index` computes resolution,
  backlinks, broken links (with suggested paths to create), external links, orphans, and title overlaps every time it reads (nothing is stored).
- **Links inside code blocks and inline code are not links.** markdown-it-py handles block structure, and this package reads code
  spans and Markdown link positions inside inline areas directly from the source (see "Dependencies" below).
- **Position units**: code points inside the library, UTF-16 code units in contract views (`WikiLink.start`, `end`, search highlights)
  (the web app can `slice` the received string as is).
- **Renaming rewrites only the link target text** (`rewrite_links`). It does not re-render, so line break style, tabs, and formatting stay
  the same. Links connected by title or alias are not rewritten (they stay connected after the move).
- **Path guarding** (`LocalWikiPages`): rejects `..`, absolute paths, drives, backslashes, control characters, Windows forbidden characters, reserved names, and hidden names
  (starting with `.`); symbolic links and junctions are neither read nor written, and it checks once more that the real path is inside the folder. Writes use a temporary file in the same
  folder + an atomic replace. For the write limitation on operating systems without directory fds, see "Limitations" below.
- **Batched reads** (optional `WikiPages` capability `reading()`): a context for reading many files (value = the same function as `read`). With fds,
  `LocalWikiPages` descends to the root only once and keeps reusing the same folder fd (the per-file checks are the same as `read`). `read_pages`
  uses it when present, which speeds up the first index on slow file systems (network, virtual drives). Implementations without it use `read` as is.

## Dependencies: what / why / alternatives

- **markdown-it-py** (MIT, active, already used by `ac-sdd`): a CommonMark block parser (code blocks, HTML blocks, paragraph boundaries, headings).
  Inline parsing is turned off: inline tokens do not give source positions, and with it on, 2,000 pages (20 MB) take about 10 seconds,
  beyond the 2-second target. For code spans, autolinks, and inline links inside inline areas, only the CommonMark rules needed for link
  positions are applied to the source (reference links `[text][name]` are not read by this step). Alternatives: mistune (weak source positions),
  regexes only (misjudges code blocks), the `mdit-py-plugins` wiki link plugin (fixed patterns that users cannot change).
- **ruamel.yaml**: package default syntax data and page front matter (safe load). Common front matter (`key: value`, `key: [value, value]`)
  is read through a fast path that gives the same result as YAML (plain text only; values that could read as numbers, booleans, or dates go through YAML).
- Internal: `agent-console-contracts` (models, issue codes), `agent-console-safe-regex` (user link patterns, with time and length
  limits), `agent-console-text-template` (link insertion templates and scheme query templates, so the same safe substitution is not kept in two places),
  `agent-console-secret-rules` (masking secrets before indexing), `agent-console-registry` (search index plugin loader),
  `agent-console-store` (path checks `check_content_path` and atomic writes, the same naming rules as definition bodies),
  `agent-console-conditions` (conditions of write and check rules), `agent-console-secret-rules` (body secret checks),
  `agent-console-safe-zip` (zip import safety rules, shared with memory).

## Installation

```bash
pip install agent-console-wiki
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-wiki
```

## Minimal usage (folder → backlinks, without the server)

```python
>>> import tempfile
>>> from agent_console_wiki import (
...     LocalWikiPages, build_index, compile_syntax, effective_syntax, neighborhood, read_pages,
... )

>>> folder = tempfile.mkdtemp()
>>> pages = LocalWikiPages(folder)
>>> pages.write("start.md", "# 시작\n\n[[guide|안내]]와 [메모](notes/one.md)를 보세요.\n".encode())
>>> pages.write("guide.md", "---\ntitle: 안내서\n---\n처음으로: [[start]]. 코드 안 `[[가짜]]`는 링크가 아니다.\n".encode())
>>> pages.write("notes/one.md", "[[없는 페이지]]\n".encode())

>>> syntax = compile_syntax(effective_syntax())     # the package default syntax (can be turned off)
>>> parsed, issues = read_pages(pages, syntax)
>>> index = build_index(parsed, syntax, home="start")
>>> [(b.path, b.title) for b in index.backlinks("start")]
[('guide', '안내서')]
>>> [(link.raw, link.status, link.resolved) for link in index.page_links("start")]
[('[[guide|안내]]', 'ok', 'guide'), ('[메모](notes/one.md)', 'ok', 'notes/one')]
>>> [(link.status, link.suggested_path) for link in index.page_links("notes/one")]
[('broken', '없는 페이지')]
>>> sorted(index.orphans)
[]
>>> [(n.path, n.depth) for n in neighborhood(index, "start", 1).nodes]
[('start', 0), ('guide', 1), ('notes/one', 1)]

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

Changing the syntax: pass user settings (`WikiSettings`) and wiki rule syntaxes to `effective_syntax(settings, rules=[(rule id, syntax)])`,
or give the layers directly with `merge_syntax(("default", ...), ("settings", {...}))`. For example, with
`{"links": [{"id": "paren", "kind": "pattern", "pattern": "\\(\\((?P<target>[^)]+)\\)\\)", "resolve": ["path"]}]}`
`((target))` is a link. The pattern must have a `target` group; `label` and `anchor` groups are optional.

Markdown link rules (`kind: markdown`) read both inline links `[text](path.md)` and reference links (`[text][name]`, `[name][]`, `[name]` +
a definition `[name]: path.md`). A reference link is a link only when its name has a definition (names are compared by CommonMark rules), and the target
position is the path on the definition line. Text inside code blocks and inline code, and images (`![image][name]`), are not links.

Renaming: `rewrite_links(text, index.links[page], page=page, old="guide", new="docs/guide", syntax=syntax)`
rewrites only the link targets in that page's body (when `page == old`, the moved page's own relative links are rewritten relative to the new location).
Reference links are fixed on the definition line, and a definition used by several links is fixed only once.
Inserting links: `render_link_text(syntax, from_page=..., target=..., label=...)` (the rule's `insert` template; without one,
`WikiLinkInsertUnavailableError`). Search highlights: `search_marks(snippet, query)` (UTF-16 ranges).
Judged values (what write and check rule conditions read): `index.facts(path)`, `write_subject`, `lint_subject`; the shapes match the contract
`WIKI_WRITE_SUBJECT_PATHS` and `WIKI_LINT_SUBJECT_PATHS`.

Issues are `WikiIssue` (page `page`, line `line`, rule `rule_id`, no raw values): `wiki.front_matter_invalid`,
`parse_timeout`·`link_pattern_invalid`·`unknown_link_kind`·`unknown_title_source`·`syntax_missing`·
`duplicate_rule_id`, `invalid_glob`, `home_missing`, `too_many_pages`, `too_large`. The code values are the contract `KnownIssueCodes`,
and `WikiIssueCodes` (`UNKNOWN_TITLE_SOURCE`, `REDACTED_CONTENT`) are aliases of them. Errors are `WikiError.code` (`wiki.invalid_path`,
`page_not_found`·`page_exists`·`link_insert_unavailable`).

Test tools in `agent_console_wiki.testing`: `MemoryWikiPages` (in-memory page files), `WikiPagesContractTests`
(a contract suite that tests your own `WikiPages` implementation for the same semantics; needs pytest).

## Search index

The index is a **rebuildable cache** (page files are the truth). The protocol `WikiSearchIndex` (`update`, `remove`,
`rebuild`, `search`, `hashes`) has two implementations: `ScanSearchIndex` (scans in memory, `scan`) and, in the submodule
`agent_console_wiki.sqlite`, `SqliteFtsSearchIndex(path, tokenizer="trigram")` (`sqlite-fts`, standard `sqlite3`
FTS5). The caller gives the index file location (this package does not fix it). Every word of the query must appear as a substring in the path, title, tags,
aliases, or body (substring matching, which works for Korean). Snippets are cut from **the body with secrets masked** (omitted `redact`
= the `ac-secret-rules` default rules), and `marks` are UTF-16 ranges relative to the snippet. SQLite without FTS5 or trigram
falls back to `unicode61` (prefix matching) → `scan`, with `degraded=True` (the server reports it as a `wiki.search_degraded` issue).
If the file is broken or the settings differ when it is opened, it is discarded and rebuilt. Plugins use the entry point
`agent_console.wiki_search_indexes`(`load_search_plugins`).

```python
>>> from agent_console_wiki import (
...     LocalWikiPages, ScanSearchIndex, compile_syntax, effective_syntax, parse_page,
...     search_document, sync_search_index,
... )
>>> import tempfile
>>> pages = LocalWikiPages(tempfile.mkdtemp())
>>> pages.write("a.md", "---\ntitle: 소개\n---\n이 위키는 팀의 약속을 적는다.\n".encode())
>>> syntax = compile_syntax(effective_syntax())
>>> text = pages.read("a.md").decode()
>>> doc = search_document(parse_page("a", text, syntax), text)
>>> index = ScanSearchIndex()            # without a file. File index: SqliteFtsSearchIndex(path)
>>> sync_search_index(index, [doc]).updated   # writes only what changed (hashes)
1
>>> hit = index.search("위키").items[0]
>>> (hit.path, hit.snippet, [(m.start, m.end) for m in hit.marks])
('a', '이 위키는 팀의 약속을 적는다.', [(2, 4)])

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

Tests: `WikiSearchContractTests` (fill in only `make_index` to test your own index for the same semantics), `make_search_document`.

## Store, rules, checks, history

- **Merging rules** `merge_rules(the wiki's rules, documents)`: instruction bodies are concatenated in order (the rule name header template =
  package data `data/rules_text.yaml`), and write rules, check rules, and page templates are concatenated (for the same id, the first one wins +
  `wiki.duplicate_rule_id`; missing rules give `wiki.rules_missing`). Each entry keeps its source rule id (`entries`). Reading from the definition store is
  `load_wiki_rules(store, ids, kind=)`, and the definition kinds are `definition_kinds(wiki_kind=, wiki_dir=, ...)` (names and
  folders are caller data). The pre-save check is `check_rules` (regexes, globs, conditions, unknown actions, always-reject rules, template files, template variables).
- **Write decisions** `check_write`: `applies_to` globs → `when` → `require` and `deny_patterns` (matching line numbers) → `reject`
  /`warn` (unknown values = warn + `wiki.unknown_action`). The secret check `WikiSecretPolicy` (off, warn, or
  reject per author kind, defaults = the contract `WikiSettings`), additional checks `WikiWriteCheck`.
- **Checks** `lint`: the three default checks (severity and on/off are syntax data) + check rules + rechecking write rules (`wiki.rule_violation`,
  turned off with `lint.write_rules: false`).
- **History** `WikiHistory` (`record`, `list`, `get`, `read`, `latest`, `summaries`, `changes`, `prune`),
  `InMemoryWikiHistory`, the contract suite `testing.WikiHistoryContractTests` (the SQLite implementation `sqlite.SqliteWikiHistory` is below).
- **Store** `WikiRepository`: write (`if_hash`, new pages only, size and count limits), preview (files, history, and index unchanged),
  move (rewrites only the link strings of backlinks; pages changed in the meantime go to `conflicts`), delete, revert, external change `scan`
  (`external`, `import`; the same hash is not recorded again), checks, graph, link insertion, template rendering.
- **Freshness window** `WikiRepository(freshness_seconds=)` (default `0` = list the page folder on every read): above 0 the repository keeps
  one snapshot (page listing, link index, history summaries) until the window has passed since the last check (`clock` decides; a clock that
  goes back counts as expired). Its own writes, deletes, moves, restores, imports, and `scan()` drop the snapshot at once, and write decisions
  always use the current files. Files changed by another editor can show up to the window late; `invalidate()` drops the snapshot, and
  `page_files()` returns the listing the snapshot uses (for cache keys).
- **zip** `export_zip`, `import_zip` (no extraction to disk; only entries with path attacks are rejected; archive limits write nothing;
  `ac-safe-zip`, the same rules as memory import).

```python
>>> from agent_console_contracts.wiki import WikiAuthor, WikiRulesDefinition
>>> from agent_console_wiki import (
...     InMemoryWikiHistory, RulesDocument, WikiRepository, WikiRuleRejectedError, merge_rules,
... )
>>> from agent_console_wiki.testing import FakeClock, MemoryWikiPages

>>> rules = merge_rules(["r"], [RulesDocument("r", WikiRulesDefinition.model_validate({
...     "kind": "wiki-rules", "id": "r", "name": "메모 금지",
...     "write_rules": [{"id": "no-temp", "deny_patterns": ["TODO"], "message": "임시 메모 금지"}],
... }))])
>>> repo = WikiRepository(
...     MemoryWikiPages(), wiki_id="notes", syntax=compile_syntax(effective_syntax()),
...     rules=rules, history=InMemoryWikiHistory(), clock=FakeClock(),
... )
>>> _ = repo.write("start", "# 시작\n[[guide]]\n")
>>> _ = repo.write("guide", "# 안내\n", author=WikiAuthor(kind="agent", agent_id="w", label="정리꾼"))
>>> try:
...     repo.write("draft", "첫 줄\nTODO 나중에\n")
... except WikiRuleRejectedError as exc:
...     print(exc.details["rule_id"], exc.details["lines"])
no-temp [2]
>>> result = repo.move("guide", "docs/guide")
>>> [(r.path, r.count) for r in result.rewritten], repo.read("start").text
([('start', 1)], '# 시작\n[[docs/guide]]\n')
>>> [(v.op, v.author.label) for v in repo.page_history("docs/guide").items]
[('move_in', None)]

>>> clock = FakeClock(step=0.0)
>>> pages = MemoryWikiPages({"a.md": "# A\n"})
>>> fresh = WikiRepository(
...     pages, wiki_id="n", syntax=compile_syntax(effective_syntax()), clock=clock,
...     freshness_seconds=5,
... )
>>> [p.path for p in fresh.list_pages().items]
['a']
>>> pages.write("b.md", b"# B\n")  # another editor, inside the window
>>> [p.path for p in fresh.list_pages().items]
['a']
>>> clock.advance(5)
>>> [p.path for p in fresh.list_pages().items]
['a', 'b']

```

## SQLite history store

`agent_console_wiki.sqlite.SqliteWikiHistory(path)` is the SQLite implementation of `WikiHistory` (SQLAlchemy Core, passes the same
contract suite). The tables are `wiki_page_versions` (one row per version, no body) and `wiki_blobs` (one body row per hash), and
they are created with `create_all` when opened (standalone use). The server brings the same shape up through a migration lineage: the server module wraps
the folder `sqlite.MIGRATIONS_DIR` and the name `sqlite.BRANCH_NAME` (`wiki`, version table `alembic_version_wiki`).

```python
>>> from agent_console_contracts.wiki import WikiAuthor
>>> from agent_console_wiki import HistoryEntry
>>> from agent_console_wiki.sqlite import BRANCH_NAME, SqliteWikiHistory
>>> history = SqliteWikiHistory(":memory:")     # a path for a file
>>> me = WikiAuthor(kind="user")
>>> _ = history.record([HistoryEntry.of("notes", "a", "create", b"v1", author=me, at=1.0)])
>>> _ = history.record([HistoryEntry.of("notes", "a", "update", b"v2", author=me, at=2.0)])
>>> [c.op for c in history.changes("notes").items], BRANCH_NAME
(['update', 'create'], 'wiki')
>>> history.close()

```

## Agent tool set

`WikiToolkit(wikis, access=, author=, text=, on_event=, write_budget=, query_hash=)` is a tool set that does not know the runtime (the same shape as the memory
`MemoryToolkit`). `specs()` returns tools only for the operations the access settings allow.

- **7 tools**: `search(query, wiki?, prefix?, tags?, limit?)`, `read(path, wiki?, section?)`, `list(prefix?, wiki?,
  limit?)`·`links(path, wiki?)`·`write(path, content?, wiki?, mode: replace|append|section, section?, template?,
  title?, if_hash?, message?)`·`move(path, to, wiki?, rewrite_links?, if_hash?, message?)`·`delete(path, wiki?,
  if_hash?, message?)`. Parameter names are contract vocabulary; the names, descriptions, result header line, and maximum characters the model sees are the access
  settings (`WikiAccessConfig`, defaults = the contract schema defaults); parameter descriptions, result lines, and failure text are `data/tool_text.yaml`
  (replace with `text=WikiToolText.from_mapping(...)`).
- **Choosing a wiki**: `wikis` is the wikis of this run space (a mapping or a function). If a wiki is not in the access settings or the operation is not allowed,
  `wiki.denied`; if it is in the settings but not in `wikis`, `wiki.wiki_unavailable` (`unavailable()` gives the list).
- **Writes**: for append, section, and template, the toolkit builds the new body from the current body and writes with `write(if_hash=current hash)`
  (`wiki.conflict` if it changed in the meantime). template is for new pages only, and `content`, if given, is appended to the end of the template body. section
  keeps the heading line and replaces only that section's body.
- **Failures** are not exceptions but `is_error` + reason codes: `wiki.denied`, `wiki_unavailable`, `page_not_found`, `not_found`
  (section), `template_missing`, `conflict`, `page_exists`, `too_large`, `secret_rejected`, `rule_rejected` (rule id, message,
  line), `rate_limited`, `invalid_path`, `validation_failed` (input format), `redacted_content` (below).
- **Results** are masked with `repository.secrets.redact` and then cut at `max_result_chars`. If the body read has masked places, a notice line (text `read_redacted`; not added when empty)
  is put at the very start of the result. Writing a masked body back as is would replace real secrets with mask
  markers, so a write to an existing page whose new body contains more mask markers than the source is blocked with `wiki.redacted_content`
  (event status `secret_rejected`, line numbers only, no values) (decided by `compose_write`; the `wiki-update` node does the same).
  Writes that delete masked lines, edits to other sections, and new pages are not blocked. **Events** (`on_event(type,
  WikiEventPayload)`, type `wiki.<op>`) contain no body or raw query (only sizes and hashes).
- **Query hash** (`query_sha256`): `query_hash=query_hasher(mode, salt=)` (the shared `agent-console-query-hash`, re-exported,
  the same rules as the memory tool set). The default is a salted HMAC-SHA256 (random when the tool set is created if no salt is given,
  so even short queries are hard to recover with a dictionary attack); `sha256` is the unsalted value; `off` attaches no hash (only the character count).
  If you need the same value across runs, create one hasher and pass it to several tool sets.
- **Write limit**: `write_budget` (`take() -> bool`, default implementation `WriteBudget(limit)`, re-exported from `agent-console-write-budget`,
  the same object as the memory tool set) is used once by each write, move, and delete. Create one per run and share it among
  several tool sets.
- **Instructions**: `instructions()` (= `wiki_instructions(access, targets)`) builds the text to put into `ToolProvision.instructions`:
  the merged rule instructions per wiki (`include_rules_instructions`) and the path hint (`path_hint`, filled from `WikiToolTarget.name` and
  `pages_dir`; no hint when the template uses `pages_dir` but there is none). The same text appears once.

```python
>>> import asyncio
>>> from agent_console_contracts.wiki import WikiAccessConfig, WikiAuthor
>>> from agent_console_wiki import WikiToolkit, WikiToolTarget, WriteBudget

>>> access = WikiAccessConfig.model_validate(
...     {"wikis": [{"wiki": "notes", "access": ["read", "search", "write"]}]}
... )
>>> kit = WikiToolkit(
...     {"notes": WikiToolTarget(repo, name="노트", pages_dir="wiki/notes")},
...     access=access,
...     author=WikiAuthor(kind="agent", agent_id="keeper", label="위키 관리"),
...     write_budget=WriteBudget(10),
... )
>>> [spec.op for spec in kit.specs()]
['read', 'search', 'write']
>>> out = asyncio.run(kit.call("write", {"path": "log", "content": "첫 기록", "mode": "append"}))
>>> out.is_error, out.event.op, out.event.bytes
(False, 'write', 10)
>>> bad = asyncio.run(kit.call("write", {"path": "log", "content": "TODO", "mode": "append"}))
>>> bad.code, bad.event.rule_ids
('wiki.rule_rejected', ['no-temp'])
>>> asyncio.run(kit.call("delete", {"path": "log"})).code
'wiki.denied'
>>> kit.instructions()[-1].startswith("위키 페이지 파일은 wiki/notes/")
True

```

The same write method is used outside tools too (for example, nodes that edit pages without an LLM). `compose_write(repo, path, content=,
mode=, section=, template=, title=, if_hash=)`는 새 본문과 `write` 조건(`PageComposition{content, create_only,
if_hash}`)만 만들고 쓰지 않는다(절이 없으면 `WikiSectionNotFoundError` — 코드 `wiki.not_found`, `details.reason =
section_not_found`). `wiki_failure(exc)`는 저장소 예외를 도구와 같은 이벤트 상태·사유 코드(`WikiFailure{status,
code, reason, rule_ids}`).

```python
>>> from agent_console_wiki import WikiPageExistsError, compose_write, wiki_failure
>>> plan = compose_write(repo, "log", content="둘째 기록", mode="append")
>>> plan.content, plan.create_only, plan.if_hash == repo.current("log").content_hash
('첫 기록\n둘째 기록', False, True)
>>> wiki_failure(WikiPageExistsError("log")).status
'conflict'

```

With the Claude Agent SDK, wrap each spec with `@tool` and put it into an in-process MCP server (this package does not know the SDK):

```text
from claude_agent_sdk import create_sdk_mcp_server, tool

def sdk_tools(kit):
    out = []
    for spec in kit.specs():
        @tool(spec.name, spec.description, dict(spec.input_schema))
        async def handler(args, _spec=spec):
            result = await _spec.call(args, None)
            return {"content": [{"type": "text", "text": result.text}], "is_error": result.is_error}
        out.append(handler)
    return create_sdk_mcp_server(name="wiki", tools=out)
```

## Limitations

- **Race window for path-based (Windows) writes**: on operating systems without directory fds (`openat`), `LocalWikiPages` writes
  by path. It rechecks the path (links, junctions, outside the folder) after creating the temporary file and right before replacing, but if another process swaps an intermediate folder
  for a link or junction in the narrow window between the last check and `os.replace`, it can write outside the wiki folder. This window
  cannot be closed structurally (the file system path is looked up by name again). The directory fd method (Linux, macOS) replaces relative to the open folder fd,
  so it has no such window. Reads check after opening that the open file is the file at that path, so they never return content from outside the folder.
  If the wiki folder is somewhere other users and processes cannot modify, this window is useless to an attacker.
- **Query hashes are the same only within a process by default**: the default `hmac` uses a random salt created with the tool set when no salt is given,
  so after a server restart the same query gets a different `query_sha256`. To compare across restarts, the caller
  injects a salt (the server uses the salt environment variable from the server administrator settings) or chooses `sha256` (in which case short queries can be recovered with a dictionary attack).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
AGENT_CONSOLE_PERF=strict uv run pytest tests/test_agent_console_wiki_perf.py tests/test_agent_console_wiki_search_perf.py   # including wall-clock thresholds
```

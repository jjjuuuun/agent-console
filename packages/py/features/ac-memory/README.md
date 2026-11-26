# agent-console-memory

The **core library of the shared memory** that agents read and write while running.
It holds the store protocol and an in-memory implementation, scope kinds, access decisions, the agent tool set, and secret checks.
It does not know the execution engine, agent nodes, or log packages (import-linter blocks them). So you can use it as is without the Agent Console server,
in other agent frameworks (direct SDK use, MCP servers).

- **Store**: the `MemoryStore` protocol and `InMemoryMemoryStore`. `DeferredMemoryStore(open_store, exists=)` answers reads with an empty memory
  when the store does not exist and opens it on the first `write` (viewing alone never creates a file).
  - Every write raises the version and leaves a history entry.
  - `if_version` reports conflicts.
  - Writes to the same entry are queued.
  - Deleting only marks the entry; a full delete (`purge`) removes its versions too.
  - The SQLite implementation is the submodule `sqlite` (`open_sqlite_memory_store`, see "SQLite store" below). A new implementation inherits `testing.contract.MemoryStoreContractTests` to check that it has the same semantics.
- **Scope kinds**: what each scope is called and how its scope id is determined are data.
  - The package default data is `data/default_scope_kinds.yaml` (3 kinds).
  - User settings can turn them off (`include_default_scope_kinds: false`), change them, or add to them.
  - Scope ids are computed from a `{/pointer}` template over the access context. The contract `MemoryAccessContext` defines the context fields.
  - If the template resolves to an empty value, that scope cannot be used in that run (`memory.scope_unavailable`).
  - Scopes that need computation are added with plugins in the entry point `agent_console.memory_scope_kinds`.
- **Access**: `allowed(config, op, scope_kind)`. The access settings of the `memory` resource (`MemoryAccessConfig`) decide the allowed operations per scope kind (read, search, write, delete).
- **Tool set**: `MemoryToolkit(...).specs()` returns tools only for allowed operations.
  - Tool names, descriptions, and the result header line are access settings data.
  - Parameter descriptions and result text are `data/tool_text.yaml` and can be replaced with `text=`.
  - Failures are not exceptions but `is_error` results with reason codes (`memory.denied`, `not_found`, `conflict`, `too_large`, `secret_rejected`, `rate_limited`, `scope_unavailable`, `invalid_key`).
  - Every call emits an event `memory.<op>`. The payload (`MemoryEventPayload`) **does not contain the body or the raw query**. It carries only sizes and hashes.
    The query hash (`query_sha256`) is set with `MemoryToolkit(query_hash=query_hasher(mode, salt=))` (the hasher is the shared `agent-console-query-hash`, re-exported, the same as the wiki). The default is a salted HMAC-SHA256
    (random when the hasher is created if no salt is given, so even short queries are hard to recover with a dictionary attack); `sha256` is the old unsalted value,
    and `off` attaches no hash.
- **Secret checks (injected)**: every write checks the key, tags, and body with a `SecretScanner`.
  - The default judge is the default rules of `ac-secret-rules`, and the default mode is `reject`.
  - `redact` masks the body and tags and saves. If a suspected value appears in the key, the write is rejected regardless of the mode.
  - Rejection errors carry only the field and the rule id, never the value found.

> The tool result header line (access settings data) only reduces prompt injection and **is not a security boundary**. Narrow write permissions with the access settings.

## Installation

```bash
pip install agent-console-memory            # store protocol, in-memory implementation, scope kinds, tool set, cleanup, export
pip install "agent-console-memory[sqlite]"  # + the submodule `sqlite` (SQLite store) and the scale measurement tools in `testing`
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> "agent-console-memory[sqlite]"
```

Dependencies: `agent-console-contracts` (models), `agent-console-conditions` (JSON pointers in templates), `agent-console-secret-rules` (default secret judgement), `agent-console-registry` (loaders), `agent-console-safe-zip` (zip import safety rules, shared with wiki import), `ruamel-yaml` (reading package default data). Extra `sqlite`: `sqlalchemy` (table definitions and queries of the submodule `sqlite`). The top-level `agent_console_memory` imports without sqlalchemy. Consumers that use the SQLite store (for example the server module) depend on `agent-console-memory[sqlite]`.
- `ruamel-yaml`. What: reads YAML. Why: the repository's standard YAML library (the same as definition storage). Alternative: JSON data files (no comments).
- `sqlalchemy`. What: SQLite table definitions (`MetaData`) and Core queries. Why: server migrations (Alembic) can compare against the same table definitions, and it is the repository's standard access method. Alternative: the standard `sqlite3` directly (no dependency, but table definitions for migration comparison would have to be kept separately).

## Minimal usage

Write and read with only the store, scope kinds, and tool set, without the server. The scope kind names are example data.

```python
>>> import asyncio
>>> from agent_console_contracts.memory import MemoryAccessConfig, MemoryAccessContext
>>> from agent_console_memory import InMemoryMemoryStore, MemoryToolkit, merge_scope_kinds

>>> catalog = merge_scope_kinds(
...     include_defaults=False,
...     user={"notes": {"label": "노트", "id": "{/graph_id}"}},
... )
>>> access = MemoryAccessConfig.model_validate(
...     {"scopes": [{"kind": "notes", "access": ["read", "search", "write"]}]}
... )
>>> events = []
>>> kit = MemoryToolkit(
...     InMemoryMemoryStore(),
...     access=access,
...     context=MemoryAccessContext(graph_id="team-1", agent_id="planner", run_id="r1"),
...     catalog=catalog,
...     on_event=lambda event_type, payload: events.append((event_type, payload)),
... )
>>> [spec.name for spec in kit.specs()]
['memory_read', 'memory_search', 'memory_write']

>>> write = next(spec for spec in kit.specs() if spec.op == "write")
>>> asyncio.run(write.call({"key": "결정/api-버전", "content": "v2로 고정"}, "tool-1")).text
'노트:결정/api-버전에 v1로 썼습니다.'

>>> read = asyncio.run(kit.call("read", {"key": "결정/api-버전"}))
>>> read.text.splitlines()[1]
'v2로 고정'

>>> denied = asyncio.run(kit.call("write", {"key": "x", "content": "y", "scope": "other"}))
>>> denied.is_error, denied.code
(True, 'memory.denied')

>>> [(t, p.status, p.version) for t, p in events]
[('memory.write', 'ok', 1), ('memory.read', 'ok', 1), ('memory.write', 'denied', None)]

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

### Using only the store

```python
>>> from agent_console_contracts.memory import MemoryAuthor, MemoryScopeRef
>>> from agent_console_memory import MemoryQuery, VersionConflictError

>>> store = InMemoryMemoryStore()
>>> scope = MemoryScopeRef(kind="notes", id="team-1")
>>> me = MemoryAuthor(kind="user")
>>> entry = store.write(scope, "회의/10-28", "첫 기록", author=me, tags=["회의"]).entry
>>> store.write(scope, "회의/10-28", "고친 기록", author=me, if_version=1).entry.version
2
>>> try:
...     store.write(scope, "회의/10-28", "늦은 기록", author=me, if_version=1)
... except VersionConflictError as exc:
...     print(exc.code, exc.current_version)
memory.conflict 2
>>> [(v.version, v.op) for v in store.history(entry.id)]
[(1, 'create'), (2, 'update')]
>>> store.search(MemoryQuery(text="고친")).total
1

```

### SQLite store

It needs the extra `sqlite`. It keeps the same `MemoryStore` semantics in one file (`BEGIN IMMEDIATE` writes, per-entry version history, FTS5 trigram full-text search).
If the query is shorter than 3 characters or this SQLite has no FTS5, it falls back to substring search (`LIKE` style), and in the latter case
`store.warnings()` returns a `memory.search_fallback` warning.

```python
>>> from agent_console_memory.sqlite import open_sqlite_memory_store
>>> db = open_sqlite_memory_store(":memory:")   # with a file path, that file (parent folders are created)
>>> db.write(scope, "회의/10-28", "SQLite에 쓴 기록", author=me).entry.version
1
>>> db.search(MemoryQuery(text="기록")).total
1
>>> db.close()

```

### Cleanup rules

Cleanup rules are user data (`MemoryRetentionRule`: id, condition `when`, action `archive`|`delete`). **There are no package default rules.** With no rules, the plan has 0 items.

- Judged fields: `scope{kind, id}`, `key`, `tags`, `pinned`, `archived`, `bytes`, `version`, `age_days`, `idle_days`, `last_read_days` (only when it was read by a tool), `author_kind`, `created_by`, `updated_by` (`RETENTION_SUBJECT_FIELDS`).
- Pinned entries are never cleaned up (when a rule matches, they are only counted in the plan's `excluded_pinned`). Only the first rule in declaration order is used.
- Plan items carry the `updated_at` and `bytes` at the time of judgement (the screen does not reload the list). The contract's path suggestions `MEMORY_RETENTION_SUBJECT_PATHS` (rule schema `examples`) are kept in sync with `RETENTION_SUBJECT_FIELDS` (a test catches drift).
- Conditions are judged through the compiled path of `ac-conditions`. Rule validation is `retention_issues` (reusing `condition_issues`; an empty condition is an error for cleanup).
- Applying (`apply_retention`) changes entries only at the version from planning time, and leaves a version (author `system`, `label` = rule id) so the change can be reverted.
- Planning and export scan entries with `iter_entries`. If the store has the optional capability `EntryScanner` (`scan_entries`), bodies are read in one pass; otherwise entries are read page by page through `search`. Large store implementations are faster with `scan_entries`.
- Cleanup plans do not look at bodies, so they scan with `iter_entries(..., with_content=False)`. If the store has the optional capability `HeadScanner` (`scan_heads`, lightweight heads `EntryHead` without bodies), that is used first (the SQLite implementation neither reads the body column nor builds contract models).

```python
>>> from agent_console_conditions import builtin_operators
>>> from agent_console_contracts.memory import MemoryAuthor, MemoryScopeRef
>>> from agent_console_memory import InMemoryMemoryStore, apply_retention, retention_plan
>>> from agent_console_memory.testing import FakeClock

>>> operators = {op.descriptor.id: op for op in builtin_operators()}
>>> clock = FakeClock(0.0)
>>> board = MemoryScopeRef(kind="board", id="")
>>> store = InMemoryMemoryStore(clock=clock)
>>> _ = store.write(board, "임시/메모", "곧 버릴 기록", author=MemoryAuthor(kind="user"), tags=["임시"])
>>> clock.advance(31 * 86_400)
>>> retention_plan(store, [], now=clock(), operators=operators).count
0
>>> rule = {"id": "stale-temp", "action": "archive", "when": {"all": [
...     {"path": "/tags", "op": "contains", "value": "임시"},
...     {"path": "/idle_days", "op": "gte", "value": 30}]}}
>>> plan = retention_plan(store, [rule], now=clock(), operators=operators)
>>> [(item.key, item.rule, item.action) for item in plan.items]
[('임시/메모', 'stale-temp', 'archive')]
>>> apply_retention(store, plan).archived
1
>>> store.find(board, "임시/메모").updated_by.label
'stale-temp'

```

### Export and import (Markdown zip)

One zip entry is one memory entry. The path is `<scope kind>/<scope id>/<key>.md` (an empty scope id is `_`, and scope ids are percent-encoded), and a YAML header (id, tags, pinned, archived, version, author) is put before the body.

- Import reads the location from the path and uses only tags, pinned, archived, and body format from the header. It creates entries with new ids at version 1.
- When the same scope and key exist, it follows the policy `skip`, `overwrite` (a new version), or `rename` (a new key `"{key} ({n})"`). With `dry_run=True`, it writes nothing and counts the same numbers.
- Safety: files are never extracted to disk.
  - The whole archive is rejected (`TooLargeError`) for: compressed size, entry count, and the decompressed size limits for one entry and in total (`MemoryTransferLimits`, zip bombs).
  - Only that file is refused (`errors`) for: `..`, absolute paths, backslashes, drive letters, symbolic links.
  - Writes go through the store policy as is (key rules, secret checks, size), and problem lists carry no bodies or secret values.

```python
>>> from agent_console_memory import export_markdown, import_markdown

>>> data = export_markdown(store)
>>> copy = InMemoryMemoryStore()
>>> result = import_markdown(copy, data)
>>> result.created, result.errors
(1, [])
>>> import_markdown(copy, data, policy="rename", dry_run=True).renamed
1
>>> copy.find(board, "임시/메모").archived
True

```

### Wrapping as Claude Agent SDK tools (documentation example, not run)

A tool spec is a name, description, input schema, and async call, so it maps directly to an SDK in-process tool.

```text
from claude_agent_sdk import create_sdk_mcp_server, tool

def to_sdk_tool(spec):
    @tool(spec.name, spec.description, dict(spec.input_schema))
    async def handler(args):
        out = await spec.call(args, None)
        return {"content": [{"type": "text", "text": out.text}], "is_error": out.is_error}
    return handler

server = create_sdk_mcp_server("memory", tools=[to_sdk_tool(s) for s in kit.specs()])
```

## Extension points

| What | How |
| --- | --- |
| Scope kinds | Data: `merge_scope_kinds(user={id: {label, description, id template}})` (replaced as a whole per id, null = off). Computed: entry point `agent_console.memory_scope_kinds` = a function without arguments → a list of `MemoryScopeKind` (`resolver=`) or `{id: data}`. `load_scope_kind_plugins(new_scope_kind_registry())` → `plugin_scope_kinds(registry)` → `merge_scope_kinds(plugins=...)` |
| Store | Inject an implementation of the `MemoryStore` protocol. Call `prepare_write(policy, ...)` before writing and check the same semantics with `testing.contract.MemoryStoreContractTests` |
| Secret judgement | `MemorySecretGuard(scanner=<SecretScanner implementation>, mode="reject"\|"redact")`. User rules: `SecretRulesScanner(rules=default_rules().with_extra(...))` |
| Tool text | `MemoryToolkit(text=ToolText.from_mapping(...))` |

## Built in-house (what / why / alternatives)

- What: the store, versions, scope computation, and the tool set.
- What: running cleanup rules (plan and apply) and the Markdown zip format. Condition judgement uses `ac-conditions`, and zip and YAML use the standard `zipfile` and `ruamel-yaml` (no new dependencies). Alternatives: cleanup directly in SQL, which is impossible because conditions are user data (with operator extensions); a single JSON file as the export format, which is hard for people to read and keep in git.
- Why: it needs explicit per-key records, versions, authors (run, node), and scope isolation. People edit this model, so it must be deterministic without LLM extraction.
- Alternatives: mem0 (needs LLM extraction and a vector store), the MCP memory server (no scopes or versions).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

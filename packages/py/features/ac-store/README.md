# agent-console-store

Store interfaces and implementations. Definitions are YAML files (the source of truth); version history, Runs, and event records are SQLite; plus in-memory versions for tests.
It depends only on `agent-console-contracts`, `agent-console-numbered-id`, and `agent-console-settings` (document comparison for version comparison); it knows neither the runtime nor the server.

## Installation

Inside the workspace:

```bash
uv sync --all-packages
```

Standalone install (from another project):

```bash
uv pip install ./packages/py/features/ac-store
```

## Dependencies: what / why / alternatives

| Dependency | Why | Alternatives |
| --- | --- | --- |
| `sqlalchemy>=2` (Core) | Writes event and Run records to SQLite while keeping it easy to switch databases or swap in a test implementation. Uses only Core, no ORM. | The standard `sqlite3` directly (the agent_bench approach; fewer dependencies but weak schema history and portability) |
| `alembic>=1.13` | Schema change history and rollback (reversible migrations). Applied from code (`upgrade(engine)`). | `metadata.create_all` (no history or rollback), a hand-made version table |
| `ruamel.yaml>=0.18` | Keeps comments and key order of hand-edited YAML after saving (round trip). | PyYAML (loses comments), JSON files (awkward for people to edit) |

## Minimal usage

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Run, RunEvent
>>> from agent_console_store import FileDefinitionStore, VersionConflict, open_sqlite

>>> tmp = tempfile.TemporaryDirectory()
>>> data = Path(tmp.name)  # in real use, the data and workspace paths from the settings
>>> db = open_sqlite(data / "console.sqlite3")  # migrations are applied too
>>> defs = FileDefinitionStore(data / "workspace", versions=db.versions)

>>> created = defs.create("graph", {"id": "main", "name": "메인"})
>>> saved = defs.save(  # saving needs If-Match (the expected version)
...     "graph", {"id": "main", "name": "새 이름"}, expected_version=created.version_hash
... )
>>> try:
...     defs.save("graph", {"id": "main", "name": "x"}, expected_version=created.version_hash)
... except VersionConflict as exc:  # .details = VersionConflictDetails
...     print(exc.details.current_version_hash == saved.version_hash)
True
>>> defs.get("graph", "main").document
{'id': 'main', 'name': '새 이름'}
>>> defs.get_version("graph", "main", created.version_hash).content  # a past version
{'id': 'main', 'name': '메인'}

>>> db.runs.save(
...     Run(
...         id="r1",
...         graph_id="main",
...         graph_version=saved.version_hash,
...         status="running",
...         input={},
...         origin="api",
...         created_at=0.0,
...     )
... )
>>> def event(seq):
...     return RunEvent.model_validate(
...         {
...             "event_id": f"e{seq}",
...             "run_id": "r1",
...             "seq": seq,
...             "ts": 0.0,
...             "node_path": [],
...             "type": "agent.text_delta",
...             "payload": {"text": "안녕"},
...         }
...     )
>>> [db.events.append(event(seq)) for seq in (1, 2, 2)]  # reloading the same event_id is ignored (idempotent)
[True, True, False]
>>> [e.seq for e in db.events.list("r1", since_seq=1)]  # increments after reconnecting
[2]
>>> db.close()
>>> tmp.cleanup()

```

For tests and temporary runs, use `InMemoryDefinitionStore()` and `InMemoryStorage()` (same interfaces, same rules).

The SQLite `routing_decisions` table exists for compatibility with existing databases. No code writes to it and the migrations are frozen, so only the definition remains;
leftover rows are deleted together when a Run is deleted.

## Adding a new definition kind

Kinds are registrations, not a list. Create one `DefinitionKind` and pass it in, and saving, versions, and If-Match work without code changes.

```python
from agent_console_store import DEFAULT_KINDS, DefinitionKind, FileDefinitionStore

note = DefinitionKind("note", directory="notes", model=NoteModel)
defs = FileDefinitionStore("workspace", [*DEFAULT_KINDS, note])  # or defs.register_kind(note)
```

Version hashes are injected: `DefinitionKind(..., hash_fn=...)` or `FileDefinitionStore(..., hash_fn=...)`.
(The app injects ac-graph's `graph_hash` into the graph kind.)

`DefinitionKind.portable` (default true) says whether the kind can live in a project folder copy space (`ac-project-space`). Singleton kinds
cannot be moved regardless of the value (`is_portable`). Register kinds such as the app registry with `portable=False`.
Kinds whose `DefinitionKind.library` (default true) is false are not kept in the library space (the app workspace), only in project and standalone spaces.
The store does not look at this value; whoever opens the library store leaves that kind out (requests for that kind give `NotFound`).
`kind.with_summary_fields(*fields)` is a copy with additional list summary fields.
`DefinitionKind.reserved_ids` (default empty) are words that must not be used as ids of that kind (case-insensitive, for example ids that collide with the fixed REST path
`/<kind>/check` at the same depth). The store does not look at this value. Whoever decides ids, such as create or copy plans, reads it to avoid them or suggest a new id.
`DefinitionKind.title` (default None) is the kind's display name (the copy dialog, the kind column of configuration tables). The default kinds have values. The store does not look at this value.

When you only have a name and need an id, use `slug_id(name, fallback=)` and `unique_id(name, taken, fallback=)` (strip accents, runs of disallowed
characters → `-`, lowercase, 120 characters, `-2`, `-3`… on overlap, case-insensitive). Numbering itself is `numbered_id(base, is_taken, *, max_length=, limit=)` from
`agent-console-numbered-id`, re-exported here (`agent_console_store.numbered_id`).

```python
>>> from agent_console_store import slug_id, unique_id
>>> slug_id("Project Notes", fallback="wiki"), unique_id("Project Notes", ["project-notes"], fallback="wiki")
('project-notes', 'project-notes-2')
>>> unique_id("프로젝트", [], fallback="wiki")
'wiki'

```

Pre-write checks are injected with `write_guard` (`FileDefinitionStore(..., write_guard=fn)`). If `fn(kind, id, document, files)`
raises, none of the document, body, or version record is written (the secret check of `ac-project-space` uses this).
`load_yaml_text`, `dump_yaml`, `merge_into`, `wrap_value`, `to_plain`, and `atomic_write_bytes` are public tools for handling
other files (for example the folder manifest) in the same YAML format (comments and key order preserved).

## Comparing two versions (`diff_versions`)

Compares two versions of one definition (or a version → current) as the contract `DefinitionDiff`. The document is compared as a list of JSON Pointer changes
(`agent_console_settings.diff_documents`), and body files only by the sha256 in the version snapshots. Which locations are secrets
is passed by the caller as `secret_paths` (document → list of JSON Pointers), and those values become `mask` (default `SECRET_MASK` = `***`).

```python
>>> from agent_console_store import DefinitionKind, InMemoryDefinitionStore, diff_versions
>>> notes = InMemoryDefinitionStore([DefinitionKind("note", "notes")])
>>> v1 = notes.create("note", {"id": "n", "title": "a", "token": "t1"}).version_hash
>>> _ = notes.save("note", {"id": "n", "title": "b", "token": "t2"}, expected_version=v1)
>>> diff = diff_versions(notes, "note", "n", v1, secret_paths=lambda doc: ["/token"])
>>> [(c.path, c.after, c.secret) for c in diff.changes]
[('/title', 'b', False), ('/token', '***', True)]

```

## Behavior rules in brief

- Files are written atomically with a temporary file + `os.replace`. Existing files are updated with comments and key order preserved, and unknown fields are preserved too.
- Even if a file changes from outside, the current hash is computed on the next read and a snapshot is kept.
- A single process is assumed (an in-process RLock). If several processes write to the same root at once, If-Match is not guaranteed.
- The interface is synchronous. Calls are short local writes, so you can call them directly from an asyncio loop; the app wraps them in a thread pool if needed.
- Errors are `StoreError` subclasses, and `.code` matches the contract error codes (`not_found`, `already_exists`, `version_required`, `version_conflict`).
- Migration lineages: `legacy` (0001 to 0003, frozen, version table `alembic_version`) and module lineages
  (`migrations/versions` of module packages, version tables `alembic_version_<name>`) are independent. `SqliteDatabase`
  (`open(path)`, `engine`, `upgrade(branches)`, `downgrade_branch`, `revision(name)`) upgrades legacy first and then
  only the lineages passed in (of enabled modules). A lineage only needs `name` and `versions` attributes (`MigrationBranchLike`).
  Tables that legacy created but module lineages own, such as the `usage_observations`, `conversations`, `chat_queue`, and `runs` families, are
  `schema.MODULE_OWNED_TABLES` (excluded from migration comparison).
  **Legacy is never downgraded** (frozen). To roll back, roll back only module lineages (`downgrade_branch`).
  Reason: downgrading legacy to 0002 or below removes module-owned tables (`usage_observations` and others), but module version tables
  (`alembic_version_usage` and others) remain, so on the next start the module lineage sees "already upgraded" and does not recreate the tables.
- Run history lineage: `runs`, `node_runs`, `run_events`, and `interactions` are owned by the lineage `runs` of `ac-mod-runs` (`MODULE_OWNED_TABLES`). The table definitions and the store implementation (`SqliteStorage`) remain in this package, because the path that uses only this package without the lineage and rows in existing databases share the same definitions. Columns the lineage adds (`root_run_id`, `parent_node_id`, `call`, `invoked_by`, interaction `root_run_id`) are read and written **only when they exist** in the database (`schema.runs_lineage_active`). Without them (standalone use without the lineage), the values stay in `doc` and `list(root_run_id=)` scans `doc`. In that case, call NodeRuns of the same node (`call` > 0) cannot be told apart. The table shape after the columns are added is `schema.runs_lineage_metadata`.
- Migrations: `upgrade(engine)`, `downgrade(engine, "base")`, `current_revision(engine)`. Existing migration files are never edited; new ones are added.

## Opening a project records database (`open_records_db`)

Brings one SQLite file in a folder to **the same lineage chain as the app database** (legacy + the module lineages passed in). Used without the server or modules.
If the file does not exist, it is not created (`absent`, viewing = empty lists); `writable_engine()` creates it on the first write. If it is behind, the revision is reread under the write lock,
a SQLite online backup is kept, and each lineage is upgraded (even if two connections open it at once, only one applies). If the revision is unknown to this app
(a newer app), it is opened only with `mode=ro` (`newer`); if it is broken or the upgrade fails, `unavailable` (`reason`, backup path).
**It never downgrades automatically.** No list of lineage names is in the code (the caller passes the `project`-scoped lineages of enabled modules).

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_store import open_records_db
>>> folder = Path(tempfile.mkdtemp())
>>> db = open_records_db(folder / "records.sqlite3", [], backup_dir=folder / "backups")
>>> db.state.state, db.read_engine() is None  # viewing alone does not create the file
('absent', True)
>>> _ = db.writable_engine()  # created on first write, and legacy is upgraded
>>> db.state.state, db.revision()
('ready', '0003')
>>> db.close()

```

Public: `RecordsDb` (`state`, `read_engine()`, `writable_engine()`, `revision()`, `refresh()`, `close()`), `RecordsState`,
`RecordsUnavailable` (`reason`, `backup_path`, code `project.records_unavailable`), `RecordsAbsent`, the shapes consuming modules receive,
`RecordsHandle` and `RecordsSpaces` (optional capability `BatchRecordsSpaces.batch()`: does not evict by the open handle limit while iterating
several spaces; consumers use `RecordsStores.batch()`), the port name `RECORDS_SPACES_PORT` (`records.spaces`), `is_network_fs` (journal `DELETE` on network file
systems), and `can_write_path`. Writability and network detection are injected as arguments. Restoring a backup is only
copying `records-<UTC>-<lineage>@<revision>.sqlite3` in `backup_dir` as a file (the app never deletes or edits them).

## Open resource cache (`OpenCache`)

A name → open value cache shared by the project space pools (records database, memory database). Least recently used order, idle (`idle`),
limit (`over`, which removes and returns entries; closing them is the caller's job), `drop`, `clear`, and `shutdown()` (closes everything, after which
`put` raises `CacheShut`), so late opens after server shutdown do not leave connections behind.

```python
>>> from agent_console_store import OpenCache
>>> closed = []
>>> cache = OpenCache(closed.append)
>>> cache.put("p1", "handle-1")
>>> cache.shutdown()
>>> closed, cache.shut
(['handle-1'], True)

```

## Moving app database records (`RecordsMove`)

A domain-agnostic, table-level move tool. Given a main table + dependent tables + a group id, it moves rows between two engines in the order
copy (one transaction on the target, skipping existing keys) → verify (row counts and values) → delete from the source (one transaction on the source),
and rolls back the target on failure (`run_moves` combines several jobs into one flow). The module docstring has a runnable example.

## Finding the space of a record id (`SpaceLocator`)

Finds records stored across the host database and project records databases (conversations, runs) by one id. It does not know record kinds and takes only
"is that id in that place" (`has`). It looks at known spaces → registered space ids (limit `limit`) → the host (None), and when found in one, it
remembers it and next time rechecks only that place. Interpreting not-found and ambiguous results (404, 409) is the caller's job.

```python
>>> from agent_console_store import SpaceLocator
>>> rows = {None: {"a"}, "p1": {"b"}, "p2": {"b"}}
>>> loc = SpaceLocator(lambda place, key: key in rows[place], project_ids=lambda: ["p1", "p2"])
>>> loc.find("a"), loc.find("b"), loc.find("z")
([None], ['p1', 'p2'], [])

```

## Choosing the definition store space (`SpaceStores`, port `definitions.spaces`)

Modules that handle definitions choose the store by the request's space name (REST `?project=<name>`). Without a name, the default (library);
when a name comes but there is no provider (`DefinitionSpaces.open(space)`), `SpacesUnavailable` (409 `feature_unavailable`, so the
query is never ignored with a write to the library); an unknown name gives `UnknownSpace` (404 `project.not_found`). Only the provider knows what names mean (project
registration ids and so on). `MappedSpaces` is an example implementation as a name → store table.

```python
>>> from agent_console_store import InMemoryDefinitionStore, MappedSpaces, SpaceStores
>>> library, project = InMemoryDefinitionStore(), InMemoryDefinitionStore()
>>> stores = SpaceStores(library, lambda: MappedSpaces({"p1": project}))
>>> stores.get(None) is library, stores.get("p1") is project
(True, True)

```

To keep a space's version history in that folder's records database, pass `RecordsVersionRepository(lambda: handle)` (reads use `read_engine()`, giving empty results when there is
no file; writes use `writable_engine()`) as the store's `versions`. This history store satisfies `VersionWriteCheck.ensure_writable()`,
so when the pre-write check calls it and the records database cannot be written (`RecordsUnavailable` 409, for example a newer revision), the definition files are not written
either. Exceptions that override `StoreError.field_issues()` (for example plain-text secret rejection) are put into 422 `details.issues`
with field locations by `store_error_body`.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-store`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-store/tests
```

## Omitted = inherit, resource bodies, interactions

- **Omitted = inherit**: definitions are stored exactly as the user wrote them. Model instances are stored with `exclude_unset`, dicts as is,
  and models are used only for validation. Omitted, `null`, and `[]` stay distinct after saving. Old files filled with null are not
  fixed automatically.
- **Resource bodies**: `RESOURCE_KIND` (included by default) keeps the body in `resources/<id>/<content.file>` next to `resources/<id>.yaml`.

```python
>>> from agent_console_store import InMemoryDefinitionStore
>>> defs = InMemoryDefinitionStore()  # the same rules as the file store
>>> created = defs.create(
...     "resource",
...     {"id": "team-md", "type": "instruction", "name": "팀 지침", "content": {"file": "content.md"}},
... )
>>> saved = defs.write_content(
...     "resource", "team-md", "# 지침".encode(), expected_version=created.version_hash
... )
>>> defs.read_content("resource", "team-md").decode()
'# 지침'
>>> saved.version_hash != created.version_hash  # the body is part of the version hash
True

```

  If `content.file` is outside the definition folder (`..`, absolute paths, links pointing outside), `InvalidContentPath`.
- **Record stores**: `db.interactions` (the in-memory `InMemoryStorage` uses the same name). Conversation and chat queue stores are owned by `agent_console_mod_chat.storage`.
  When `db.interactions.close(id, status="answered", ...)` is called concurrently, only one succeeds and the others get `InteractionClosed`.
  `db.events.list(run_id, actor=, type_prefix=)`, `latest_by_type`, `list_by_actor`, `db.runs.list(conversation_id=, agent=)`.

## Body snapshots, multi-file bodies, resuming (migration 0003)

> Boundary: the store does not know resource *types* (`ContentSpec.multi_file`). Whether a type allows several files is checked by the caller (the server) before writing files. `prune_orphan_bodies` deletes whole id-shaped folders that have no definition YAML, so when the app calls it, it asks the user to confirm first.

```python
db = open_sqlite("data/console.sqlite3")
defs = FileDefinitionStore(
    "workspace",
    versions=db.versions,
    max_content_bytes=10 * 1024 * 1024,  # total body size of one definition (None = unlimited)
    max_versions=50,
)  # versions to keep per definition (None = all)

# multi-file resources (skill and others): every file in the folder is the body. If-Match is the one version_hash of the definition.
created = defs.create("resource", {"kind": "resource", "id": "sk", "type": "skill", "name": "s"})
v1 = defs.write_files(
    "resource",
    "sk",
    {"SKILL.md": b"...", "scripts/run.py": b"..."},
    expected_version=created.version_hash,
)  # one version
defs.list_files("resource", "sk")  # ResourceFile[]
defs.read_version_file("resource", "sk", created.version_hash, "SKILL.md")  # a past body
defs.restore_version(
    "resource", "sk", v1.version_hash, expected_version=defs.get("resource", "sk").version_hash
)

defs.prune_blobs()
defs.prune_orphan_bodies("resource")
db.runs.list(resumed_from="run-1")
```

- Each save keeps the body files in the version as content-addressed blobs (identical content is stored once). Versions before 0003 have no snapshots.
- Path rules are strict, following Windows: forbidden characters such as `:`, reserved names (`CON`, `nul.txt`), trailing dots and spaces, names that differ only in case, and file/folder name collisions are rejected. Links are checked relative to the workspace root.
- Rolling back migration 0003 removes the contents of `chat_queue`, `content_blobs`, and `content_files`.

# agent-console-link-projects-memory

Projects and memory link module. It opens `<config folder>/memory.sqlite3` in a project folder and provides it as a space
(`memory.spaces`) of the memory module (`mod-memory`). Project runs use only the memory of that folder; shared (library) memory is
copied with `POST /memory/copy` (the copy is independent afterwards).

- Required port `projects.spaces` (`mod-projects`). Without it this link is off and there is no project memory.
- Provided port `memory.spaces`: registration id → `ProjectMemorySpace{store, context, path}`. `context` is
  `{project_id: folder id}` (the manifest `id`), so the scope id stays the same even when another app uses a different registration id.
- Migration lineages: the lineages of enabled modules that declare the scope `memory` (setting `migration_scope`) are applied to the file. The code has
  no lineage names.
- Lazy creation: when `memory.sqlite3` does not exist yet, viewing (list, search, scopes, tags) does not create it.
  The store is the `ac-memory` `DeferredMemoryStore`, so it answers with empty memory, and the first write creates the file and applies the
  lineages. When the file does not exist and the config folder is not writable, opening raises `ConfigReadonly` as before.
- Cache: `max_open_spaces` (default 8) and `idle_close_seconds` (default 300), the same defaults as the project space and record database
  caches.
- Optional port `projects.lookup`: when present, the optional method `existing()` of `memory.spaces` returns only registered projects that
  are not unregistered, whose folder exists, whose config folder is writable, and whose `memory.sqlite3` **already exists**
  (it creates and opens nothing). The automatic server cleanup of `mod-memory` cleans these
  projects after the shared memory. This link has no administrator options. The targets are the user setting
  `memory.retention.auto{library, projects, exclude_projects}`, and the interval is
  `modules.options.mod-memory.retention_interval_seconds` (0 = all off). To turn off only the automatic cleanup of project memory,
  set `memory.retention.auto.projects: false`. When this link is off (`--disable-module
  link-projects-memory`), project memory does not exist at all and the automatic cleanup covers only the shared memory.
- When the file does not exist in a folder that is not writable, it is not created and the request returns 409 `project.config_readonly`. On a network drive
  (`journal: auto`), the `DELETE` journal is used. The user-facing issue `project.network_fs` comes from the project list.

Dependencies: `ac-memory[sqlite]` (store implementation), `ac-project-space` (reading manifests, errors), and `ac-store` (applying lineages,
detecting network file systems). What and why: the same SQLite implementation and lineage tools are reused as they are. Alternative:
the memory module receives a path and opens it itself (the module would then need to know the project cache and folder rules).

## Install

```bash
pip install agent-console-link-projects-memory
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-projects-memory
```

## Minimal usage

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts.memory import MemoryScopeRef
>>> from agent_console_memory.testing import user_author
>>> from agent_console_modkit import MigrationBranch
>>> from agent_console_link_projects_memory import ProjectMemoryPool
>>> from agent_console_link_projects_memory.testing import FolderSpaces
>>> folder = Path(tempfile.mkdtemp())
>>> versions = Path(tempfile.mkdtemp())
>>> _ = (versions / "m_0001.py").write_text(
...     "from agent_console_memory.sqlite import schema\n"
...     "revision = 'm_0001'\ndown_revision = None\nbranch_labels = None\ndepends_on = None\n"
...     "def upgrade():\n    from alembic import op\n    schema.metadata.create_all(op.get_bind())\n"
...     "def downgrade():\n    pass\n", encoding="utf-8")
>>> pool = ProjectMemoryPool(lambda: FolderSpaces({"p1": folder}),
...                          lambda: [MigrationBranch("memory", versions)])
>>> space = pool.open("p1")
>>> space.path.relative_to(folder).as_posix(), space.context
('.agent-console/memory.sqlite3', {'project_id': 'p1'})
>>> space.store.write(MemoryScopeRef(kind="notes", id=""), "k", "본문",
...                   author=user_author()).entry.version
1
>>> pool.shutdown()  # server shutdown: close, and later opens do not open the file
>>> pool.open_spaces(), pool.is_shut
([], True)
>>> ProjectMemoryPool(lambda: FolderSpaces({"p1": folder}), lambda: [],
...                   listing=lambda: FolderSpaces({"p1": folder})).existing()
['p1']

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

In the integrated server, `mod-memory` declares the lineage (`MigrationBranch("memory", …, scopes=("app", "memory"))`),
and this module receives it with `ctx.active_migrations("memory")` and applies it.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

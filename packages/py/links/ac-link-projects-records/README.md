# agent-console-link-projects-records

A link module that opens the **record database** of a project folder (`<folder>/.agent-console/records.sqlite3`) and provides it to the runs,
chat, and copy version modules. The projects module and the record modules do not know each other; this link connects them. Opening the database and
applying the lineages (Alembic) is done by `open_records_db` of `agent-console-store`.

- Required port `projects.spaces` (project registration id → space). Without it this link is off, and the app assembly blocks records
  (it does not write to the app database instead).
- Provided port `records.spaces` (`RecordsSpaces`): `open(space name)`, `state(space name)`, `close(space name)`.
  Space names are `project:<registration id>` (the prefix is a setting).
- **It opens on first write.** Viewing alone creates neither the file nor the config folder (`absent` = empty list). An outdated database is backed up and then upgraded; a newer
  database is only read. The lineages to apply are those of enabled modules that declare `"project"` in `MigrationBranch.scopes` (no list of names in code).
- It keeps the app id `host_id` (`<state folder>/host_id`) and spool files that hold records left over when a folder disappears
  (`<state folder>/records-spool/<registration id>/<run id>.jsonl`). The next time that space is opened, they are written again (duplicate event `seq`
  values are ignored) and deleted.
- Open spaces are managed by an upper limit (`max_open_spaces`) and an idle time (`idle_close_seconds`). An evicted handle comes back when it is written again.
- Passes that read several spaces in turn (usage totals and so on) run inside a `pool.batch()` block (`BatchRecordsSpaces`; the consumer side is
  `RecordsStores.batch()`). Spaces opened inside the block are not evicted by the limit until the block ends, and when the outermost block ends the limit is enforced starting with the
  least recently used. So even with more projects than the limit, one pass opens each project once, and the next pass reopens only the spaces beyond the limit.

## Install

```bash
pip install agent-console-link-projects-records
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-projects-records
```

## Dependencies (what, why, alternatives)

No new external dependencies (`agent-console-store`, `agent-console-project-space`, `agent-console-modkit`, and `agent-console-runtime` (session archive parts) are in-house packages).

## Minimal usage

Open a record database from one folder, without a server.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_projects_records import PoolOptions, RecordsSpacePool, RecordsSpool
>>> from agent_console_link_projects_records.testing import FolderSpaces
>>> root = Path(tempfile.mkdtemp())
>>> (root / "app").mkdir()
>>> pool = RecordsSpacePool(
...     lambda: FolderSpaces({"app": root / "app"}),  # in place of projects.spaces
...     lambda: [],  # module lineages to apply (legacy only when empty)
...     host_id="host-0001",
...     spool=RecordsSpool(root / "spool"),
... )
>>> handle = pool.open("project:app")
>>> handle.state.state, handle.read_engine() is None  # viewing alone does not create the file
('absent', True)
>>> _ = handle.writable_engine()  # created on first write
>>> handle.state.state, (root / "app" / ".agent-console" / "records.sqlite3").exists()
('ready', True)
>>> pool.shutdown()  # server shutdown: close, and later opens do not open the file
>>> pool.open("project:app").state.reason
'link_disabled'

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Settings (`modules.options.link-projects-records`)

| Key | Default | Meaning |
| --- | --- | --- |
| `space_prefix` | `project:` | The prefix removed from the space name (the rest is the project registration id) |
| `max_open_spaces` | 8 | Number of record databases kept open at the same time. Above it, connections are closed starting with the least recently used (inside a `batch()` block, when the block ends). With at least as many as the registered projects, usage totals do not reopen them |
| `idle_close_seconds` | 300 | Closes the connection of a record database not used for this long (0 = never close) |
| `busy_timeout_ms` | 5000 | How long to wait for a lock while another app is writing |
| `backups_keep` | 3 | Number of pre-upgrade backups to keep |
| `journal` | `auto` | `auto`, `WAL`, or `DELETE` (auto = DELETE on a network drive) |
| `spool_dir` | `records-spool` | Name of the spool folder (inside the app state folder) |

All of these are advanced settings.

`session_archive{enabled, dir}` (on by default, `sessions`): when a node finishes, the original conversation session is copied to
`<folder>/.agent-console/<dir>/<backend>/<session>/` (subscribes to `runs.event`; the backend archive capability is the optional port `runs.session_archive`),
and the `records.sessions` port provides the resume state and restore (`ProjectSessionArchive`). Credential files are not included. When the folder is shared, the original conversations
are shared with it. When it is off, nothing new is archived and existing copies are not deleted. An archive failure is the info issue `records.session_archive_failed`.

## Standalone run

```bash
python -m agent_console_link_projects_records --check
```

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

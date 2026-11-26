# agent-console-project-space

Opens `<folder>/.agent-console/` of one project folder as a **configuration copy space**.
Definitions (agents, teams, resources, and so on) are stored in the same format as workspace definition YAML (one folder per kind, `ac-store`'s
`FileDefinitionStore`), and the folder manifest `project.yaml` is read and written.
It works with only the folder, without the server, a database, or the web app.

- At registration (`init_space`), `project.yaml` and `.gitignore` are created **only when missing**. Existing ones are adopted and not changed.
  Nothing is written into a folder with a broken manifest. A folder that cannot be written is reported with `config_writable=False`.
- Values that look like secrets are not stored (`SecretRejected`, with locations but no values). Definitions hold only `secret://<name>` references.
- Conflict detection uses the same If-Match (`expected_version`) as the definition store. So does the manifest.
- No kind names, folder names, or file names are in the code. Kinds are `DefinitionKind` (only `portable` kinds go into the space),
  and names are the `config_dir` and `SpaceLayout` arguments. The `.gitignore` template is the package data `data/gitignore.template`. The name slots in the template (`{records_file}`,
  `{sessions_dir}`, `{memory_file}`, `{state_dir}`) are filled from the space layout (`render_gitignore_template`).
- The file system is injected as `SpaceFiles` (default `LocalFiles`). The definition store itself is `FileDefinitionStore`, so
  its root is a local path.
- It only reports the paths of the records database (`records.sqlite3`) and the memory database (`records_db_path`, `memory_db_path`). It does not create the files. Opening the records database is done by `ac-store`'s `open_records_db` (this package knows only the path).

## Installation

```bash
pip install agent-console-project-space
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-project-space
```

Dependencies (what / why / alternatives): `agent-console-store` (reuses the definition store and YAML format / to avoid a new storage format),
`agent-console-secret-rules` (reuses the secret suspicion rules / to avoid copying the rules; alternative: accept only an injected check function, not chosen because
standalone use could skip the check), `agent-console-contracts` (`ProjectManifest`).

## Minimal usage

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import ProjectManifest
>>> from agent_console_project_space import init_space, open_space, read_manifest

>>> folder = Path(tempfile.mkdtemp())
>>> result = init_space(folder, manifest=ProjectManifest(id="payments", name="결제 서비스"))
>>> result.manifest_state, result.gitignore_state, result.config_writable
('created', 'created', True)
>>> sorted(p.name for p in (folder / ".agent-console").iterdir())
['.gitignore', 'project.yaml']

>>> space = open_space(folder)
>>> _ = space.definitions.create("agent", {"id": "dev", "name": "개발자"})
>>> space.definitions.list_ids("agent")
['dev']
>>> read_manifest(space).manifest.name
'결제 서비스'

>>> from agent_console_project_space import SecretRejected
>>> try:
...     space.definitions.create("agent", {"id": "bad", "name": "x", "attributes": {"api_key": "abcd1234efgh5678"}})
... except SecretRejected as error:
...     print([f.path for f in error.findings])
['/attributes/api_key']

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Public API

| Name | What it does |
| --- | --- |
| `open_space(folder, *, kinds, versions, config_dir, files, layout, secret_rules, scan_bodies, ...)` | Opens the space (no writes). `ProjectSpace{folder, root, definitions, manifest_path, gitignore_path, memory_db_path, records_db_path, sessions_dir, state_dir, portable_kinds, config_writable}` |
| `init_space(folder, *, manifest, gitignore_template, **open arguments)` | Creates `project.yaml` and `.gitignore` only when missing -> `InitResult{space, manifest, manifest_state, manifest_issue, gitignore_state}` |
| `read_manifest(space)` / `write_manifest(space, manifest, *, expected_version)` | Reads the manifest (None when missing) / writes with If-Match (unknown keys and comments preserved) |
| `reset_manifest(space, manifest, *, now)` | Keeps the old `project.yaml` as `<state_dir>/backups/project-<UTC>.yaml` and writes a new one |
| `portable_kinds(kinds)` | Kinds that go into the space (`DefinitionKind.is_portable`) |
| `scan_secrets(rules, document)` | Locations of suspected plain-text secrets (no values) |
| `default_gitignore_template()` | The package data `.gitignore` template |
| `missing_gitignore_lines(space, template=None)` | Lines of the template starting with `/` that are missing from `.gitignore` (all of them when there is no file). It only reports |
| `append_gitignore(space, template=None)` | Appends the missing lines at the end (existing lines stay) and returns the added lines. `ConfigReadonly` when read-only |
| `SpaceFiles`, `LocalFiles` | File system injection point / default implementation |
| Exceptions | Under `SpaceError` (`StoreError`): `FolderMissing`, `ConfigReadonly`, `UnsafeConfigDir`, `ManifestInvalid` (`reason`), `SecretRejected` (`StoreError`, `findings`, `field_issues()` → 422 `details.issues`). `code` is the contract `ErrorCodes`; the server responds with the shared `store_error_body` |

Lines in the `.gitignore` template start with `/` so they point only directly under the config folder (so resources named `claude` or `sessions`
are not left out of commits). Version history is passed by the caller as `versions=` (usually that folder's records database,
`agent_console_store.RecordsVersionRepository`). If omitted, it is in memory. If the history store provides `ensure_writable()`, it is called before writing definitions,
so when the records database cannot be written, the definition files are not written either.
Test tools are in `agent_console_project_space.testing` (`ReadOnlyFiles`, `FolderSpaces`, and so on).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

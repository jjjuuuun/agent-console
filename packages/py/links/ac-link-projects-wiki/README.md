# agent-console-link-projects-wiki

A link module that provides project folders as **wiki spaces** of the wiki module. The projects module (`mod-projects`) and the wiki module (`mod-wiki`) do not know each other; this link connects them.

- Required port `projects.spaces` (registration id → project space). Without it this link is off.
- Provided port `wiki.spaces` (`ProjectWikiSpaces`): `open(registration id) -> ProjectWikiSpace{store, folder,
  config_writable, config_dir, pages_dir, pages_root, index_dir}`. Wiki and wiki rule definitions go into that folder's definition
  store (`<folder>/.agent-console/`), pages into `<folder>/.agent-console/<pages_dir>/<wiki id>/`, and the search index into the
  state folder (`<config folder>/.state/<index_dir>/`, a cache that can be rebuilt). When the same folder is registered in another app (another
  workspace), wikis, pages, and rules stay the same, and when the records link (`link-projects-records`) is on too,
  page history also stays in that folder's record database.
- **Path guarding**: `FolderGuard` of `ac-projects` (the same rules as `link-projects-sdd`). When the page folder overlaps a reserved folder of the config
  folder (state and session folders, definition kind folders, the setting `reserved_dirs`), or when the page folder or wiki folder resolves (after following links)
  outside the project folder, the space is not opened (422 `folders.invalid_path`; absolute paths are not included).
  Page paths inside a wiki folder are guarded by `ac-wiki` `LocalWikiPages`.
- A folder that is not writable gets `config_writable=false`: viewing and search work, and writes return 409 `project.config_readonly`
  (returned by `mod-wiki`). The search index is kept in memory.
- When a space is opened and the manifest (`project.yaml`) is broken, the request returns 409 `project.manifest_invalid`; when the folder does not exist, 409
  `project.folder_missing`. Opening alone creates nothing.
- **When this link is off**, `mod-wiki` returns 409 `wiki.spaces_unavailable` for `?project=` requests. It does not create the wiki in the app
  workspace (the standalone root) instead.

## Install

```bash
pip install agent-console-link-projects-wiki
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-projects-wiki
```

## Dependencies (what, why, alternatives)

No new external dependencies (`agent-console-project-space` (spaces, manifests), `agent-console-projects` (path guard
`FolderGuard`), `agent-console-store` (path string checks), `agent-console-modkit`, and `agent-console-contracts` are in-house
packages). The wiki module (`agent-console-mod-wiki`) is only a dev dependency (for tests); the link connects to it by port names only.

## Minimal usage

Open one folder as a wiki space, without a server.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_projects_wiki import ProjectWikiSpaces, UnsafePagesRoot
>>> from agent_console_link_projects_wiki.testing import FolderSpaces
>>> folder = Path(tempfile.mkdtemp())
>>> spaces = ProjectWikiSpaces(lambda: FolderSpaces({"app": folder}))  # in place of projects.spaces
>>> space = spaces.open("app")
>>> space.config_dir, space.pages_dir, space.config_writable
('.agent-console', '.agent-console/wiki-pages', True)
>>> space.pages_root == folder / ".agent-console" / "wiki-pages"
True
>>> try:
...     ProjectWikiSpaces(lambda: FolderSpaces({"app": folder}), pages_dir=".state").open("app")
... except UnsafePagesRoot as exc:
...     exc.reason
'reserved'

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Settings (`modules.options.link-projects-wiki`)

| Key | Default | Meaning |
| --- | --- | --- |
| `pages_dir` | `wiki-pages` (package data) | Page folder inside the config folder. When not set, it inherits `modules.options.mod-wiki.pages_dir` (`SeedSetting`) |
| `index_dir` | `wiki-index` (package data) | Search index folder inside the state folder |
| `reserved_dirs` | `[]` | Folders the page folder must not overlap (relative to the project folder). State, session, and definition kind folders are always blocked |

The config folder name follows `mod-projects.config_dir` (`pages_root` = `<config_dir>/<pages_dir>`).

## Standalone run

```bash
python -m agent_console_link_projects_wiki --check                        # check the assembly with an empty folder list module
python -m agent_console_link_projects_wiki --with mod-projects --with mod-wiki
```

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

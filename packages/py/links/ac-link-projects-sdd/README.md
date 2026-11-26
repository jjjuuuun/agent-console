# agent-console-link-projects-sdd

A link module that provides project folders as **spec spaces** of the SDD module. The projects
module (`mod-projects`) and the SDD module (`mod-sdd`) do not know each other; this link connects them.

- Required port `projects.spaces` (registration id → project space). Without it this link is off.
- Provided port `sdd.spaces` (`ProjectSddSpaces`): `open(registration id) -> ProjectSddSpace{store, folder,
  config_writable, files, config_dir}`. Specs and document templates go into that folder's definition store (`<folder>/.agent-console/`),
  so specs and rules stay the same when the same folder is registered in another app (another workspace).
- `files` (`ProjectSpecFiles`) reads and writes only inside that folder. `..`, absolute paths, and links (whose real path is outside the folder) are
  rejected (422 `folders.invalid_path`). The app config folder (`.agent-console`, depending on settings) is rejected for reading, writing, and listing,
  and a folder that is not writable returns 409 `project.config_readonly`.
- When a space is opened and the folder manifest (`project.yaml`) is broken, the request returns 409 `project.manifest_invalid`; when the folder does not exist,
  409 `project.folder_missing`. Opening alone creates nothing.
- **When this link is off**, `mod-sdd` returns 409 `sdd.spaces_unavailable` for `?project=` requests. It does not create the specs in the app
  workspace instead.

## Install

```bash
pip install agent-console-link-projects-sdd
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-projects-sdd
```

## Dependencies (what, why, alternatives)

No new external dependencies (`agent-console-project-space` (spaces, manifests), `agent-console-projects` (path guard
`FolderGuard`), `agent-console-sdd` (`SpecFiles`, path checks), `agent-console-store`, and `agent-console-modkit` are in-house
packages).

## Minimal usage

Open one folder as a spec space, without a server.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_projects_sdd import ProjectSddSpaces
>>> from agent_console_link_projects_sdd.testing import FolderSpaces
>>> folder = Path(tempfile.mkdtemp())
>>> spaces = ProjectSddSpaces(lambda: FolderSpaces({"app": folder}))  # in place of projects.spaces
>>> space = spaces.open("app")
>>> space.config_dir, space.config_writable
('.agent-console', True)
>>> space.files.write("docs/plan.md", b"# plan\n")
>>> [e.name for e in space.files.list("docs")]
['plan.md']
>>> from agent_console_sdd import SpecPathError
>>> try:
...     space.files.write(".agent-console/x.md", b"x")
... except SpecPathError as exc:
...     exc.details["reason"]
'reserved'

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Settings (`modules.options.link-projects-sdd`)

`reserved_dirs` (default `[]`): folders, besides the app config folder, that import, export, and file listing do not touch (paths relative to the project
folder, for example `.git`). The config folder name follows `mod-projects.config_dir`, and the spec folder follows `mod-sdd.spec_dir`
(`SddInfo.spec_root` = `<config_dir>/<spec_dir>`).

## Standalone run

```bash
python -m agent_console_link_projects_sdd --check                       # check the assembly with an empty folder list module
python -m agent_console_link_projects_sdd --with mod-projects --with mod-sdd
```

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

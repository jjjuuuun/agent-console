# agent-console-mod-projects

Agent Console projects feature module (module id `mod-projects`).

- Project = a local folder + the configuration copies inside it (`<folder>/.agent-console/`). The app registry
  (`<workspace>/projects/<id>.yaml`) keeps only the folder, the unregistered flag, and labels; the name, description, and project layer live in the folder manifest
  (`.agent-console/project.yaml`).
- On registration, the manifest and `.gitignore` are created **only when they do not exist**. Existing ones are adopted, and when the manifest is broken nothing is
  written to the folder (status `manifest_invalid`, [Recreate settings file]).
- The same folder or overlapping folders are not registered (409). Deleting means unregistering; folder contents and records are not deleted.
- It exposes over REST: folder checks, browsing inside the app, the native folder picker (on the server computer, loopback servers only), and copying between spaces
  (library ↔ project, with reference closure, conflict choices, body files, and secret rejection).
- The rule calculations are done by the pure packages `agent-console-projects`, `agent-console-local-folders`, and
  `agent-console-project-space`.

## Install

```bash
pip install agent-console-mod-projects
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-projects
```

## Minimal usage

Use only the registry and the action set, without a server (registering a folder creates `.agent-console/` in it).

```python
>>> import tempfile, pathlib
>>> from agent_console_contracts import ProjectCreate
>>> from agent_console_local_folders import LocalFileSystem
>>> from agent_console_store import FileDefinitionStore, InMemoryVersionRepository
>>> from agent_console_mod_projects import (
...     ProjectManager, ProjectRepository, ProjectSpaceCache, project_kind)
>>> ws, folder = pathlib.Path(tempfile.mkdtemp()), pathlib.Path(tempfile.mkdtemp()) / "pay"
>>> folder.mkdir()
>>> repo = ProjectRepository(
...     FileDefinitionStore(ws, [project_kind()], versions=InMemoryVersionRepository()))
>>> options = lambda: {"config_dir": ".agent-console"}
>>> manager_box = []
>>> spaces = ProjectSpaceCache(lambda pid: manager_box[0].folder_of(pid), options=options)
>>> manager = ProjectManager(
...     repo, fs=LocalFileSystem(), spaces=spaces, space_options=options, base_dir=ws)
>>> manager_box.append(manager)
>>> view = manager.create(ProjectCreate(folder=str(folder), name="결제"))
>>> view.project.id, view.project.name, view.status
('pay', '결제', 'ready')
>>> (folder / ".agent-console" / "project.yaml").is_file()
True
>>> spaces.open("pay").folder == folder
True
>>> manager.close()

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## REST (the host adds `/api/v1`)

| Method and route | Request → response | Errors |
| --- | --- | --- |
| `GET /projects` | → `ProjectView[]` (including unregistered ones) | — |
| `POST /projects` | `ProjectCreate` → 201 `ProjectView` + `ETag` | 409 `project.folder_taken` (`details.archived` when unregistered) and `project.folder_overlaps`, 409 `already_exists`, 422 `folders.*` (not a path), 422 secret |
| `GET /projects/{id}` | → `ProjectView` + `ETag` (a hash of the registry entry and manifest combined) | 404 |
| `PUT /projects/{id}` | `ProjectUpdate` (+ `If-Match`) → `ProjectView` | 412, 409 overlap, `project.folder_missing`, `project.manifest_invalid`, `project.config_readonly` |
| `DELETE /projects/{id}` | (+ `If-Match`) → 204 (unregistered) | 404, 412 |
| `POST /projects/{id}/manifest/reset` | `ManifestResetRequest` → `ManifestResetResult` | 409 (not broken: `already_exists`; not writable) |
| `POST /projects/{id}/gitignore/append` | → `ProjectView` | 409 folder missing, not writable |
| `POST /projects/{id}/legacy/plan` | → `CopyPlan` (library definitions with the old `project` field → this space) | 404, 409 `feature_unavailable` |
| `POST /projects/copy/plan` | `CopyPlanRequest` → `CopyPlan` | 400 same space, 404 `project.not_found`, 409 `feature_unavailable` and `project.manifest_invalid` |
| `POST /projects/copy/apply` | `CopyApplyRequest` → `CopyApplyResult` (only changed items are `conflict`) | The above + 409 `project.config_readonly`, 422 secret (nothing is written), 422 `validation_failed` (the id to write in the target (the source id for copy and overwrite, the new id for rename) is a reserved word of that kind: `details.issues` = error `project.copy_reserved_id` (suggestion `suggested_id`), nothing is written; text keys `project.copy_reserved_id.rename` and `project.copy_reserved_id.write`) |
| `GET /projects/copy/kinds?project=` | → `CopyKindInfo[]` (the copy kinds of that space + `library`, `portable`, `deletable`; default and contributed kinds) | 404 `project.not_found`, 409 `feature_unavailable` (shared library without the definitions module) |
| `GET /projects/copy/items?project=&kind=` | → `CopyItem[]` (the definition list of that space, without bodies) | The above + 404 `not_found` (not a copy kind of this space) |
| `DELETE /projects/copy/items/{kind}/{id}?project=` (+ optional `If-Match`) | → 204 (common delete for all kinds: default kinds from the space store, contributed kinds through the contribution's `delete` callback. No reference check) | The above + 404 (unknown kind or item), 400 `bad_request` `details.reason=not_deletable` (`CopyKindInfo.deletable` false), 409 `project.config_readonly`, 412 `version_conflict` |
| `GET /projects/copy/items/{kind}/{id}/references?project=` | → `CopyItemReferences` (definitions in the same space that use this item, for the delete confirmation dialog. It does not know kind names; it finds them through `definitions.references` and the contributions' `references`. Without reference extraction, `checked` false + info `project.references_unavailable`) | The above + 404 (not a copy kind of this space, or the item does not exist) |
| `GET /projects/folders?path=&hidden=` | → `FolderListing` (folder names only) | 403 `folders.remote_disabled`, 4xx `folders.*` |
| `POST /projects/folders/check` | `FolderCheckRequest` → `FolderCheck` (overlaps, number of existing configuration items, `suggested_id`, `config_dir`) | 403 |
| `GET /projects/folders/capabilities` | → `FolderCapabilities` | — |
| `POST /projects/folders/pick` | `FolderPickRequest` → `FolderPickResult` (picked, cancelled, unavailable, busy, timeout, failed) | 403 (not loopback) |

A picker request stays open until the user chooses. When the request is cut off, the server ends the picker process.

The old routes for cleaning up definition scopes (`POST /projects/move-plan`, `/move`, `/scope-issues`) were removed in 0.3.0. They match the
`/projects/{id}` shape, so they answer 405 Method Not Allowed. Old definitions with the `project` field are cleaned up with
`POST /projects/{id}/legacy/plan` → `POST /projects/copy/apply`.

## Ports

| Port | Direction | When missing |
| --- | --- | --- |
| `projects.lookup` | Provides (`get_project`, `list_projects`, the combined `Project`) | — |
| `projects.folders` | Provides (`() -> ProjectFolderSet`: `entries` (id, folder), `archived` (unregistered folders), `project_for`) | — |
| `projects.spaces` | Provides (`open(project_id) -> ProjectSpace`, with a cache limit and idle closing. An unknown id raises `LookupError`, a missing folder `FolderMissing`) | — |
| `definitions.spaces` | Provides (`open(project_id) -> DefinitionStore`) | — |
| `definitions.lookup`, `definitions.store` | Optional (the library) | Copies that involve the library return 409 `feature_unavailable`; space kinds = the `ac-store` defaults |
| `definitions.references` (several) | Optional | Info `project.references_unavailable` in copy plans |
| `definitions.kind_contributions` (several) | Optional (adds contributed kinds to the space kinds, including `library=False`, only portable ones. The contributions' `references` are merged with `definitions.references` for reference closure) | Space kinds = library kinds |
| `definitions.reference_rewriters` (several) | Optional (rewrites references in rename copies) | References stay as they are, with an info issue on the result item |
| `records.spaces` | Optional (`ProjectView.records_*`) | `records_state=unavailable`, `reason=link_disabled` |
| `secrets.rules` | Optional | Default secret rules |

Extension point (folder picker): code picker providers are added through the entry point `agent_console.folder_dialogs`
(`FolderDialogProvider{id, available(environ), pick(*, initial, title, timeout, cancel)}`).
The host plugin loader (`agent_console_mod_projects.plugins:load_plugins`, extension `FOLDER_DIALOGS_EXTENSION`) reads them at server startup,
so like other plugins they follow the server settings `plugins.enabled` and `plugins.disabled` and appear in `server-info`. When assembling
without a bundle, read them directly with `load_dialog_providers(enabled=, disabled=)`. Data providers (command tables) are the setting `folder_dialog.providers`.

## Settings (`modules.options.mod-projects`)

- `directory` (registry folder), `config_dir` (default `.agent-console`), `records_file` (record database file name), and
  `sessions_dir` (session archive folder name; when empty, it inherits `link-projects-records.session_archive.dir`).
  The `.gitignore` template and the `project.gitignore_outdated` check follow these names
- `status_timeout_seconds` (default 2), `browse_roots`, `allow_remote_browse` (off by default),
  `server_host` (inherits the server `host`), `case_insensitive_paths` (for example `/mnt/?`)
- `folder_dialog`: `mode` (auto, off), `providers`, `include_default_providers`, `timeout_seconds` (default 300)
- `max_open_spaces` and `idle_close_seconds` (space cache), `records_space_prefix` (inherits the records link `space_prefix`),
  `messages`, and (not read) `snapshot_ttl_seconds` and `working_directory` (the server still starts when they remain)

## Standalone run

```bash
python -m agent_console_mod_projects --check   # without --with, a local definition store is attached too
```

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

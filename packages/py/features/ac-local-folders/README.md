# agent-console-local-folders

Pure rules for picking local folders: **path normalization**, **folder checks** (exists, is a folder, permissions, hidden, link, can be created,
nearest parent), listing **only the names of subfolders** (hidden ones hidden by default, links, locks, count and time limits,
browse scope limits), **creating folders**, **default start locations**, and the **native folder picker dialog** (a command table as data +
one shared runner). You use it without the server, the web app, or other internal packages (standard library only).

- **The file system is injected** (`FileSystem` protocol): the real `LocalFileSystem`, and for tests and examples
  `MemoryFileSystem` (imitates `posix`/`windows` paths regardless of the host, hidden attributes, links, and missing permissions).
- Folder contents are never returned. `list_dirs` returns only subfolder names, paths, and flags (`hidden`, `link`, `locked`),
  and `check_folder` does not read the listing.
- It handles POSIX paths (`/srv/…`) and Windows paths (drive letter paths, UNC, case-insensitive drives). A path in a style different from the server's
  gives `problem="foreign_path"` (unusable). It does not convert paths to another OS style.
- Hidden is judged by dot names and the OS hidden attribute (Windows). Other folders to hide by name and the start locations are
  data (extension point, `data/browse_defaults.json`; the default `hidden_names` is an empty list).
  Replace them with `load_browse_defaults(dict)`.
- It does not know the project registry. Already registered, overlapping, excluding itself (`exclude_project_id`), and same as the previous path are
  judged by `ac-projects`/`ac-mod-projects` from `check.path`.

| Function | What it does |
| --- | --- |
| `normalize_lexical(raw, *, flavor, environ)` | Input → normalized absolute path (does not read the disk). Quotes, `~`, `..`, trailing separators, uppercase drives. Failures raise `FolderError` |
| `normalize(raw, *, fs, environ, real=True)` | The above + the real path with links resolved (for registration and storage) |
| `check_folder(raw, *, fs, environ, defaults, roots)` | `FolderCheck` (fields + `status`: `ok`, `ok_readonly`, `missing`, `missing_parent`, `not_directory`, `no_access`, `invalid`). Never raises because of the input |
| `list_dirs(path, *, fs, show_hidden, limit=2000, timeout=3.0, roots, defaults, clock)` | `FolderListing(path, parent, entries, truncated, timed_out, hidden_count)` |
| `make_folder(path, *, fs, name=None, roots)` | Creates one folder (parents are not created). With `name`, under `path` after checking the name |
| `default_roots(environ, *, fs, defaults)` | Whichever of home, root, macOS `/Volumes/*`, and Windows drives exist |
| `nearest_existing(path, *, fs)` | The path itself (if it is a folder) or the nearest existing parent folder |
| `path_key`, `is_within`, `validate_folder_name`, `home_dir` | Comparison key (case-insensitive on Windows), whether inside a scope, new folder name check, home from environment variables |

Error codes (`FolderErrorCode`, `FolderError.code`, `FolderCheck.problem`): `empty`, `invalid_path`, `relative`,
`foreign_path`, `no_home`, `outside_roots`, `not_found`, `not_directory`, `no_access`, `invalid_name`, `exists`,
`missing_parent`, `io_error`. `FolderError.message` is a default Korean message (screens pick their own message by code).

Time limits are checked between entries. A slow mount where one OS call hangs (network drives and so on) cannot be interrupted,
so the server calls these functions in a thread and applies a time limit from outside.

## Native folder picker dialog

The server opens the OS folder picker dialog and gets the **absolute path** the user chose. The per-OS commands are not code but
**data** (`data/folder_dialogs.json`), and one shared runner executes the table.

| Default entry id | Platform (`sys.platform` prefix) | Executable | Environment condition | Cancel detection |
| --- | --- | --- | --- | --- |
| `windows-powershell` | `win32` | `powershell` | — | Empty output (`FolderBrowserDialog`, topmost window, values passed through environment variables) |
| `macos-osascript` | `darwin` | `osascript` | — | Empty output (`choose folder`, values as `on run argv` arguments) |
| `zenity` | `linux`, `freebsd` | `zenity` | One of `DISPLAY`, `WAYLAND_DISPLAY` | Exit code 1 |
| `kdialog` | `linux`, `freebsd` | `kdialog` | One of `DISPLAY`, `WAYLAND_DISPLAY` | Exit code 1 |

- Entry format: `{id, label?, platforms, requires, env_requires?, argv, env?, cancel_exit_codes, encoding}`.
  Only `{initial}` and `{title}` inside `argv` and `env` are replaced with values (it is not `str.format`, so braces in scripts
  stay as they are). An `argv` item is a string or `{"when": "initial"|"title", "args": [...]}` (added only when the value exists).
  Do not embed user values in script strings; pass them as separate arguments or through `env` (prevents shell and script injection).
- `load_dialog_specs(extra, include_defaults=True)`: merges server administrator entries. The same id replaces that entry,
  and `"enabled": false` removes it. New ids go **before** the default entries (server administrator entries first).
- `probe_dialogs(specs, platform=, which=, environ=)` → `DialogAvailability{selected, probes, reason}`:
  It does not run commands; it looks only at the platform, executables, and environment variables. `reason`: `no_provider`, `missing_command`,
  `missing_env`. `select_dialog` returns only `selected`.
- `run_dialog(spec, runner=, initial=, title=, timeout=300, cancel=, fs=, environ=)` → `DialogResult{status,
  path, check, provider, exit_code, detail, message}`. Runs without a shell, reads the first line of standard output as the path, and
  normalizes it with `check_folder`. `status`: `picked`, `cancelled` (cancel code, empty output, `cancel` signal),
  `unavailable` (no executable), `timeout` (the runner ended the process), `failed` (`detail`: `exit_code`,
  `bad_encoding`, `invalid_path`, `os_error`). If `initial` is a folder that does not exist, the dialog opens at the nearest parent folder.
- Command execution is injected through the `CommandRunner` protocol. The real one is `SubprocessRunner` (`shell=False`, no standard input,
  `kill` on time limit or stop signal (`threading.Event`), no console window on Windows).
- There are no rules specific to one runtime environment. It looks only at the server process's platform, executables, and environment variables. If you need another tool,
  add a data entry.
- **Assumption: use it only on a loopback server.** The dialog appears on the screen of the computer the server process runs on. This package does not know
  the server binding, so blocking it on remote bindings (and opening only one at a time) is the caller's job.

```python
>>> from agent_console_local_folders import (
...     CommandOutcome, MemoryFileSystem, load_dialog_specs, probe_dialogs, run_dialog)
>>> specs = load_dialog_specs()
>>> avail = probe_dialogs(specs, platform="linux",
...                       which=lambda name: "/usr/bin/zenity" if name == "zenity" else None,
...                       environ={"DISPLAY": ":0"})
>>> avail.selected.id
'zenity'
>>> def fake_runner(argv, *, env, timeout, cancel=None):   # the real one is SubprocessRunner()
...     return CommandOutcome(exit_code=0, stdout=b"/srv/me/work/\n")
>>> fs = MemoryFileSystem().add_dir("/srv/me/work")
>>> result = run_dialog(avail.selected, runner=fake_runner, title="Project folder", fs=fs)
>>> result.status, result.path
('picked', '/srv/me/work')
>>> probe_dialogs(specs, platform="linux", which=lambda name: None, environ={}).reason
'missing_command'

```

## Dependencies: what / why / alternatives

- None (standard library only: `ntpath` and `posixpath` handle both path styles regardless of the host). Alternative:
  `pathlib.PureWindowsPath`, which would still need separate normalization of `~`, quotes, and uppercase drives plus a string comparison key,
  so it would end up as the same code.

## Installation

```bash
pip install agent-console-local-folders
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-local-folders
```

## Minimal usage

```python
>>> from agent_console_local_folders import (
...     MemoryFileSystem, check_folder, list_dirs, make_folder, default_roots)
>>> fs = (MemoryFileSystem()                     # LocalFileSystem() for the real disk
...       .add_dir("/srv/me/work/app").add_dir("/srv/me/.cache")
...       .add_file("/srv/me/notes.txt"))
>>> env = {"HOME": "/srv/me"}
>>> check = check_folder("~/work/app/", fs=fs, environ=env)
>>> check.status, check.path
('ok', '/srv/me/work/app')
>>> check_folder("/srv/me/new", fs=fs).status
'missing'
>>> foreign = check_folder("\\\\server\\work\\me", fs=fs)    # a Windows (UNC) path on a POSIX server
>>> foreign.status, foreign.problem
('invalid', 'foreign_path')
>>> listing = list_dirs("/srv/me", fs=fs)        # folder names only; hidden ones hidden by default
>>> [e.name for e in listing.entries], listing.hidden_count, listing.parent
(['work'], 1, '/srv')
>>> make_folder("/srv/me/work", name="new", fs=fs).path
'/srv/me/work/new'
>>> [(r.kind, r.label) for r in default_roots(env, fs=fs)]
[('home', '~'), ('root', '/')]

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

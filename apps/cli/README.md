# agent-console-cli

The executable command `agent-console`. It has three commands: run the server (`serve`), the Claude Code statusLine
usage bridge (`statusline`), and clear the log index (`logs purge`). The logic lives in packages: the server in
`agent-console-server`, the usage status line in `agent-console-usage`, and index clearing in `agent-console-logs`.
This package only connects the command names to them.

## Install

```bash
uv sync --all-packages        # inside the workspace
uv pip install ./apps/cli     # standalone (installs the server and usage packages too)
```

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `typer` | Commands, options, help | Options are declared with type hints, with environment variable defaults | click alone, argparse |
| `agent-console-server` | `serve` (delegates to the server `main`), reading the workspace path from the server settings | One install includes `serve` (`uv tool install`). Imported lazily only in the `_server` module (one import-linter exception) | Running `python -m agent_console_server` as a subprocess |
| `agent-console-usage` | `statusline` parsing, file merging, atomic writes, the status line | The same file format as the server usage source, defined in one place | — |
| `agent-console-logs` | `purge_index` and `open_existing_log_index` for `logs purge` | The same clearing behavior as the server API, defined in one place. Imported lazily only inside the command | Only a server API (unusable while the server is off) |

## Commands

```bash
uv run agent-console --version                  # agent-console <version>
uv run agent-console serve [server options…]    # option list: uv run agent-console serve --help
uv run agent-console statusline (--output PATH | --config PATH) [--label WINDOW=TEXT ...]
                                [--template TEXT] [--separator TEXT] [--empty TEXT]
uv run agent-console logs purge [--config PATH | --index PATH] [--source ID ...] [--category ID ...]
                                [--before WHEN] [--rescan/--no-rescan] [--dry-run | --yes] [--all]
```

### `--version`
Prints one line, `agent-console <version>`, and exits (exit code 0). The version is not kept in the code; it is read
from the installed metadata (`agent-console-cli`, `project.version` in `pyproject.toml`). It does not import the server
package.

### `serve`
Passes the arguments after `serve` unchanged to the server `agent_console_server.main(argv, prog="agent-console serve")`.
The options are defined in one place in the server, so they are the same as for `python -m agent_console_server`
(see the [server README](../server/README.md)), and options that installed modules declare with
`SettingsCompat.flags` appear automatically.

- Common options: `--config/-c`, `--host`, `--port`, `--workspace`, `--allow-origin ORIGIN` (repeatable, appended
  after the list in the settings), `--open/--no-open`, `--enable-module ID`, `--disable-module ID` (repeatable; they
  take precedence over the `modules` settings, and when both name the same id, turning off wins).
- Precedence: command line > `AGENT_CONSOLE_*` environment variables > settings file > defaults. The token is not
  printed; clients get it from `GET /api/v1/bootstrap`. A settings error exits with code 2.

### `statusline`
Reads the stdin JSON that Claude Code passes to the statusLine command, prints one usage status line, and atomically
merges only `rate_limits` into the bridge file (read by the server's `statusline-file` usage source). The logic is in
`agent-console-usage` (`agent_console_usage.statusline`); this command only connects stdin, stdout, and paths.
It does not read or write `~/.claude`: you add the one statusLine settings line yourself (see the
[`ac-usage` README](../../packages/py/features/ac-usage/README.md)).

| Option | Default | Meaning |
| --- | --- | --- |
| `--output`, `-o` | — | Bridge file path (recommended: fast) |
| `--config` / `AGENT_CONSOLE_CONFIG` | — | Without `--output`, `<workspace>/.state/usage/statusline.json` from the server settings. Without both, exit code 2 (it does not quietly write to the current folder) |
| `--label` | The window id as is | `window=display name` (repeatable) |
| `--template` | `{label} {percent}{resets_suffix}` | Template for one window. Fields: `label`, `window`, `percent`, `resets_in`, `resets_suffix` |
| `--separator` | ` · ` | Separator between windows |
| `--empty` | Empty string | Shown when there is no window to show |

- It works when windows or fields are missing. Without a usage rate it shows `-` (it does not make up a number); with
  no windows at all, the file is left as it is.
- Exit codes: 0 success; 1 when the input is not a JSON object (the file is left as it is) or the file write failed
  (the line is still printed); 2 option or settings error.
- The bridge file is replaced atomically, but read, merge, and write are not locked. When several sessions write the
  same file at the same time, the last write wins (see "Bridge file format" in the `ac-usage` README).

### `logs purge`
Deletes rows of a source, category, or time range from the log index. The meaning is the same as
`agent_console_logs.purge_index` and the server `POST /api/v1/logs/index/purge`. The original log files are not
touched.

| Option | Default | Meaning |
| --- | --- | --- |
| `--index` | — | The index SQLite file, given directly (does not read the server settings or the server package) |
| `--config` / `AGENT_CONSOLE_CONFIG` | `agent-console.yaml` in the current folder | Without `--index`, the location is read from the server settings: `modules.options.<log module>.index_path` (relative to the settings file folder) → the server database (`database`, default `<workspace>/.state/console.sqlite3`) |
| `--module-id` | `mod-logs` | Id of the log module whose location is read |
| `--source`, `--category` | — | Source and category ids (repeatable, all combined with AND) |
| `--before` | — | Events earlier than this time (epoch seconds or ISO 8601; local time when there is no time zone) |
| `--rescan/--no-rescan` | `--rescan` | Also clears the cursors of the sources in range so that the next collection indexes them again / keeps the cursors so that the rows do not come back |
| `--dry-run` / `--yes`, `-y` | dry-run | **Rows are deleted only with `--yes`.** Giving both is an error |
| `--all` | — | The whole index, without a range (neither a range nor `--all` is an error) |

- When the file or table does not exist, nothing is created and the exit code is 2. Exit codes: 0 success, 1 database
  error (locked and so on), 2 option, settings, or location error.
- While the server is collecting, the API (`POST /logs/index/purge`) is safer because it waits for the collection lock.
  The command line waits only for the SQLite lock.
- The server package is imported lazily from `_server` only when the server settings are read (the same path as the
  `--config` of `statusline`, so that the settings rules are not copied). With `--index`, the server package is not
  imported (the tests check `sys.modules`).

## Public API (reuse)

| Name | Description |
| --- | --- |
| `main(argv=None) -> int`, `app` (Typer) | Entry point |
| `cli_version(read=importlib.metadata.version) -> str` | The installed `agent-console-cli` version (used by `--version`; `0.0.0` without metadata) |

The internal command functions (`_server.run_serve`, `server_state_dir`, `server_log_index_path`,
`_statusline.run_statusline`, `_logs.run_purge`) are for these commands only.
Reusable logic is in `agent-console-usage` (`agent_console_usage.statusline`) and `agent-console-server`.

## Startup time

`statusline` runs every time Claude Code draws the status line. So the modules do not import the server, the client,
or the contracts (pydantic) at the top, and only `agent_console_usage.statusline` (standard library only) is read. The
`__init__` of `agent-console-usage` imports names when they are first used (PEP 562). Unit tests check `sys.modules`
after `import agent_console_cli` and after running `statusline`.
For the status line, the path of the installed `agent-console` executable is faster than `uv run`.

## Tests

```bash
uv run pytest apps/cli/tests
```

- Unit: the exposed commands (`serve`, `statusline`, `logs`), `serve` options reaching the server `main` and the
  settings (allowed origins, turning modules on and off, module-declared options), settings errors, and `statusline`
  not importing the server.
- statusline: file writes, the status line, invalid input, option errors, using the workspace from the server
  settings, and not touching `~/.claude`.
- logs purge: only with a temporary index database: dry-run by default, deleting with `--yes`, range combinations,
  requiring `--all`, option errors, not creating a missing file, the location from the server settings (`index_path`
  → server database), and not importing the server with `--index`.

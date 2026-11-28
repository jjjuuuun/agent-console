# Changelog

## Unreleased

## [1.1.1] - 2026-11-28

- Display version 1.1.1; `agent-console --version` prints `agent-console 1.1.1`. `serve` runs server 1.1.1 (the
  dependency range `agent-console-server>=1.0,<2` is unchanged). No command or option changes.

## [1.1.0] - 2026-11-28

- Display version 1.1.0; `agent-console --version` prints `agent-console 1.1.0` (read from the installed metadata).
  `serve` runs server 1.1.0 (the dependency range `agent-console-server>=1.0,<2` is unchanged).
- Raised the dependency range of `agent-console-logs` to 0.2 (`>=0.2,<0.3`).
- Terminal text is now English: the help of every command (`--help`, `serve`, `statusline`, `logs purge`), option
  errors, and the `logs purge` and `statusline` output lines (for example
  `Deleted: events 1 · token samples 0 · cursors 1 · agents 0`). Options, exit codes and behavior are unchanged.

## 1.0.0

- Display version 1.0.0. Added `agent-console --version` (prints `agent-console <version>`; the version is read from
  the installed metadata of `agent-console-cli`) and the public function `cli_version()`. Dependency range
  `agent-console-server>=1.0,<2`.
- With the presets feature removed, `serve --apply-preset` is gone (the module that declared the option,
  `mod-presets`, no longer exists). Removed it from the help and tests.
- `serve` passes its arguments as is to the server's `agent_console_server.main` (options are defined in one place, the
  server). Options that modules declare with `SettingsCompat.flags` also appear in `agent-console serve` (previously
  only `--apply-preset` was hardcoded). Options, meanings and exit codes are unchanged. Removed the internal functions
  `_server.serve_overrides`, `run_server` and `merge_origins` (now the server's `merge_origins`) and the constant
  `APPLY_PRESET_FLAG`. The description now calls it the command for running Agent Console. Test dev dependency
  `agent-console-modkit` (for declaring example modules).
- Without `--label`, `statusline` uses the short window names from data (`5h`, `7d`,
  `agent_console_usage.default_window_labels`).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
- `serve --enable-module ID --disable-module ID` (repeatable, takes priority over the setting `modules`).
- `serve --apply-preset` goes into `modules.options.mod-presets.apply_on_start` (instead of the old `presets.*`).
- `agent-console logs purge` (purges the log index; dry run by default, `--yes` deletes, and `--all` is required
  without a scope). Added the dependency `agent-console-logs` (imported lazily inside the command); the location is
  `--index` or the server settings (`_server.server_log_index_path`).

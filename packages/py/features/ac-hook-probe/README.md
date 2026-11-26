# agent-console-hook-probe

An executable that wraps a hook command and **runs it unchanged** while recording input, output, decisions, and duration as jsonl, plus the
log source and classifier that read those records.

- **It does not change the result.** stdin is passed to the original command as received, and stdout, stderr, and the exit code are returned
  byte for byte. Recording failures and disk errors do not affect the result (no warning lines are mixed into stderr either).
- **The same shell rules as Claude Code.** If what follows `--` is a single string, it runs in shell form (POSIX `/bin/sh -c`, Windows Git Bash
  `bash -c`, otherwise `powershell -NoProfile -Command`); if there are several, or with `--exec`, it runs without a shell. The shell rules are
  data (`DEFAULT_SHELLS`) and are chosen with `--shell` (`sh`, `bash`, `powershell`, `pwsh`, `cmd`, or a shell executable).
- **Termination signals are forwarded to the child group.** The child starts in a new process group, and TERM, INT, HUP, and QUIT received by the probe
  (on Windows INT, BREAK, TERM) are sent to the group; if it does not end within 2 seconds, the group is forcibly killed. When the child ends by a signal,
  the probe ends with the same signal. There is no time limit (Claude Code's hook timeout applies).
- **Records are masked copies.** Only a hash of the command string is kept (`command_digest`), and input and output only up to the first 80,000 bytes per stream
  (`--capture-bytes`). **Every field** except values the probe creates itself (`PLAIN_FIELDS`: times, exit code, sizes, and so on)
  (input and output, cwd, matcher, context, session id, tool, agent, decision reason, errors) is masked with the default rules of `agent-console-secret-rules`.
  Streams are captured up to 4 KB past the limit (`CAPTURE_MARGIN_BYTES`), masked first, and then cut at the limit, so secrets that straddle the boundary
  do not survive either (except secret shapes longer than 4 KB).
- **It is opt-in.** The platform attaches it only to the hooks it delivers itself, when `observe.hook_probe` is on.
  It does not modify `.claude` exports or user settings files.
- The package root and the run path import only the standard library (plus secret-rules when recording), because a process starts for every hook.
  The source and classifier are in the submodule `agent_console_hook_probe.plugins` (which uses `agent-console-logs`).

## Installation

```bash
uv sync --all-packages                                   # inside the workspace
pip install --find-links <wheelhouse> agent-console-hook-probe   # standalone (with the wheelhouse of internal dependencies)
```

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `agent-console-secret-rules` | Masks suspected secrets before recording | The whole platform uses the same rules | A custom regex |
| `agent-console-logs` | Source (inherits `JsonlFileSource`) and classifier protocols | Extension point | — |
| `agent-console-contracts` | Source and classifier descriptors | Single source of contracts | — |

## Minimal usage

Wrap and run one hook (here a Python script), and read the resulting record with the log index.

```python
>>> import json, subprocess, sys, tempfile
>>> from pathlib import Path
>>> from agent_console_hook_probe import wrap_command

>>> work = Path(tempfile.mkdtemp())
>>> script = work / "lint_hook.py"
>>> _ = script.write_text(
...     "import json, sys\n"
...     "sys.stdin.read()\n"
...     "print(json.dumps({'decision': 'block', 'reason': 'lint failed'}))\n",
...     encoding="utf-8",
... )
>>> out = work / "hook-probe"
>>> argv = wrap_command([sys.executable, str(script)], out=out, matcher="Edit")  # exec form
>>> payload = {"session_id": "S1", "hook_event_name": "PostToolUse", "tool_name": "Edit"}
>>> done = subprocess.run(argv, input=json.dumps(payload).encode(), capture_output=True)
>>> done.returncode, json.loads(done.stdout)        # the original hook's output, unchanged
(0, {'decision': 'block', 'reason': 'lint failed'})

>>> record = json.loads((out / "S1.jsonl").read_text(encoding="utf-8"))
>>> record["format"], record["event"], record["matcher"], record["decision"]["value"]
('hook-probe/1', 'PostToolUse', 'Edit', 'block')

>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex
>>> registries = LogRegistries()
>>> _ = registries.load(enabled_sources={"hook-probe-jsonl"}, enabled_classifiers={"hook-probe"})
>>> index = MemoryLogIndex()
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "hook-probe-jsonl", "config": {"roots": [str(work)]}}]}
... )
>>> LogIngestor(index, registries).scan(settings).new_events
2
>>> [e.title for e in index.query_events(LogFilter(), query_context(settings)).items]
['PostToolUse Edit 시작', 'PostToolUse Edit → block (exit 0)']

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Executable

```text
agent-console-hook-probe --out DIR [--matcher M] [--shell SH] [--exec]
                         [--context KEY=VALUE ...] [--capture-bytes N] -- <original command>
python -m agent_console_hook_probe ...      # the same thing
```

- Record file: `DIR/<session_id>.jsonl` (`no-session.jsonl` without a session; ids that cannot be used in file names are hashed).
  One hook run = one line. Lines are appended in one go after locking the file, so they do not mix even when several hooks write at once.
- Usage errors of the probe itself use exit code **1** (Claude Code's "non-blocking error"). It does not use 2 (block) so that
  a probe configuration mistake does not block tool calls. If the original command cannot be started, 127.
- `--context KEY=VALUE` is kept in the record's `context`. `run_id` and `node_path` (or `node`, separated by `/`) are used by the classifier as
  the event's run_id and node_path (taking precedence over values read from the path).

## Wrapping hooks directly in external Claude Code sessions

The platform does not modify the user's `settings.json`. To see hook input and output of external sessions too, **the user**
puts the probe in front of the hook command.

```jsonc
// originally: "command": "./.claude/hooks/check.sh --strict"
// shell form (the original command quoted as one argument), run the same way Claude Code ran it with a shell
"command": "agent-console-hook-probe --out ~/.agent-console/hook-probe -- './.claude/hooks/check.sh --strict'"
// or exec form (Claude Code `args` form)
"command": "agent-console-hook-probe",
"args": ["--out", "/srv/me/.agent-console/hook-probe", "--exec", "--", "./.claude/hooks/check.sh", "--strict"]
```

Then add that folder to the source roots in the log settings: `logs.sources: [{id: hook-probe-jsonl, config: {roots:
["~/.agent-console/hook-probe"], include: ["**/*.jsonl"], run_layout: false}}]`. To stop wrapping, delete only the probe part
in front of the command.

## Record format `hook-probe/1`

| Key | Meaning |
| --- | --- |
| `format` | `"hook-probe/1"` (when the format changes, the number goes up and the classifier reads each version) |
| `probe_id` | The id of one run (the `call_id` of the start and end events) |
| `event`, `session_id`, `tool_use_id`, `tool`, `agent_id`, `agent_type`, `cwd` | From the hook input (stdin JSON) |
| `matcher`, `context`, `form` (`shell`/`exec`), `shell` | From the probe arguments |
| `command_digest` | `sha256:<hex>` (the original command text is not kept) |
| `started_at`, `ended_at` (epoch seconds), `duration_ms` | Times and duration |
| `exit_code`, `signal`, `forwarded_signal`, `error` | Exit code (null + `signal` when ended by a signal), the signal the probe forwarded, the reason a run failed |
| `decision` | `{value, source, reason, updated_input, updated_output, additional_context}`; value: `block` (exit 2), `stop` (continue false), `allow`/`deny`/`ask`/`defer`, `modify` (modified input only), `none`, `error` (other exit codes, run failures) |
| `input`, `stdout`, `stdout_json`, `stderr` | Input and output (masked, size limited). An object if the input is a JSON object, otherwise text |
| `bytes`, `truncated` | Actual size per stream and whether it was cut |

## Log source and classifier

| id | Kind | Settings |
| --- | --- | --- |
| `hook-probe-jsonl` | Source (inherits `JsonlFileSource`), **on by default** (it is already platform data) | `roots` (empty = host `paths["state"]/runs`), `include` (default `**/hook-probe/*.jsonl`), `exclude`, `run_layout` (default true: run_id and node_path from the path `<run>/<node…>/hook-probe/<file>`) |
| `hook-probe` | Classifier | `category` (default `hook`), `error_category` (default `error`: non-blocking errors and run failures), `actor` (default `hook`), `probe_basis` (default `hook_probe`) |

One record line → two events (`start` and `complete`, with the same `call_id` = `probe_id`, so the index computes the duration).
With `correlation.call_id = tool_use_id`, it links to events from other sources for the same tool call (Claude Code sessions, platform runs).
Tags: `hook`, `hook:<event>`, `decision:<value>`.

## Public API

| Group | Names |
| --- | --- |
| Run | `main` (console script), `parse_args`, `ProbeUsageError`, `USAGE_EXIT_CODE`, `run_probe`, `ProbeIO`, `DEFAULT_GRACE_SECONDS`, `SPAWN_FAILED_EXIT_CODE` |
| Wrapping | `wrap_command` (argument list), `wrap_command_line` (one line for settings files), `default_probe_command` |
| Shell rules | `DEFAULT_SHELLS`, `ShellRule`, `shell_invocation`, `exec_invocation`, `default_shell_name` |
| Decisions and records | `derive_decision`, `parse_hook_output`, `BLOCKING_EXIT_CODE`, `build_record`, `RECORD_FORMAT`, `Capture`, `ProbeOutcome`, `command_digest`, `default_redactor`, `record_file_name`, `append_line`, `DEFAULT_CAPTURE_BYTES` |
| Plugins | `agent_console_hook_probe.plugins`: `HookProbeSource`, `HookProbeClassifier`, `SOURCE_ID`, `CLASSIFIER_ID` |

## Limitations

- If the probe is killed with SIGKILL, it cannot forward anything to the child (the child group may remain).
- On Windows, signal forwarding is `CTRL_BREAK_EVENT` (INT, BREAK) or terminating the child (TERM), and forced termination ends only the child itself.
  Windows paths were checked only with unit tests of the shell argument rules.
- If grandchild processes still hold stdout or stderr after the child ends, it waits until those pipes close (the same as running the original
  command directly).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work (internal dependencies via `--find-links <wheelhouse>`).

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

# agent-console-usage

The usage source extension point and collection service, the Claude Code statusLine bridge, and token totals for platform runs.

- **It never makes up values.** Usage rates, reset times, and statuses a source did not provide are `None`. Windows whose reset time has passed
  are removed from the current values (the usage rate after a reset is unknown).
- **It does not know window names.** Window ids (`five_hour` and so on) are strings the source provides, and display names are the setting
  `usage.window_labels` (data).
- **It does not know source names.** The service works only through the registry and the setting `usage.sources[{id, enabled, config}]`.
  The default sources are just the first implementations registered through entry points.
- This package neither reads nor writes `~/.claude`.

## Installation

```bash
uv sync --all-packages                     # inside the workspace
uv pip install ./packages/py/features/ac-usage      # standalone (with contracts and registry)
```

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `agent-console-contracts` | `UsageWindowSnapshot`, `UsageReport`, `TokenRollupRow`, descriptors | Single source of contracts | — |
| `agent-console-registry` | Source registry, entry point loading | Every extension point uses the same registration method | — |
| `jsonschema` | Validates source settings against the descriptor `config_schema` | The validator already used in the workspace | Dynamic pydantic models (needs schema → model conversion) |

## Minimal usage

```python
>>> import asyncio
>>> from agent_console_contracts import UsageSettings
>>> from agent_console_usage import UsageService, load_usage_sources, new_usage_sources

>>> sources = new_usage_sources()
>>> sorted(r.key for r in load_usage_sources(sources))  # entry point `agent_console.usage_sources`
['fake', 'run-events', 'statusline-file']
>>> now = 1_800_000_000.0
>>> service = UsageService(
...     sources,
...     clock=lambda: now,  # in real use, time.time
...     # events=db.events,  only latest_by_type(...) is used (a protocol, optional)
...     # state_dir=workspace / ".state",  observations=db.usage  (optional)
... )
>>> settings = UsageSettings.model_validate(  # usually workspace_settings.usage
...     {
...         "sources": [
...             {
...                 "id": "fake",
...                 "config": {
...                     "windows": [
...                         {"window": "five_hour", "used_ratio": 0.25, "resets_in_seconds": 7200}
...                     ]
...                 },
...             },
...             {"id": "run-events", "enabled": False},
...             {"id": "statusline-file", "enabled": False},
...         ]
...     }
... )
>>> report = asyncio.run(service.report(settings))  # UsageReport (pass rollups= to include token totals)
>>> [(w.source, w.window, w.used_ratio, w.resets_at - now) for w in report.windows]
[('fake', 'five_hour', 0.25, 7200.0)]
>>> [(i.descriptor.id, i.enabled) for i in service.sources(settings)]  # list[UsageSourceInfo]
[('fake', True), ('run-events', False), ('statusline-file', False)]
>>> service.prune(keep_seconds=30 * 24 * 3600)  # 0 when there is no observation store
0

```

Token totals (usable without a store):

```python
>>> from datetime import UTC
>>> from agent_console_contracts import Usage
>>> from agent_console_usage import UsageRecord, token_rollup

>>> records = [  # usually load_usage_records(db.runs, db.events, limit=500) or usage_records(run, node_runs, events)
...     UsageRecord(run_id="r1", usage=Usage(input_tokens=10, output_tokens=5), at=now, agent_id="pl"),
...     UsageRecord(run_id="r2", usage=Usage(input_tokens=1, output_tokens=2), at=now, agent_id="pl"),
... ]
>>> [
...     (row.agent_id, row.day, row.usage.input_tokens, row.usage.output_tokens, row.runs)
...     for row in token_rollup(records, by=("agent_id", "day"), tz=UTC)
... ]
[('pl', '2027-01-15', 11, 7, 2)]

```

statusLine bridge (without the server):

```python
>>> import json
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_usage import format_status_line, update_statusline_file

>>> tmp = tempfile.TemporaryDirectory()
>>> path = Path(tmp.name) / "statusline.json"  # usually .state/usage/statusline.json in the workspace
>>> stdin_text = json.dumps(  # the JSON Claude Code passes to the statusLine command (only the needed part)
...     {"rate_limits": {"five_hour": {"used_percentage": 23, "resets_at": now + 2 * 3600 + 13 * 60}}}
... )
>>> windows = update_statusline_file(path, stdin_text, now=now)  # atomic write
>>> print(format_status_line(windows, now=now, labels={"five_hour": "5h"}))
5h 23% (2h13m)
>>> tmp.cleanup()

```

## Extension point `UsageSource`

```python
class UsageSource(Protocol):
    descriptor: (
        UsageSourceDescriptor  # id, title, config_schema, trust (open string), setup_help, docs_url
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]: ...


# ctx: source_id (registry key), config, now, events (UsageEventQuery | None), state_dir (Path | None)
```

In the plugin package's `pyproject.toml`:

```toml
[project.entry-points."agent_console.usage_sources"]
my-source = "my_pkg.usage:MySource"
```

- The registry key (entry point name) is the source id. The service aligns the snapshot's `source` and the descriptor `id` to this key.
- Read failures are reported by raising. The service reports only that source as an error (`usage_source_failed`, timeout `usage_source_timeout`,
  settings error `validation_failed`) and the other sources keep running. The exception text is not put in the response (only the type name).
- `trust` is an open string. Known values are `agent_console_contracts.KnownUsageTrust` (documentation constants).
- Sources listed in the setting `usage.sources` follow their `enabled` (the user value always wins). Sources not listed are decided by the descriptor:
  if `auto_enable` and not `test_only`, on with empty settings; otherwise off (`auto_enabled`). So sources that produce values even with empty
  settings are on, and test sources are on only when listed. For an external source to be on by default, set `auto_enable=True`.
- Optional methods: `setup_values(ctx) -> {placeholder: value}` (fills the connection snippets, overriding the service's `setup_values`),
  `received_at(ctx) -> float | None` (`UsageSourceInfo.last_received_at`; otherwise the latest observation time among received snapshots).

### Source settings validation (`source_config_issues`)

Previews only the settings with the same rules as collection (descriptor `config_schema`, jsonschema). For pre-save checks and server warnings.

- `source_config_issues(settings, descriptors, *, base_path="/usage/sources", severity="error")` → `Issue[]`
  (code `usage.source_config_invalid`, `path` = JSON Pointer relative to the settings document, `details = {source, validator}`).
  Source ids not in `descriptors` (not installed, integration off) are skipped. Sources whose schema itself is wrong produce no issues.
- `UsageService.config_issues(settings, ...)`: calls the above with the sources usable right now (registry + `extra_sources`).
- `config_error(config, schema)` → `ErrorInfo | None`: the shape of `UsageSourceInfo.error` (`details.path`, `validator`).
  `sources()` shows the current settings errors of enabled sources even before collection, and fixing the settings clears the previous validation error.
  A source whose schema itself is wrong fails alone with `usage_source_schema_invalid`.
- Messages and details contain no input values or schema text (only locations and keyword names).

```python
>>> from agent_console_contracts import UsageSettings, UsageSourceDescriptor
>>> from agent_console_usage import source_config_issues
>>> d = UsageSourceDescriptor(id="s", title="s", trust="estimated",
...     config_schema={"type": "object", "additionalProperties": False})
>>> [i.path for i in source_config_issues(
...     UsageSettings.model_validate({"sources": [{"id": "s", "config": {"x": 1}}]}), {"s": d})]
['/usage/sources/0/config']

```

### Sources outside the registry (`extra_sources`)

`UsageService(..., extra_sources=)` accepts sources that are not entry points (for example, runtime sources another module provides through a port).
The value is `{id: source}` or a function that returns it (read again on every call).

- They are appended after registry sources in id order, and enabling, settings validation, and error reporting work the same as for registry sources.
- When an id overlaps a registry source, **the registry wins**. Get the overlapping ids with `service.conflicts()`; a warning log
  (`agent_console_usage`) is written once per id.

## Default sources

| id | What | trust | Data (`data/sources.json`) | config |
| --- | --- | --- | --- | --- |
| `run-events` | The latest value per window from the run event `usage.rate_limit` (SDK `RateLimitEvent`) | official | `auto_enable`, window names | `event_type` (default `usage.rate_limit`), `scan_limit` (default 200) |
| `statusline-file` | The file `agent-console statusline` writes (or a file of raw statusLine input) | official | `auto_enable`, `needs_setup`, window names, `setup_help`, `setup_snippets` | `path` (default `usage/statusline.json`; relative paths are relative to `<workspace>/.state`) |
| `fake` | Only the windows written in the settings, as is (E2E, screen checks) | `fake` | `test_only` | `windows[{window, used_ratio?, used_tokens?, status?, resets_at? \| resets_in_seconds?, observed_at? \| observed_seconds_ago?}]` |

`fake` is installed through an entry point too (the same way as the `fake` backend). It is `test_only`, so it is on only when listed in `usage.sources`.
Window names (`windows[{id, title, short_title}]`) are screen fallbacks, and the user's `usage.window_labels` takes precedence.

## Connecting the Claude Code statusLine (done by the user)

This program does not modify the Claude Code settings (`~/.claude`). To see the 5-hour and 7-day usage rates of interactive Claude Code,
paste one of the snippets below into **your own** settings or script. The snippets live in one place, the package data `data/sources.json`,
and the server publishes the same data as `setup_snippets` of the `statusline-file` descriptor in `GET /usage/sources` (placeholders
`{output_path}` = absolute path of `.state/usage/statusline.json` in the workspace, `{agent_console_cmd}` = absolute path of `agent-console`).
The output below is generated from that data (a doctest: if you change the data, this README must change too for the test to pass).

```python
>>> from agent_console_usage import StatuslineFileSource, fill_setup_snippets
>>> values = {"output_path": "/srv/me/agent-console/.state/usage/statusline.json",
...           "agent_console_cmd": "/srv/me/.local/bin/agent-console"}
>>> for s in fill_setup_snippets(StatuslineFileSource.descriptor.setup_snippets, values):
...     print(f"[{s.title} · {s.shell or '공통'}]\n{s.text}\n")
[상태 줄이 아직 없어요 · 공통]
{
  "statusLine": {
    "type": "command",
    "command": "/srv/me/.local/bin/agent-console statusline --output /srv/me/agent-console/.state/usage/statusline.json"
  }
}
<BLANKLINE>
[이미 다른 상태 줄 스크립트를 써요 · bash]
# 기존 스크립트에서 입력을 변수에 담은 줄(예: input=$(cat)) 바로 아래에 붙입니다.
# 입력을 변수에 담지 않는 스크립트라면 맨 위에 input=$(cat)을 넣고, 아래 명령들이 "$input"을 읽게 바꿉니다.
printf '%s' "$input" | /srv/me/.local/bin/agent-console statusline --output /srv/me/agent-console/.state/usage/statusline.json >/dev/null 2>&1 || true
<BLANKLINE>
[이미 다른 상태 줄 스크립트를 써요 · powershell]
# 기존 스크립트에서 입력을 변수에 담은 줄(예: $raw = $input | Out-String) 바로 아래에 붙입니다.
$raw | & '/srv/me/.local/bin/agent-console' statusline --output '/srv/me/agent-console/.state/usage/statusline.json' | Out-Null
<BLANKLINE>

```

- Snippets with the same `title` are the same situation (a tab on the screen) and are chosen by `shell`. Values are quoted to fit the shell or language
  (paths with spaces can be pasted as is, `fill_setup_text`).
- If you already keep the statusLine input in a file (for example `echo "$input" > ~/.cache/claude-usage/statusline.json` in an existing script),
  listing only `usage.sources[{id: statusline-file, config: {path: <absolute path of that file>}}]` is enough. This source reads both bridge files and
  raw statusLine input files (`load_statusline_windows`), and uses only `rate_limits` from raw input.
- Without `--label`, `agent-console statusline` builds the line from the short window names in the data (`5h`, `7d`) (`default_window_labels`).
- `rate_limits` arrive only on Pro/Max subscriptions and only after the first response of a session. Windows can be missing individually. Without values, the status line is
  empty (or the `--empty` text) and the file is left as is.
- Using `--config` instead of `--output` makes startup a little slower because it reads the server settings. The status line runs often, so `--output` is recommended.
- Input format: <https://code.claude.com/docs/en/statusline>
- The package `__init__` imports names on first use (PEP 562). Importing only `agent_console_usage.statusline` does not load
  the contracts (pydantic) or the registry, so the status line command starts fast (`tests/test_agent_console_usage_lazy_init.py`).

### Bridge file format (`format` = 1)

```json
{"format": 1, "updated_at": 1738420000.0,
 "windows": {"five_hour": {"observed_at": 1738420000.0, "used_percentage": 23.5, "resets_at": 1738425600, "data": {"used_percentage": 23.5, "resets_at": 1738425600}}}}
```

- Only `rate_limits` from the input are kept (cwd, session_id, transcript_path, and so on are not written).
- Merged per window: windows missing from the new input keep their previous observation (with their own `observed_at`), and windows whose reset time has passed are removed.
- Writes go to a temporary file in the same folder → `os.replace` (atomic). A corrupt file is rewritten from the new input.
- **There is no file lock.** Read → merge → write is not locked, so when several Claude Code sessions run the status line command at almost the same time,
  the later writer can overwrite windows the earlier one merged (last write wins). The file is never seen half
  written (atomic replace); what is lost is one window observation from that moment, and the next run fills it again.
  The status line runs often and briefly, so this avoids a status line stalled by lock waits (or stale lock files). Usage rates are per-account
  values, so whichever session writes, the latest value of the same window remains.

## Token total rules

- Inputs: NodeRun `usage` (the final value of a node attempt) + `agent.subagent_stopped.usage` (delegates).
- Agent and model: the actor and `model` of `agent.session_started` with the same node (`node_path == [node_id]`) and the same attempt.
  `None` if not found (never guessed from neighboring events in time). The model of a delegate is unknown (`None`).
- Sums: per field, only present values are added. Fields that nobody provided are `None` (not filled with 0).
- `precision`: when a row has only total tokens, `total_only`; when only partial, the `mixed` text (replace it with `precision_text`).
- Dimensions: `agent_id`, `graph_id`, `model`, `day` (`TokenRollupRow` fields). `day` uses the time zone passed in.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-usage`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-usage/tests
```

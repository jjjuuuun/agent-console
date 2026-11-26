# agent-console-link-logs-usage

Logs and usage link module. It adds the usage source `local-logs` (trust level `estimated`), which **estimates** usage windows from the
per-response token samples of the log index (`logs.query` of `mod-logs`), to the optional multi port `usage.sources` of `mod-usage`.

- Window definitions, budgets, filters, and the token kinds to count are **usage settings data** (`usage.sources[{id: local-logs, config}]`).
  Omitted keys use the default data `data/local_logs_defaults.json` (replace it with the administrator option `defaults_file`).
  The code has no log source ids or window lists.
- The calculations are `block_windows` (ccusage-style blocks: the time of the first message rounded down to the hour, for the block length;
  later messages start a new block) and `rolling_totals` (moving windows) from `ac-logs`.
- Only samples in the log index exist, so in the app **only sessions of registered projects are counted** (log sources collect only under
  registered project folder keys). Usage from folders that are not registered is not part of the estimate.
- **No values are made up.** Without a budget, `used_ratio` is null (the limit denominator is not public). When none of the samples has the token kinds
  to count, `used_tokens` is null. When the query range has no samples, no window is returned.
- The sample cache is dropped on `logs.ingested` (newly indexed logs), only for entries that read that log source.
- When this link is off (or when `mod-logs` or `mod-usage` is off), the usage source list has no `local-logs`.
- `local-logs` is `auto_enable` (on even without usage settings). The window names (`windows`) are the window
  `title` and `short_title` in the default data.

## Turning on log sources found on this computer

`local-logs` returns values only when the log index has samples. The Claude Code session log source (`claude-code-jsonl`) copies conversation text
into the index, so its descriptor is off by default. This link turns that source on as a read-only default source **when its log folder exists
on this computer** (port `logs.source_defaults`, applied by `mod-logs`).

- The rules are data, `data/auto_log_sources.json` (`[{id, path, env?, env_subpath?}]`). `~` in `path` is the `HOME` of the injected
  environment, and when the `env` environment variable is set, only `env_subpath` under it is checked (the same rule as the source's default root).
- It only checks whether the folder exists. It writes nothing to that folder or to `~/.claude`, and it does not change any settings file.
- When the user sets `logs.sources[{id, enabled}]` (including turning it off), that value wins. To turn it off, use `enabled: false`.
- When this link, `mod-logs`, or `mod-usage` is off, nothing is turned on automatically. The administrator option `auto_enable_log_sources: false` also turns it off.
- The logs screen can show such a source as "default (automatic)" by looking at `enabled: true` in `GET /logs/sources`, the descriptor's `default_enabled: false`, and the absence of
  `enabled` in the settings.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_logs_usage import load_auto_log_sources, log_source_defaults
>>> home = Path(tempfile.mkdtemp())  # a fake home (in a real setup, HOME of the server environment)
>>> rules = load_auto_log_sources()  # package data
>>> log_source_defaults(rules, {"HOME": str(home)})
{}
>>> (home / ".claude" / "projects").mkdir(parents=True)
>>> log_source_defaults(rules, {"HOME": str(home)})
{'claude-code-jsonl': True}

```

Waiting for the first query: when `logs.ingest` is present, the **first** query of `local-logs` waits up to `first_scan_wait_seconds` (default 5 seconds) for the collection
of the log sources it reads (or for the startup collection, when it is still running). So the first `GET /usage` right after the server starts returns values too. When the wait
runs out, it answers from the current index and the collection continues in the background.

## Install

```bash
pip install agent-console-link-logs-usage
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-logs-usage
```

| Dependency | What | Why | Alternative |
| --- | --- | --- | --- |
| `agent-console-logs` | `LogFilter`, `parse_log_filter`, `block_windows`, `rolling_totals` | Window calculation and filter parsing match the log core | Own implementation (duplicate) |
| `agent-console-usage` | `UsageSource` protocol, `UsageSourceContext` | The shape of a usage source | — |
| (dev) `agent-console-logs-claude` | Checks automatic enabling and the first query with the real Claude Code log source (fake home) | Verifies the default root rule of the real source as well | A synthetic source (cannot verify the path rule) |

## Minimal usage

Without a server: inject a token sample query (an object with only `token_samples(flt)`) and use it as a source.

```python
>>> import asyncio
>>> from agent_console_contracts.logs import TokenSample
>>> from agent_console_usage import UsageService, new_usage_sources
>>> from agent_console_link_logs_usage import LocalLogsUsageSource
>>> from agent_console_link_logs_usage.testing import SampleQuery
>>> h0 = 1_800_000_000.0  # on the hour
>>> query = SampleQuery(  # in a real setup, logs.query of mod-logs
...     [TokenSample(message_id="m1", time=h0 + 600, input_tokens=40, output_tokens=10)],
...     source="my-logs",
... )
>>> service = UsageService(
...     new_usage_sources(),
...     clock=lambda: h0 + 3600,
...     extra_sources={"local-logs": LocalLogsUsageSource(query)},
... )
>>> from agent_console_contracts import UsageSettings
>>> settings = UsageSettings.model_validate(
...     {"sources": [{"id": "local-logs", "config": {
...         "filter": {"source": "my-logs"},
...         "budgets": {"local_five_hour": 200},
...     }}]}
... )
>>> [(w.window, w.used_tokens, w.used_ratio, w.resets_at and w.resets_at - h0)
...  for w in asyncio.run(service.collect(settings))]
[('local_five_hour', 50, 0.25, 18000.0), ('local_seven_day', 50, None, None)]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Settings (`usage.sources[{id: local-logs, config}]`)

| Key | Shape | Default (data) |
| --- | --- | --- |
| `windows` | `[{id, kind: block\|rolling, hours? \| days?, title?, short_title?}]` | `local_five_hour` (block 5h), `local_seven_day` (rolling 7d) |
| `budgets` | `{window id: token count}`; when set, `used_ratio = used_tokens / budget` | `{}` |
| `filter` | Log query filter (`source`, `project`, `model`, …; not `since`, `until`, `limit`, `cursor`, `order`) | `{source: [claude-code-jsonl]}` |
| `count` | Token kinds to count (`input`, `output`, `cache_creation`, `cache_read`) | All four |
| `lookback_hours` | The past range read to find block boundaries (the window length when shorter than it) | 168 |

- Settings override per top-level key (setting `windows` replaces the whole default window list).
- Snapshot: for `block`, when a block is open now, the total, `resets_at` (block end), and `status: active`; otherwise `used_tokens: 0` and
  `status: idle`. For `rolling`, the total of `now - length <= t <= now` (no `resets_at`). `observed_at` is the time of the last sample in the range
  (the log time; when it is the same value, no new observation is recorded). `raw` has the token breakdown, block start, sample count, and budget.
- Limit: block boundaries are found only from the samples within `lookback_hours` (for usage that continued without a break for longer than that, the
  boundaries can differ from ccusage).

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `logs.query` | `token_samples(LogFilter) -> Sequence[TokenSample]` (`LogTokenQuery`) |
| Required | `usage.service` | Presence check only (when the usage module is off, this link is off too) |
| Subscribes | `logs.ingested` | Invalidates the sample cache by `source_ids` |
| Optional | `logs.ingest` | `scan(source_ids)` (waiting for the first query) |
| Provides | `usage.sources` (multi) | `LocalLogsUsageSource` (`UsageSource`) |
| Provides | `logs.source_defaults` (multi) | `() -> {log source id: True}` (only rules whose folder exists) |

Administrator options (`modules.options.link-logs-usage`): `source_id` (default `local-logs`; when it collides with a plugin source, it is left out and
`mod-usage` warns `usage.source_conflict`), `defaults_file` (default values JSON; a relative path is relative to the settings file folder),
`auto_enable_log_sources` (default true), `auto_log_sources_file` (automatic enabling rules JSON), and `first_scan_wait_seconds` (default 5).

## Standalone run

```bash
python -m agent_console_link_logs_usage [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_logs_query_module` (no samples) and `testing.local_usage_module` (a placeholder).
To start it with the real routes: `--with mod-logs --with mod-usage`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

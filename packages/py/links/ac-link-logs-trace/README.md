# agent-console-link-logs-trace

Logs and trace link module. It builds a delegation flow (`Trace`) from the session events of the log index (`logs.query`).
It has the same shape as the run history flow (`link-runs-trace`), so the web app uses the same drawing
component (`trace-view`).

- `GET /logs/sessions/{session}/trace` → `Trace` (`run_id` = session id).
- When this link is off, the route returns 404 and the web app hides the delegation flow drawing on the session screen, showing only
  the table and timeline (web role `logs:trace`).

## Linking rule: explicit ids only

The same as `ac-trace`. Events that are close in time are not linked as cause and effect; without a link key, a span stays without a parent.

| Relation | Link key |
| --- | --- |
| Span | One event `thread` (agent line) = one span (`thread:<line id>`) |
| Parent | When `correlation[<link key>]` of an event in line S equals the `call_id` of an event in a **different** line T, T is the parent (delegation call id ↔ subagent metadata `toolUseId`). With two or more candidates, or a cycle, there is no parent |
| Link | Events with `from` and `to`: sending line → receiving line (only when both sides have a line). The same call id in the same direction is merged into one. `edge_id` = call id, `kind` = `via` |

- A span with a parent has the kind `delegated` (`tool_use_id`; the summary of the received event = `task_preview`; the summary and status of the
  `complete` event with the same call id in the parent line = `result_preview` and `status`). Otherwise it is `thread`.
- Hidden categories are read too (link evidence does not depend on display settings). Only the original timestamps are used (null when missing).

## Install

```bash
pip install agent-console-link-logs-trace
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-logs-trace
```

## Minimal usage

Without a server, pass events to `build_log_trace` (in a real setup, the list from `logs.query.events`).

```python
>>> from agent_console_contracts.logs import LogEvent
>>> from agent_console_link_logs_trace import build_log_trace
>>> def ev(seq, thread, **more):
...     return LogEvent.model_validate({"uid": f"u{seq}", "seq": seq, "source": "demo",
...         "observed_at": 0.0, "category": "other", "thread": thread, "session": "s1",
...         "time": float(seq), **more})
>>> trace = build_log_trace([
...     ev(1, "main", call_id="c1", stage="start", via="Task", **{"from": ["main"]}, to=["sub"]),
...     ev(2, "sub", correlation={"tool_use_id": "c1"}, summary="검토해 줘"),
...     ev(3, "sub"),  # lines that are only close in time, without a link key, are not linked
...     ev(4, "lonely"),
... ])
>>> [(s.id, s.kind, s.parent_id) for s in trace.spans]
[('thread:main', 'thread', None), ('thread:sub', 'delegated', 'thread:main'), ('thread:lonely', 'thread', None)]
>>> [(link.source, link.target, link.kind) for link in trace.links]
[('thread:main', 'thread:sub', 'Task')]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

To build it from the index, use `LogTraceViews(query).trace(session)` (`query` has the shape of `logs.query`;
only `events(LogFilter)` is used).

## Ports and settings

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `logs.query` | `events(flt: LogFilter, *, with_total=False) -> LogEventPage` (keyset pages) |

Settings `modules.options.link-logs-trace`:

| Key | Default | Meaning |
| --- | --- | --- |
| `link_keys` | `["tool_use_id"]` | The `correlation` names used to find parents (change them when a log format uses different names) |
| `max_events` | `20000` | Upper limit on the events read from one session (when exceeded, only the first part is drawn) |

## Standalone run

```bash
python -m agent_console_link_logs_trace [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_logs_module` (an empty in-memory index; pass another index with `index=`).
For real logs, start it together with the logs module: `--with mod-logs`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work. The test fixture
`tests/data/claude_config` is a copy of the ac-logs-claude synthetic fixture (refresh the snapshots with `UPDATE_SNAPSHOTS=1`).

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

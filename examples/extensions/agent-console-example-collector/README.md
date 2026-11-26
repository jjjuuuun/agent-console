# agent-console-example-collector

An example that adds a new **observation collector** with a single plugin package.
No engine, server, web, or backend code changes. Once installed, it appears in the collector list of the claude-sdk backend
(`collectors` of `GET /api/v1/backends`), and it disappears when removed.

Collector `example.tool_count` (tool call count)
- During one run, it counts the tool call blocks of model responses by tool name (per-run state `ctx.state`).
- On the run's result message, it emits the event `example.tool_count{total, by_tool}` once. The backend publishes it as a generic RunEvent,
  so it shows up as it is on the run screen and the logs screen (source `platform-runs`).
- The setting `only` (the list of tool names to count; empty = all) is the pydantic model `ToolCountConfig`. The descriptor's `config_schema` is
  that schema, and a wrong setting shows up as the validation warning `observe.collector_config_invalid`.
- It does not interfere with the run. The backend swallows exceptions and leaves one warning event per run.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

Subclass `BaseClaudeSdkCollector` and override only the methods you need. Below, SDK messages are fed directly to the run part `CollectorRun`
(in a real setup, the backend feeds them).

```python
>>> import asyncio
>>> from typing import ClassVar
>>> from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock
>>> from agent_console_backend_claude_sdk.collectors import (
...     BaseClaudeSdkCollector, CollectorContext, CollectorRun, resolve_collector_settings,
... )

>>> class ToolCount(BaseClaudeSdkCollector):
...     id: ClassVar[str] = "tool-count"
...     title: ClassVar[str] = "도구 호출 수"
...     emits: ClassVar[tuple[str, ...]] = ("tool.count",)
...     default_backend: ClassVar[str] = "claude-agent-sdk"
...     def on_message(self, message: object, ctx: CollectorContext) -> None:
...         if isinstance(message, AssistantMessage):
...             n = sum(isinstance(b, ToolUseBlock) for b in message.content)
...             ctx.state["n"] = ctx.state.get("n", 0) + n
...         elif isinstance(message, ResultMessage):
...             ctx.emit("tool.count", {"count": ctx.state.get("n", 0)})

>>> sent = []
>>> async def out(event):
...     sent.append((event.type, dict(event.payload)))
>>> async def warn(warning):
...     sent.append(("log.warning", warning.details))
>>> run = CollectorRun(
...     [ToolCount()],
...     resolve_collector_settings({"collectors": {"tool-count": {"enabled": True}}}),
...     clock=lambda: 0.0, redact=lambda v: v, out=out, warn=warn,
... )
>>> calls = AssistantMessage(content=[ToolUseBlock(id="t1", name="Read", input={})], model="m")
>>> done = ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
...                      num_turns=1, session_id="s")
>>> for message in (calls, done):
...     asyncio.run(run.on_message(message))
>>> sent
[('tool.count', {'count': 1})]

```

The real implementation is `src/agent_console_example_collector/tool_count.py` (settings model, counts by name, pure functions
`count_tool_uses` and `merge_counts`). Below, that implementation is discovered as if it were registered as an entry point.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_backend_claude_sdk.collectors import COLLECTORS_GROUP, discover_collectors
>>> ep = EntryPoint(
...     "example.tool_count", "agent_console_example_collector:ToolCountCollector", COLLECTORS_GROUP
... )
>>> found, reports = discover_collectors("claude-agent-sdk", entry_points=[ep])
>>> [c.descriptor.id for c in found]          # when installed, call it without the entry_points argument
['example.tool_count', 'sdk-hooks', 'mcp-calls']
>>> found[0].descriptor.config_schema["properties"]["only"]["title"]
'셀 도구'

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Registration and settings

```toml
[project.entry-points."agent_console.collectors"]   # agent_console_backend_claude_sdk.collectors.COLLECTORS_GROUP
"example.tool_count" = "agent_console_example_collector:ToolCountCollector"
```

A backend uses only the collectors whose `descriptor.backend` (default `claude-agent-sdk`) is its own id. To use it with a claude-sdk
backend instance that has another id, pass `ToolCountCollector(backend="<id>")` to `ClaudeSdkBackend(collectors=[...])`.

Agent, team, and common settings (`observe`; when omitted, the settings above are inherited). Collectors that are not configured are off.

```yaml
observe:
  collectors:
    example.tool_count:
      enabled: true
      config:
        only: [Bash, Edit]     # empty = all
```

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-collector   # install
uv pip uninstall agent-console-example-collector                        # remove
```

**Restart the server** after installing or removing.
- Install: `example.tool_count` appears in `collectors` of the claude-sdk entry of `GET /api/v1/backends`. When you run with the settings above,
  one `example.tool_count` event appears at the end of the run.
- Remove: it disappears from the collector list. `observe.collectors.example.tool_count` stays in the settings, but it only produces the validation warning
  `observe.unknown_collector`, and runs work as before (checked by the tests).
- Turn off while installed: set `enabled: false` (or delete the entry).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

```bash
cd examples/extensions/agent-console-example-collector
uv run --project ../../.. python -m pytest
```

The tests run without installing (`pythonpath = ["src"]`). The SDK is replaced by an injected fake client (`agent_console_backend_claude_sdk.testing.FakeSdkClient`),
so there are no model calls. The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).

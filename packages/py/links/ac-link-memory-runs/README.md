# agent-console-link-memory-runs

Agent Console memory and runs link module (`link-memory-runs`). It gives agents shared memory tools (search, read, write, delete).
The runs module (`mod-runs`) and the memory module (`mod-memory`) do not know each other; this link connects them by adding an agent tool
provider (`TOOL_PROVIDERS`) to every run through the run scope (`runs.scopes`).

| What | Details |
| --- | --- |
| Received port (required) | `memory.service` (`mod-memory`). Without it this link is off |
| Provided ports | `runs.scopes` (a memory tool provider per run), `definitions.checks` (an unknown scope kind in a memory resource → warning `memory.unknown_scope_kind`) |
| Resource type | `memory` (entry point `agent_console.resource_types`, package data `data/memory_resource_type.yaml`, settings schema = contract `MemoryAccessConfig`; the scope kind field uses the `x-ui` widget `memory-scope-kind`) |
| Run events | `memory.read`, `memory.search`, `memory.write`, and `memory.delete` per tool call (payload = contract `MemoryEventPayload`: scope, key, id, version, byte count, hash, result count, search text length and hash, tool name, `tool_use_id`, duration. **No content or search text**) |
| Administrator option | `modules.options.link-memory-runs.max_writes_per_run` (default 200; empty = no limit; above it, `rate_limited`) |
| Web role | `memory:runs` (the memory chip in the run detail) |

- **Opt-in**: only agents with a `memory` resource attached get the tools. Tool names, descriptions, result header lines, and permissions per scope are
  the resource config (data). The `delete` tool is given only when some scope allows deleting.
- **Layers**: when the same slot has several attachments (common → team → agent → node), the allowed actions of the closest layer are used for each scope kind.
  For the other keys (default scope, tool names, and so on), the value set by the closest layer also wins (`merge_access`;
  the rule is the same `agent_console_nodes_core.merge_access_layers` as the wiki link).
- **Scope ids** are computed from the context (`MemoryAccessContext`). `graph_id` is the team of the run that ran the node
  (the child team for a nested team); `root_graph_id` and `project_id` are values of the root run. Agents cannot choose scope ids.
- **The write limit per run** is shared by all agents of one run (including child runs).
- **Turning it off**: when `mod-memory` or this link is off, runs still finish, and each node with a memory resource attached gets one
  "slot the backend could not apply" warning (`resource.slot_unsupported`). While this package is installed, the resource type stays registered
  even with the link off (you can still create the resources).
- Memory content can be read by other agents as if it were instructions (it is not a security boundary). Narrow write permissions with the resource.

## Dependencies: what, why, alternatives

- In-house: `agent-console-memory` (tool set, scope kinds), `agent-console-nodes-core` (provider protocol, service
  keys), `agent-console-runtime` (`HostTool`), `agent-console-resources` (resource type base),
  `agent-console-store` (definition kind name `resource`), `agent-console-modkit` (module).
- External: pydantic, ruamel.yaml (descriptor data). No new external dependencies.

## Install

```bash
pip install agent-console-link-memory-runs
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-memory-runs
```

## Minimal usage

Without a server or a run engine, build the tools from one provider and call them (the memory service is injected).

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_memory import merge_scope_kinds
>>> from agent_console_nodes_core import ToolProvisionContext
>>> from agent_console_runtime import CancelToken
>>> from agent_console_link_memory_runs import MemoryToolProvider
>>> from agent_console_link_memory_runs.testing import StaticMemoryService
>>> service = StaticMemoryService(catalog=merge_scope_kinds(
...     include_defaults=False, user={"notes": {"label": "노트", "id": "{/graph_id}"}}))
>>> events = []
>>> async def emit(event_type, payload):
...     events.append((event_type, payload["status"], payload["scope"]))
>>> config = {"scopes": [{"kind": "notes", "access": ["read", "write"]}],
...           "tools": {"write": {"name": "jot", "description": "기록을 남깁니다"}}}
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="a", node_path=["a"],
...     agent_id="a", call=0, iteration=0,
...     bundle=ResourceBundle(slots={"memory": [{"config": config}]}),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken())
>>> provision = MemoryToolProvider(lambda: service, slot="memory").provide(ctx)
>>> [t.name for t in provision.host_tools], sorted(provision.consumed_slots)
(['memory_read', 'jot'], ['memory'])
>>> asyncio.run(provision.host_tools[1].handler({"key": "결정", "content": "v2"})).is_error
False
>>> events
[('memory.write', 'ok', {'kind': 'notes', 'id': 'team'})]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Standalone run (with an in-memory memory service module): `python -m agent_console_link_memory_runs --check`.
With the real modules: `--with mod-memory --with mod-runs`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

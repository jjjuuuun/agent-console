# Memory

Shared memory is a record that agents read and write during runs. Scope kinds (what to divide the record by) are
defined by data and plugins ([memory-scope-kind](#memory-scope-kind)), and the store is replaced by injection
([memory-store](#memory-store)). Memory tools reach agents through the general tool provider point
([agent-tool-provider](#agent-tool-provider)). Wiki tools use the same point.

## agent-tool-provider

**When to use**: to add tools and instructions when an agent node calls the model. Features such as memory and the
wiki use this point to "give tools only to the agents that use this feature". The agent node does not know what the
tools mean.

**Minimal shape**: an object with `id` and `provide(ctx) -> ToolProvision`. `ToolProvision` has `host_tools` (the
tool list), `consumed_slots` (the bundle slots it handled), `warnings`, and `instructions` (instruction text). Put it
in the node service `TOOL_PROVIDERS` (a list) for each run. In the server, a run scope ([run-scope](projects.md#run-scope))
puts it there.

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_nodes_core import ToolProvisionContext, provide_tools
>>> from agent_console_nodes_core.testing import EchoToolProvider
>>> from agent_console_runtime import CancelToken
>>> async def emit(event_type, payload):
...     pass
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="pl", node_path=("pl",),
...     agent_id="pl", call=0, iteration=0, bundle=ResourceBundle(),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken(),
... )
>>> merged = provide_tools([EchoToolProvider("echo", tool_name="echo", instructions=["echo로 확인하세요."])], ctx)
>>> [tool.name for tool in merged.host_tools], list(merged.instructions)
(['echo'], ['echo로 확인하세요.'])

```

**Rules**
- `provide` is called synchronously, once per node, before the backend is called. Do heavy work such as store queries
  when a tool handler is called.
- Opt in through bundle slots (`ctx.bundle`). Give tools only to agents that have the feature's resource attached, and
  list the slots you handled in `consumed_slots` so they are removed from the backend request.
- You can emit events under your own prefix with `ctx.emit` for each tool call. Do not put content or raw search
  terms in the payload (only sizes, hashes, and status).
- Warning codes: `tools.provider_failed` for exceptions and invalid results (only that provider is skipped),
  `tools.duplicate_name` for name collisions, `tools.backend_capability_missing` when the backend does not accept host
  tools, and `tools.instructions_unsupported` when it does not accept the instructions slot. In every case the run
  continues.

**Common mistakes**: giving tools to every agent (it creates behavior the user did not turn on), putting secret values
in exception messages (the warning keeps only the exception type name, but the message can end up in logs), and using
the same tool name as another provider.

**Turning off**: when you turn off the run scope (link module) that adds the provider, the tools drop out. Runs go
ahead without the tools.

<!-- extdocs:facts agent-tool-provider -->
- Registration: Registration kind `service`.
- Interface:
  - `agent_console_nodes_core:ToolProvider` — Provider that supplies tools for each agent node run.
  - `agent_console_nodes_core:TOOL_PROVIDERS` — Service key. The same `name` means the same key (the type argument is for static checks).
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
  - contract-tests: `agent_console_nodes_core.testing:EchoToolProvider`
<!-- /extdocs:facts -->

## memory-scope-kind

**When to use**: to add or change the units that divide memory (per team, per project, shared by everyone, and so
on). If the scope id can be derived from values of the run information (the access context), user settings are
enough. To derive it from values outside the context, such as the current time, publish a computed scope kind with a
plugin.

**Adding with data**: the `memory` section of the workspace settings. The keys are scope kind ids, and `id` is a JSON
pointer template over the access context.

```yaml extdocs:validate=agent_console_contracts.memory:MemorySettings
include_default_scope_kinds: true
scope_kinds:
  team-notes:
    label: 팀 노트
    description: 팀 구성마다 따로 두는 기록
    id: "{/graph_id}"
  board:
    label: 공용 게시판
    id: ""
```

**Adding with a plugin**: the entry point value is a function without arguments that returns a list of
`MemoryScopeKind` (computed scopes provide a `resolver`) or a data dictionary like the one above. For a full example,
see the [memory scope example](../../examples/extensions/agent-console-example-memory-scope/README.md).

**Rules**
- The merge order is package defaults (when `include_default_scope_kinds` is set) → plugins → user settings. The same
  id replaces the whole entry, and `null` turns it off.
- When the resolved template is empty, that scope cannot be used in that run (`memory.scope_unavailable`). An empty
  template (`id: ""`) means there is only one scope.
- The context fields (`graph_id`, `agent_id`, `run_id`, `project_id`, and so on) are defined by the contract
  `MemoryAccessContext`. Pointing to a field that does not exist always gives an empty value.
- `resolver` takes the access context and returns a scope id. When the scope cannot be used, it returns `None` (an
  exception is treated as `None` too).

**Common mistakes**: changing a scope kind id (records already written stay under the old id and are not visible
under the new one), and putting human-readable names in the scope id template (the template is a key that divides
values).

**Turning off and leftover data**: turning off a scope kind or removing the plugin does not delete the records of
that scope. If the access settings of a memory resource point to a kind that does not exist, a
`memory.unknown_scope_kind` warning is attached and only that scope cannot be used.

<!-- extdocs:facts memory-scope-kind -->
- Registration: Register in the entry point group `agent_console.memory_scope_kinds` (constant `agent_console_memory:MEMORY_SCOPE_KINDS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_memory:MemoryScopeKind` — One scope kind (an entry in the merged list).
- Settings: `memory.scope_kinds`, `memory.include_default_scope_kinds`
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-memory-scope](../../examples/extensions/agent-console-example-memory-scope/README.md)
  - snippet: Data in the user setting `memory.scope_kinds`
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## memory-store

**When to use**: to keep memory in another store (an in-house DB, a remote service). It is also where you plug in your
own store when you use the memory library in another agent framework without the server.

**Minimal shape**: implement the `MemoryStore` protocol (write, read, find, history, delete, purge, search) and pass
it to the constructor of the consumer (`MemoryToolkit`, the memory module's service). The in-memory implementation
`InMemoryMemoryStore` and the SQLite implementation (`agent_console_memory.sqlite`) are models to follow.

```python
from agent_console_memory.testing.contract import MemoryStoreContractTests


class TestMyStore(MemoryStoreContractTests):
    def make_store(self, *, policy=None, clock=None):
        return MyStore(policy=policy, clock=clock)
```

**Rules**
- Methods are synchronous and must be safe to call from threads.
- Every write raises the version and leaves a history entry. When `if_version` does not match, it is a
  `VersionConflictError` (`memory.conflict`). Writes to the same entry are serialized.
- Delete only marks the entry; only purge (`purge`) removes the versions as well.
- Key rules, size limits, and secret checks are defined by the policy (`MemoryPolicy`). Implementations follow the
  policy they receive as it is.
- Check that the meaning is the same with the contract test suite `MemoryStoreContractTests`
  ([Testing](testing.md#3-contract-test-suites)).

**Common mistakes**: searching only the content (the contract suite checks that keys, content, and tags are searched
case-insensitively), and keeping history versions after a purge.

**In the server**: the memory module uses the SQLite implementation on the host DB as the app library store (without
a DB, process memory plus a `memory.storage_memory` warning). The store for each project space is decided by the link
module that provides the port `memory.spaces`. To plug another store into the server, write a link that provides that
port.

<!-- extdocs:facts memory-store -->
- Registration: Inject an implementation through a constructor or an argument (an object that follows the interface).
- Interface:
  - `agent_console_memory:MemoryStore` — Memory store. Methods are synchronous and must be thread-safe.
- Built-in implementations: —
- Examples:
  - contract-tests: `agent_console_memory.testing.contract:MemoryStoreContractTests`, `agent_console_memory:InMemoryMemoryStore`
- Turning it off or removing it: Without an injected implementation, the default implementation is used.
<!-- /extdocs:facts -->

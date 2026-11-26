# agent-console-example-memory-scope

An example that adds a new **memory scope kind** with a single plugin package.
No engine, server, or web code changes. Once installed, it appears in the scope kind list (`GET /api/v1/memory/scope-kinds`)
with `origin: plugin:agent-console-example-memory-scope`, and it disappears when removed.

Scope kind `example-week`, a **computed scope kind**
- The scope id is the ISO week `{year}-W{week}` (for example `2026-W44`; two-digit week, the ISO week-numbering year, in UTC).
- Data scope kinds (id templates such as `{/project_id}` in `memory.scope_kinds`) read only values of the access context. To decide the scope id from
  a value outside the context, such as the current time, ship a `MemoryScopeKind` with a `resolver` as a plugin, as this example does.
- The scope kind id and display name are arbitrary values chosen by the example. They are not user configuration or a package default scope kind.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

The entry point target is a single function without arguments. It returns a list of `MemoryScopeKind` (computed scope kinds pass a `resolver`) or
`{scope kind id: data (label, description, id template)}`. A `resolver` receives the access context and returns the scope id,
or None when it cannot be used (an exception also counts as None).

```python
>>> from datetime import UTC, datetime
>>> from agent_console_contracts.memory import MemoryAccessContext
>>> from agent_console_memory import MemoryScopeKind
>>> def scope_kinds():
...     def resolve(context: MemoryAccessContext) -> str:
...         year, week, _ = datetime.now(UTC).isocalendar()
...         return f"{year}-W{week:02d}"
...     return [MemoryScopeKind(id="week", label="주차", resolver=resolve)]

```

The loader (the host plugin loader `memory` of `mod-memory`, internally `agent_console_memory.load_scope_kind_plugins`) calls
this function, checks the format, and attaches the origin name `plugin:<distribution name>`. Below, this package's implementation
(`agent_console_example_memory_scope:scope_kinds`) is loaded as if it were registered as an entry point, and a scope is computed from the merged list
(`iso_week_scope_kind` is used directly to fix the clock).

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_memory import (
...     MEMORY_SCOPE_KINDS_GROUP, load_scope_kind_plugins, merge_scope_kinds,
...     new_scope_kind_registry, plugin_scope_kinds,
... )
>>> ep = EntryPoint(
...     "example.memory_scope", "agent_console_example_memory_scope:scope_kinds",
...     MEMORY_SCOPE_KINDS_GROUP,
... )
>>> registry = new_scope_kind_registry()
>>> [report.status for report in load_scope_kind_plugins(registry, entry_points=[ep])]
['loaded']
>>> [(k.id, k.origin) for k in plugin_scope_kinds(registry)]
[('example-week', 'plugin:example.memory_scope')]

>>> from agent_console_example_memory_scope import iso_week_scope_kind
>>> fixed = iso_week_scope_kind(lambda: datetime(2026, 10, 28, tzinfo=UTC))
>>> catalog = merge_scope_kinds(include_defaults=False, plugins=[fixed])
>>> catalog.resolve("example-week", MemoryAccessContext())
MemoryScopeRef(kind='example-week', id='2026-W44')

```

When you build the `EntryPoint` directly without installing, there is no distribution information, so the origin name is the entry point name.
When installed, it becomes `plugin:agent-console-example-memory-scope` (the tests check both).

## Registration

```toml
[project.entry-points."agent_console.memory_scope_kinds"]   # agent_console_memory.MEMORY_SCOPE_KINDS_GROUP
"example.memory_scope" = "agent_console_example_memory_scope:scope_kinds"
```

- The entry point name (`example.memory_scope`) is the registry key. The server setting `plugins.enabled` (allow list) selects by this name.
- The merge order is package defaults (with `include_default_scope_kinds`) → plugins → user. When you write the same id in the workspace
  settings, the user scope kind wins (`plugin:…` in `overrides`), and writing null shows it as a turned-off scope kind (`disabled: true`).

```yaml
memory:
  scope_kinds:
    example-week: null      # turn off only this scope kind while it stays installed
```

When the access settings of a `memory` resource allow actions (read, write, and so on) on the scope kind `example-week`, agents
write to that week's scope (`example-week:2026-W44`). The next week it becomes a new scope.

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-memory-scope   # install
uv pip uninstall agent-console-example-memory-scope                        # remove
```

**Restart the server** after installing or removing (`mod-memory` must be on).
- Install: `GET /api/v1/memory/scope-kinds` lists `example-week` with `origin: plugin:agent-console-example-memory-scope`
  (the `id` template is null, and `context_fields` is an empty list), and the web app's scope kind list uses this response too.
- Remove: it disappears from the list. Entries already written under `example-week:…` are not deleted; they remain as an unknown scope kind (`kind_known: false`).
- Turn off while installed: remove `example.memory_scope` from the server setting `plugins.enabled`, or set it to null in `memory.scope_kinds` as above.

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

```bash
cd examples/extensions/agent-console-example-memory-scope
uv run --project ../../.. python -m pytest
```

The tests run without installing (`pythonpath = ["src"]`). Installing and removing are simulated by creating and deleting this package's `dist-info` in a temporary folder
(only the discovery of the scope kind entry point group is isolated to that folder, so the result is the same in a venv where it is really installed), and the list and the scope calculation
are checked in the same order as server startup (host plugin loader → `mod-memory` assembly).
The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).

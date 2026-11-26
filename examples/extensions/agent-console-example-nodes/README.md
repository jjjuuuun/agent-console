# agent-console-example-nodes

An example that adds a new node type with **a single plugin package**.
No engine, server, or web code changes. Once installed, it appears in the editor palette and the settings form, and it disappears when removed.

Node type `example.text_transform` (text transform)
- Turns the value of the input `in` into text (strings as they are, anything else as JSON).
- Settings: `mode` (enum: `upper`, `lower`, `title`, `keep`), `prefix` (string), `strip` (boolean).
- Output `out` = `prefix + case conversion(text after strip)`. It is deterministic, without external calls.
- Palette group `예제`, avatar `Aa`, color `#0ea5e9`.

### What it means in a team

| Descriptor attribute | Value | Meaning |
| --- | --- | --- |
| `role` | `agent` (`TEAM_ROLE`) | The role string that the connection rules (the `connects` of edge types) look at. It is the value the default edge types (user message `message`, handoff `handoff`, reply `reply`) accept, so the node fits into an agent's place as it is. Roles are not a fixed list: when you use a new role name, the node can be connected only by edge types that list that name in `connects` |
| `binds` | none | The node is not created from one agent or resource definition. So it is not a target of the settings layers (common, team, agent), resource attachments, or usage lists, and its only settings are the node config |
| `rerunnable` | `true` | It is deterministic, so when an interrupted run is resumed it is safe to run again from this node with the saved input |

For example: user → (entry) → text transform → (reply) → user. Place the node in the editor and turn on the entry and reply toggles in the panel
(the node type scenario of E2E `08-extension`).

This package is not a uv workspace member. Install and remove it separately. When it is not installed, it changes nothing.

## Minimal code

Implement the **`NodeType` protocol** (`src/agent_console_example_nodes/text_transform.py`).
It imports only the public contract (`agent_console_contracts`) and the engine interface (`agent_console_runtime`).

| Member | In this example |
| --- | --- |
| `descriptor: NodeTypeDescriptor` | id, title, category, `config_schema` (`model_json_schema()` of a pydantic model), `ui_schema` (rjsf hints), `static_ports`, `ui_hints` (icon, color) |
| `resolve_ports(config) -> PortSpec` | Fixed ports `in` → `out` |
| `validate(config, ctx) -> list[Issue]` | Semantic validation beyond the schema: a warning when the settings change nothing |
| `async execute(ctx, inputs) -> NodeResult` | Transforms `inputs["in"]` into `NodeResult(status="succeeded", outputs={"out": ...})` |

When a class is registered as the entry point, the engine instantiates it without arguments. When it needs outside values (settings, services),
it receives them through `ctx.services` (`ServiceKey`) or `ctx.secrets`, and it does not read globals or environment variables directly.

To use only the transform logic, import `transform_text(value, TextTransformConfig(...))` and use it without the node.

## Registration

One entry point in `pyproject.toml`. Group = `agent_console_runtime.NODE_TYPES_GROUP` (`agent_console.node_types`);
name = the descriptor `id` (registry key = descriptor id = `NodeSpec.type`).

```toml
[project.entry-points."agent_console.node_types"]
"example.text_transform" = "agent_console_example_nodes:TextTransformNode"
```

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
# Install (editable mode). The dependencies (agent-console-contracts, runtime) use the workspace installation as they are.
uv pip install -e examples/extensions/agent-console-example-nodes

# Remove. After a server restart it disappears from the palette and the settings form. Teams that use this type are not deleted;
# validation reports `unknown_node_type` (runs are blocked).
uv pip uninstall agent-console-example-nodes
```

To turn it off while installed, use the server setting `plugins.enabled` (an allow list; when set, every entry point not in the list is skipped) and leave `example.text_transform` out of that list.

Note: by default `uv sync` removes packages that are not in the lock file. To sync with the example installed,
use `uv sync --all-packages --inexact` (`uv run` does not remove them).

## Checking on the server

Entry points are read once at server startup. After installing or removing, **restart the server**.

```bash
uv run agent-console serve
curl -s http://127.0.0.1:<port>/api/v1/node-types | grep example.text_transform   # appears when installed
```

The node appears in the `예제` group of the web editor palette, and when you place the node, the settings form is drawn from `config_schema` and `ui_schema`.
When the server setting `plugins.enabled` is set, `example.text_transform` must be in that list too for it to load.

## Test

Start the engine with `agent_console_runtime.testing.make_harness()`, register the node in the registry directly, and run it.

```python
h = make_harness()
h.registries.node_types.register("example.text_transform", as_node_type(TextTransformNode))
run = await h.make().run(graph, {"in": " hi "})
```

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).

```bash
cd examples/extensions/agent-console-example-nodes
uv run --project ../../.. python -m pytest
```

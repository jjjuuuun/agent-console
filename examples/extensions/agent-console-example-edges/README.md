# agent-console-example-edges

An example that adds a new **edge type** with a single plugin package.
No engine, server, or web code changes. Once installed, it appears in the editor's edge type choice and in the settings screen's default type for new edges, and it disappears when removed.

Edge type `example.relay` (pass on with a prefix)
- `scheduling = flow`: when the upstream node succeeded and produced a value in `out`, the value is passed to `in` of the downstream node. On failure or without a value, that path is blocked.
- Setting: `prefix` (string, default `[중계] `). When the value is a string, the prefix is added in front; otherwise the value is passed on as it is.
- Connection rule `connects`: role `agent` → `agent` (the `role` string of the node type descriptor). Team validation blocks edges between other roles with `team.connects_mismatch`.
- It is deterministic, without external calls.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

```python
from agent_console_contracts import EdgeConnects, EdgePortPair, EdgeSpec, EdgeTypeDescriptor
from agent_console_runtime import Activation, NodeRunView


class RelayEdge:
    descriptor = EdgeTypeDescriptor(
        id="example.relay",
        title="접두어 붙여 넘기기",
        scheduling="flow",
        connects=EdgeConnects(source=["agent"], target=["agent"]),
        default_ports=EdgePortPair(source="out", target="in"),
        config_schema={"type": "object", "properties": {"prefix": {"type": "string"}}},
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None  # dead-path
        return Activation(f"{edge.config.get('prefix', '')}{source.outputs[edge.source.port]}")
```

The real implementation is `src/agent_console_example_edges/relay.py` (validates the settings with a pydantic model and generates the schema).
`scheduling` is engine vocabulary (`flow`, `none`, `entry`, `exit`), and the engine and editor act on this attribute, not on the edge type name.

## Registration

One entry point in `pyproject.toml`. Group = `agent_console_runtime.EDGE_TYPES_GROUP` (`agent_console.edge_types`);
name = the descriptor `id` = the `kind` of a graph edge.

```toml
[project.entry-points."agent_console.edge_types"]
"example.relay" = "agent_console_example_edges:RelayEdge"
```

For a module that is not installed, you can also list it in the server setting `plugins.modules` in the form `"example.relay=agent_console_example_edges:RelayEdge"`
(it goes through the same checker and the `plugins.enabled` filter).

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-edges   # install
uv pip uninstall agent-console-example-edges                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Install: `GET /api/v1/edge-types` lists `example.relay`, and when you connect two agents in the editor, its title appears among the choices.
- Remove: it disappears from the choices. Teams that use this edge are not deleted; validation reports `unknown_edge_type` (runs are blocked).
- Turn off while installed: remove `example.relay` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).

```bash
cd examples/extensions/agent-console-example-edges
uv run --project ../../.. python -m pytest
```

E2E: the edge type scenario of `apps/web/e2e/08-extension.spec.ts` installs this package into a temporary folder and uses it.

# agent-console-example-interactions

An example that adds a new **interaction kind** (a request to the user during a run) and an **edge type** that allows that kind
with a single plugin package. No engine, server, or web code changes.

- Interaction kind `example.sign_off` (get a sign-off): request `{text}`, response `{approved: boolean (required), note?: string}`.
  The screen hint `renderer = "example-sign-off"` is a name the web app does not know, so the web app collects the response with **a form built from the response schema** (an approved checkbox + a note).
  The server and engine validate the response with `response_schema` (422 `validation_failed` when wrong).
- Edge type `example.ask_sign_off` (allow sign-off requests): `scheduling = none` (the engine does not evaluate it), `interaction.kinds = ["example.sign_off"]`,
  role `agent` → `user`, default ports `out` → `asks`. Only agents with this edge going out can open sign-off requests. Without it, the request is not opened and
  `unavailable` is returned to the backend.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

An interaction kind is **one piece of descriptor data** (no class needed).

```python
from agent_console_contracts import (
    EdgeInteraction,
    EdgeTypeDescriptor,
    InteractionKindDescriptor,
    UiHints,
)

SIGN_OFF = InteractionKindDescriptor(
    id="example.sign_off",
    title="서명 받기",
    response_schema={
        "type": "object",
        "properties": {"approved": {"type": "boolean"}},
        "required": ["approved"],
    },
    ui_hints=UiHints(renderer="example-sign-off"),
)


class AskSignOffEdge:
    descriptor = EdgeTypeDescriptor(
        id="example.ask_sign_off",
        title="서명 받기 허용",
        scheduling="none",
        interaction=EdgeInteraction(kinds=["example.sign_off"]),
    )

    def activates(self, source, edge):
        return None  # the engine does not evaluate none edges
```

The side that opens a request is a node (`ctx.request_input(InteractionRequest(kind="example.sign_off", ...))`) or the execution backend that node hands off to.
With the fake backend, you can open one with the agent rule `backend_options.default.ask: [{kind: "example.sign_off", ...}]`.

## Registration

```toml
[project.entry-points."agent_console.interaction_kinds"]   # agent_console_runtime.INTERACTION_KINDS_GROUP
"example.sign_off" = "agent_console_example_interactions:SIGN_OFF"

[project.entry-points."agent_console.edge_types"]          # agent_console_runtime.EDGE_TYPES_GROUP
"example.ask_sign_off" = "agent_console_example_interactions:AskSignOffEdge"
```

When an entry point points to a descriptor object, the loader (`as_interaction_kind`) wraps and registers it.

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-interactions   # install
uv pip uninstall agent-console-example-interactions                        # remove
```

**Restart the server** after installing or removing.
- Install: `GET /api/v1/interaction-kinds` lists `example.sign_off`, and `GET /api/v1/edge-types` lists `example.ask_sign_off`.
- Remove: both disappear. Validation reports `unknown_edge_type` for teams that use this edge, and requests of this kind from a backend are not opened.
- Turn off while installed: remove both names from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

```bash
cd examples/extensions/agent-console-example-interactions
uv run --project ../../.. python -m pytest
```

The tests run without installing (`pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).
E2E: the interaction kind scenario of `apps/web/e2e/08-extension.spec.ts` installs this package into a temporary folder and uses it.

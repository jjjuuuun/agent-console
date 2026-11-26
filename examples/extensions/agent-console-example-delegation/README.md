# agent-console-example-delegation

An example that adds a new **delegation strategy** with a single plugin package.
No engine, server, or web code changes. Once installed, it appears in the delegation strategy list (`GET /api/v1/delegation-strategies`) and in the
*Delegation strategy* choices of delegation edges in the editor, and it disappears when removed.

Delegation strategy `example.round_robin` (hand off in turn)
- It calls the delegates **once each, in edge order** through the engine's `ctx.invoke_node` (each delegate gets its own NodeRun), hands each one the delegator's input
  as it is, and joins the results into the delegator's result. It is a deterministic delegation that calls no model.
- Settings (the delegator node config `delegation.example.round_robin`): `item_template` (default `[{target}] {result}`;
  variables `target`, `role`, `result`, `status`), `separator` (default: a blank line), `failure_text` (default `(실패: {code})`), and
  `stop_on_failure` (default false; when on, the delegator also fails with `example.round_robin.member_failed` as soon as one delegate fails).
- The rules are descriptor values: **`composable = false`**: when the same delegator also has delegates of another strategy (for example subagent `subagent`
  or independent delegation `host`), team validation blocks it with `team.mixed_strategies` (error). The value is turned off on purpose to show the
  difference from strategies that can be mixed. `requires_backend_capability = null` (the delegator's backend is not called),
  `allows_outgoing_flow = false`, and `max_depth = null` (only the setting `delegation.max_depth`).

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

```python
from agent_console_contracts import AgentSettings, DelegationStrategyDescriptor, Issue
from agent_console_runtime import AgentResult, DelegationPlan, NodeContext


class RoundRobinDelegation:
    descriptor = DelegationStrategyDescriptor(
        id="example.round_robin",
        title="차례로 맡기기",
        member_fields=list(AgentSettings.model_fields),
        max_depth=None,
        allows_outgoing_flow=False,
        requires_backend_capability=None,
        member_interaction_kinds=None,
        composable=False,
    )

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        return []

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult:
        parts = []
        for m in plan.members:  # the minimal example assumes the default agent node ports (in, out)
            view = await ctx.invoke_node(m.node_id, {"in": plan.request.prompt}, by_edge=m.edge_id)
            parts.append(f"[{m.node_id}] {view.outputs.get('out', '')}")
        return AgentResult(status="succeeded", text="\n\n".join(parts))
```

The real implementation is `src/agent_console_example_delegation/round_robin.py` (validates the settings with a pydantic model and generates the schema, reads port names
from the target node type, handles failures, and substitutes safely with `fill`).

## Registration

One entry point in `pyproject.toml`. Group = `agent_console_runtime.DELEGATION_STRATEGIES_GROUP`
(`agent_console.delegation_strategies`); name = the descriptor `id`.

```toml
[project.entry-points."agent_console.delegation_strategies"]
"example.round_robin" = "agent_console_example_delegation:RoundRobinDelegation"
```

To use only the engine without an entry point, register it in a registry directly (the tests do this):
`registries.delegation_strategies.register("example.round_robin", RoundRobinDelegation())`.

Using it in a team: choose the strategy with the config `strategy` of a delegation edge (`delegate`) (it overrides the default strategy of the edge type).

```yaml
edges:
  - id: d1
    source: {node: lead, port: delegates}
    target: {node: writer, port: delegated}
    kind: delegate
    config: {strategy: example.round_robin}
nodes:
  - id: lead
    type: agent
    config:
      agent_ref: lead
      delegation:                      # settings per strategy (omitted = schema defaults)
        example.round_robin: {separator: " | "}
```

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-delegation   # install
uv pip uninstall agent-console-example-delegation                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Install: `GET /api/v1/delegation-strategies` lists `example.round_robin`.
- Remove: it disappears from the list. Teams that chose this strategy are not deleted; the pre-save validation reports `team.unknown_strategy` (warning),
  and when run, the delegator node fails with `agent.unknown_strategy`.
- Turn off while installed: remove `example.round_robin` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest
with this folder's settings (`uv run poe examples`). Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>`
(`uv run poe wheels` in the repository), and then `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-delegation
uv run --project ../../.. python -m pytest
```

The tests run end to end with the default nodes (agent node and delegation edge, `agent-console-nodes-core`) and the fake backend: running in turn,
settings, failure handling, `team.mixed_strategies` when mixed with another strategy, and a warning and a run failure after removal.
E2E: `apps/web/e2e/08-extension.spec.ts` (`ext` flavor) installs this package into a temporary folder and checks the list and a run.

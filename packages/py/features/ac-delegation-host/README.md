# agent-console-delegation-host

The standalone delegation strategy `host` (a delegation strategy plugin). It gives the delegator model one **delegation tool** (platform
tool `HostTool`). When the model calls the tool, the target node runs through the engine's `ctx.invoke_node` in **its own NodeRun, session,
backend, model, and resources**, and the result comes back as the tool result. When the backend reports the tool call id
(`HostTool.call_handler`), it is passed on as `tool_use_id` in the target NodeRun's `node.*` payload. The target can delegate again (nesting) or ask the user
through its own `ask_user` edge. You use it with only the engine (`agent-console-runtime`) and the contracts, without the server, the web app, or node plugins.

- The rules are descriptor values (`host_descriptor()`): depth comes only from the user setting `delegation.max_depth`
  (`max_depth: null`), outgoing flow edges from the target are not allowed (`allows_outgoing_flow: false`), every settings field of the target
  applies (`member_fields` = all of `AgentSettings`), target questions are not limited, the delegator backend needs the `host_tools` capability,
  `composable: true` (runs combined with other composable strategies on one delegator), `shares_session: false` (the target runs in its own
  session, so the target's interaction kinds and wait limits are not added to the delegator session grant).
- Tool names, parameter names, and the text the model sees are **schema defaults** of the strategy config (`HostDelegationConfig`).
  Change them with the delegator node's per-strategy config (for example, agent node `delegation.host`). There is no branching on names in the code.
- Tool input = `{<target_param>: target node id (enum), <task_param>: the task}`. The task goes into the first input
  port of the target node type (change it with `input_port=`).
- Result: when the delegation edge config `result` is `text` (default), the value of the target's first output port; when it is `reply`, the reply text that the target's reply edge
  (`scheduling = exit`) would produce. Target failure, depth exceeded (`delegation.depth_exceeded`), cycles, unknown targets, and
  empty tasks are not exceptions but `is_error` tool results (the delegator model decides). The `{code}` and `{message}` of the failure text (`failure_text`)
  contain only values masked by the engine (`ctx.secrets.redact`).
- Serializing runs of the same target, concurrent run slots, cleanup on cancel, emitting target replies, and recording are done by the engine. This strategy does not run the target
  directly.
- Mixed delegation: `contribute(plan, ctx)` does not call the backend and returns only `DelegationContribution(host_tools=[tool])`.
  The node merges what each strategy returned with `merge_contributions` (ac-runtime) (overlapping tool names =
  `delegation.duplicate_host_tool_names`).
- Static checks at save time: `static_issues(config, members)` returns edge result shape issues
  (`delegation.invalid_result_mode`, edge issues) and config rules that a schema cannot express (target and task parameter names
  are the same, `delegation.invalid_config`); `declared_names(config, members)` returns `{"host_tool": [tool names]}`.
  Config schema violations and duplicate targets are reported by the general `ac-teams` rules.

## Dependencies: what / why / alternatives

- Internal: `agent-console-contracts` (descriptor and issue models), `agent-console-runtime` (protocols, `HostTool`,
  `invoke_node`). It does not know node plugins (`ac-nodes-core`), teams (`ac-teams`), or backends (import-linter contract).
- **pydantic**: strategy config validation and JSON Schema (descriptor `config_schema`). The contracts package already uses it.
- As an alternative, the delegation strategy could call the backend directly to run the target, but that would duplicate the node run rules (settings, resources, questions,
  recording), so it was not chosen.

## Installation

```bash
pip install agent-console-delegation-host
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-delegation-host
```

Once installed, it is registered as `host` in the entry point group `agent_console.delegation_strategies`
(`load_registries` finds it). If you remove it, `host` edges become an "unregistered delegation strategy" warning in team validation.

## Minimal usage

```python
>>> from agent_console_contracts import Agent
>>> from agent_console_delegation_host import HostDelegation
>>> from agent_console_runtime import AgentRequest, DelegationMember, DelegationPlan

>>> host = HostDelegation()
>>> d = host.descriptor
>>> d.id, d.composable, d.max_depth, d.requires_backend_capability, d.shares_session
('host', True, None, 'host_tools', False)

>>> plan = DelegationPlan(
...     strategy="host",
...     delegator_node_id="lead",
...     backend="fake-agent",
...     request=AgentRequest(agent=Agent(id="lead", name="Lead"), prompt="로그인 구현"),
...     members=[
...         DelegationMember(node_id="be", edge_id="lead->be", role="백엔드", delegate_when="서버 작업"),
...         DelegationMember(node_id="qa", edge_id="lead->qa", role="검증"),
...     ],
...     config={"tool_name": "hand_off"},
... )
>>> host.validate(plan)
[]
>>> (tool,) = host.contribute(plan, ctx=None).host_tools  # the engine context is needed only when calling the handler
>>> tool.name, tool.input_schema["properties"]["target"]["enum"], tool.input_schema["required"]
('hand_off', ['be', 'qa'], ['target', 'task'])
>>> print(tool.description.splitlines()[-2])
- be: 백엔드 — 서버 작업

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

To use it inside the engine, register it in the registry (`registries.delegation_strategies.register("host", HostDelegation())`
or an entry point), and the delegator node calls `strategy.run(plan, ctx)` (standalone) or `contribute` (mixed).
`tests/test_agent_console_delegation_host.py` has examples that run end to end with the engine, the fake backend, and claude-sdk (SDK mock).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

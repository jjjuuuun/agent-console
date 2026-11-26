# agent-console-nodes-core

Plugins for the default node types (`agent`, `user`, `resource`), edge types (`subagent`, `handoff` (+ the old name `data`), `uses`,
`message`, `reply`), and the delegation strategy `sdk-subagents`. The engine (`agent-console-runtime`) and
the team semantics (`agent-console-teams`) do not know these names. This package only registers them through entry points,
and decisions are made from descriptor attributes (`role`, `executable`, `binds`, `scheduling`, `invocation`, `connects`).

## Installation

```bash
uv sync --all-packages                        # inside the workspace
uv pip install ./packages/py/features/ac-nodes-core    # standalone
```

Dependencies: `agent-console-contracts`, `-registry`, `-runtime`, `-resources`, `-teams`, `pydantic`.
It does not know store, routing, or backend packages. Only the tests use `agent-console-backend-fake-agent` and `-resources-core`.

## Registration (entry points, name = registry key = descriptor id)

| Group | Names | Objects |
| --- | --- | --- |
| `agent_console.node_types` | `agent`, `user`, `resource` | `agent:AgentNode`, `user:UserNode`, `places:ResourceNode` |
| `agent_console.node_types` | `team` | `team:TeamNode` (nested team) |
| `agent_console.edge_types` | `subagent`, `delegate`, `handoff`, `data`, `uses`, `message`, `reply`, `ask_user` | `edges:*Edge` |
| `agent_console.edge_types` | `loop` | `loops:LoopEdge` |
| `agent_console.edge_types` | `when`, `on_error` | `conditional:WhenEdge`, `conditional:OnErrorEdge` |
| `agent_console.interaction_kinds` | `question`, `tool_permission`, `review` | `interactions:QUESTION` and others (descriptor objects) |
| `agent_console.delegation_strategies` | `sdk-subagents` | `delegation:SdkSubagentsStrategy` |

## Node types

| id | role | Ports | config | Behavior |
| --- | --- | --- | --- | --- |
| `agent` | agent, `binds{agent, agent_ref}` | Inputs `in`, `delegated`, `resources`; outputs `out`, `delegates` | `agent_ref`, `role?`, `delegate_when?`, `settings?` (node layer `AgentSettings`), `delegation?` (delegation strategy id → that strategy's config, for example `{host: {tool_name: hand_off}}`) | See "Agent run" below. `actor_of(config)` = `agent_ref` |
| `user` | user | Inputs `hears`, `asks`, `review`; outputs `says` + decision ports (`review.decisions[].id`, dynamic) | `review?{title, message, decisions[{id, label, edit, feedback, ui_hints}], output_template?, kind (default review), timeout_seconds?, on_timeout?}` | `executable=true`, but without incoming `entry` or `flow` edges the engine does not schedule it. When run through a flow, see "Intermediate user review" below. Without `review`, `user.not_reviewable`. Declarative badge `검토` (review settings + a flow input) |
| `resource` | resource, `binds{resource, resource_ref}` | Output `provides` | `resource_ref` | `executable=false`. Node layer attachments of the connected agents (`ac-teams`) |
| `team` | team, `binds{graph, team_ref}`, `ui_hints.shape = stacked` | Input `in`, output `out` | `team_ref`, `version?` (definition store version hash; omitted = latest), `input_key?`, `reply?` (list of reply labels), `reply_separator` (default a blank line), `settings?` (overrides of the child team layer, `GraphSettings`) | See "Nested team run" below |

### Nested team run (`team`)

1. Finds the team through the service `TEAM_LOOKUP` (`(id, version|None) -> Graph|None`). Without the service,
   `team.lookup_unavailable` (message `TEAM_LOOKUP_UNAVAILABLE_MESSAGE`); a missing team or version gives `team.team_not_found`.
2. With `settings`, the child team layer is overridden with `ac-teams.with_team_settings` (only the given values; `team.invalid_settings` if wrong).
3. `ctx.run_child(graph, {"text": value}, services={SESSIONS: …})`. Value = the input `in` (if it is an object and `input_key` is set, that key).
   Sessions pass on only the path keys `"<this node>/<child node>"` of the parent `SESSIONS`, with the prefix removed (`child_sessions`; grandchildren follow the same rule).
   The same key (`session_path_key`) is used when the conversation saves sessions after the child Run (that is the conversation side's job).
4. Result: child `completed` → `out` = the reply texts chosen by `pick_replies` joined with `reply_separator` (with a `reply` list,
   those labels in list order; otherwise all `final` replies by `order` → emission order). `waiting` (parked) → this node is also `waiting`
   (`wait.reason = TEAM_CHILD_WAITING`, `data.child_run_id`). Anything else → `failed` (the child error as is + `details.child_run_id`,
   or `team.child_failed` if there is no error). Refusals (nesting limit `team.nesting_exceeded`, cycle `team.recursive`, validation `validation_failed`) are
   returned by the engine as failure results without a child Run. Usage `usage` = the child's `totals` (included in the parent's totals).
5. Interactions inside the child Run (questions and so on) make the engine put the parent Run in `waiting`, and they continue through `respond(child Run id, …)`.
   The allowed interactions of the child Run are decided by the child Run preparer (`GraphRuntime(child_preparer=)`; none without it).

The `team` role is included at both ends of flows (`handoff`, `loop`, `when`, `on_error`), as the target of `message`, and as the source of `reply` (edge rule data).
It is not a target of delegation edges (`subagent`, `delegate`).

### Agent run
1. `team_plan(ctx.graph, registered descriptors)` → 2. `node_settings` (common → team → agent → node + resource
edges) → 3. backend = the effective `backend` → `DEFAULT_BACKEND` → 4. bundle = `node_bundle(..., accepted_slots=
capabilities.resource_slots)`; the files slot is written to `<RUN_FILES_ROOT>/<run>/<node>/` and replaced with `{path, root, name}`
(`write_files`: base64 decoding, rejects paths outside the folder and symbolic links, parent folders are checked per slot and then created. Items that already have only `{path, root?}`
are passed on only when `path` and `root` are inside that run folder; the backend opens these paths as agent-accessible folders (`add_dirs`),
so other plugins must not be able to open arbitrary paths. The first path segment `_bundle` is reserved); when items of slots other than the files slot
have `files: [{name, content, …}]` (skills, rule files), `write_item_trees` writes them with the same rules to
`<RUN_FILES_ROOT>/<run>/<node>/_bundle/<node>/<slot>/<item name>/` and replaces the item with
`{…, root, tree_root, files: [{name, path, media_type?}]}` (it does not know slot names, only shapes. The tree folder name is
the node id, so even when the backend passes this folder as a plugin folder, names differ per node) → 5. definition (identity) + effective settings, secret reference resolution,
prompt = `assemble_prompt(in value, prompt_template)` (variables `{inputs}`, `{message}`, `{node}`). After building the request and before calling the backend,
it emits `agent.context_prepared` (`context_prepared_payload`: resource id, kind, byte count, and sha256 of the bundle sources, and the fragment count = the number of prompt
inputs, **no bodies**); session = `SESSIONS[node]`
(none when the effective `session` is `fresh`, none when the backend differs), `interactions` = `session_grant(plan, node, delegation strategy)`
→ 6. if there are delegates (`invocation` edges), they are grouped per delegation strategy, and for each group a `DelegationPlan` is built from the effective settings, bundle, `describe_member`, and
strategy config (`delegation[strategy id]`) and validated with `validate` → with one strategy,
`registries.delegation_strategies.get(id).run(plan, ctx)`; with several, see "Mixed delegation" below; without any, `backend.run` →
7. `out` = the response text.
Bundle and resource problems give `log.warning` (details `code`, no values).

Merging: the prompt input is built from the per-edge values the engine gives, `ctx.incoming("in")`. The format is effective settings (data).

| Setting | Default (contract `AgentSettings`) | Use |
| --- | --- | --- |
| `prompt_input_template` | `"{source}: {value}"` | Format of one value when there are several (merging) |
| `prompt_single_input_template` | `"{value}"` | Format when there is one value |
| `prompt_input_separator` | `"

"` | Separator between values |

Variables: `source` (the sending node's label, or its id), `source_id`, `port`, `edge`, `value`, `index` (from 1). The result built this way is
`{inputs}` of `prompt_template`. In code: `PromptFormat.of(settings)`, `assemble_prompt(items, template, fmt=)`.

## Edge types

| id | scheduling | connects (source → target) | Default ports | config |
| --- | --- | --- | --- | --- |
| `subagent` | none, invocation `sdk-subagents` | agent → agent | `delegates` → `delegated` | `strategy?` |
| `handoff` / `data` (hidden) | flow | agent, user → agent, user | `out` → `in` | none |
| `uses` | none | resource → agent | `provides` → `resources` | `mode?`, `config_override?` |
| `message` | entry | user → agent | `says` → `in` | `input_key?` (omitted = `"text"` = `DEFAULT_MESSAGE_KEY`, the same as ac-chat), `template?` (`{message}` + Run input keys) |
| `reply` | exit | agent, user → user | `out` → `hears` | `label?`, `order?`, `final` (default true), `stream` (default true, for the screen). Declarative chip `중간 결과` (intermediate result, `final == false`) |
| `ask_user` | none, interaction `question`, `tool_permission` | agent → user | `out` → `asks` | `kinds?` (narrowing), `timeout_seconds?`, `on_timeout?` (`expire`, `cancel_run`), `label?` |

| `delegate` | none, invocation `host` | agent → agent | `delegates` → `delegated` | `strategy?`, `result?` (`text` default \| `reply`) |

`delegate`: the upper agent calls the lower agent through a delegation tool **in the lower agent's own session, backend, and settings**. The `host`
delegation strategy implementation is the separate package `agent-console-delegation-host` (this package knows only the id string as descriptor data;
without it installed, team validation warns about an "unregistered delegation strategy"). `result` is the shape of the result the target returns (read by that strategy).

`message`: does not pass when the Run input lacks the key. `reply`: `Reply(text, label, order, final)` only when the source node succeeded.

### Loop edge `loop`

| id | scheduling | connects | Default ports | config |
| --- | --- | --- | --- | --- |
| `loop` | flow, `cycle{max_iterations: 3}` | agent, user → agent, user | `out` → `in` | `max_iterations?` (≥1; when empty, the setting `flow.max_iterations` → default 3) |

An edge that can close a flow cycle (the engine decides by the descriptor `cycle`, not the name). It passes only when the source node succeeded and emitted a value on the port,
and the engine runs the nodes in between again as a new iteration. Example: a user review node's decision port `rejected` → the author's `in`.
The next iteration of an agent node continues the previous iteration's session (a new session with the setting `session: fresh`), and when continuing, the prompt contains only the values
that newly arrived in this iteration (for example the rejection reason; `Incoming.carried` values are left out). With a new session, the remaining values are put in again too.

### Condition and failure edges `when`, `on_error`

| id | scheduling | connects | Default ports | config |
| --- | --- | --- | --- | --- |
| `when` | flow | agent, user → agent, user | `out` → `in` | `conditions?` (`ConditionSpec{all?, any?, negate?}`; always passes when empty) |
| `on_error` | flow, `handles_failure` | agent, user → agent, user | `out` → `in` | none |

`when`: conditions are evaluated only when the source node succeeded and emitted a value on the port (failure handling is `on_error`'s job). The judged value is
`condition_subject` = `{output?, structured?, status, iteration, error?}` (`path` is a JSON Pointer, for example `/output`,
`/structured/verdict`, `/iteration`). When true, the port value is passed on and the evidence goes to `edge.traversed.condition`; when false,
`Blocked(reason="condition_false")` leaves `edge.skipped{reason, condition}`. Operators come from the `ac-conditions`
registry (installed entry points when omitted; inject with `WhenEdge(operators=...)`), and items with unknown operators are
false + `log.warning` (`details.code = condition.unknown_operator`). The pre-save check (`EdgeValidator.validate_edge`) reports
`condition_issues` with config paths `/conditions/...`. For the editing screen, it carries schema `examples` on path fields, and `ui:widget: condition-list` and `ui:options.path_titles` (path → title) in the `ui_schema`
`conditions` (data).
The actual value in the evidence (`actual`) is cut at 200 characters **after** the masking function is applied (`WhenEdge(redact=...)` or `use_redactor`, `ac-conditions.RedactorConsumer`;
the runs module gives the engine's `secrets.redact`), because masking at the recording stage
cannot recognize cut secret fragments.

`on_error`: passes `{error: {code, message}, node_id}` only when the source node is `failed`. When it passes, the engine treats that failure
as handled, and the Run can end `completed`.

## Intermediate user review (A → user → B)

Opens an interaction (`review.kind`, default `review`) with the value that came into the `review` port (usually through `handoff`) as its content.
The payload is `{content, decisions, title?, source_node?}`, and the response schema is `review_response_schema(decision ids)` per request
(`decision` enum). A value is emitted only on the port of the chosen decision (the rest are dead paths, so downstream is skipped). For decisions that allow `edit`,
`edited` replaces the content, and only decisions that allow `feedback` take comments. Value = `output_template` (variables `content` (the edited content if edited),
`original` (before editing), `edited`, `feedback`, `decision`, `source_node`, `title`) or the content. Expiry fails with `review.expired`, cancellation with `review.cancelled`.
A decision id that collides with the fixed output port (`says`) is a validation error and does not become a port. Input ports (`hears`, `asks`, `review`) are in a
different name space, so they can be used as decision ids.

## Interaction kinds

| id | Request | Response | `free_text_path` | `expire_response` | renderer |
| --- | --- | --- | --- | --- | --- |
| `question` | `{questions[{question, header?, options[{label, description?}], multi_select}], text?}` | `{answers{question: label \| label[] \| string}, response?}` (one of the two is required) | `/response` | none (the adapter denies) | `choices` |
| `tool_permission` | `{tool_name, input_preview?, title?, display_name?, description?, blocked_path?, decision_reason?, tool_use_id?, agent_id?}` | `{decision: allow \| allow_for_run \| deny, message?, updated_input?}` | none | `{decision: deny, message: <no user response>}` | `permission` |
| `review` | `{content, decisions[...], source_node?, title?}` | `{decision, edited?, feedback?}` (enum per request) | none | none (the node fails) | `review` |

The agent node passes `session_grant(plan, node, delegation strategy)` (its own `ask_user` edges + the delegates' grants
filtered by `member_interaction_kinds`) as `AgentRequest.interactions`. Without edges it is `None`, and the backend
does not open requests. The delegation strategy sink passes `request_input` through to ctx (passing the backend's `InteractivePort` check).

## Delegation strategy `sdk-subagents`

`member_fields = [model, system_prompt, tools, disallowed_tools, resources]`, `max_depth=1`,
`allows_outgoing_flow=false`, `requires_backend_capability="subagents"`, `member_interaction_kinds=["tool_permission"]`.
Why `resources` is included: the SDK `AgentDefinition` takes skills, mcpServers, and prompt (instructions) per subagent.
The files and hooks slots share the session, so the backend merges them into the delegator side with a warning.

`run`: puts `subagents = subagent_specs(members)` into the delegator request and runs it with the delegator's backend. The sink passed to the backend
wraps `ctx` and satisfies `SubagentResultListener` (ac-runtime, `on_subagent_result(name, *, text, status, actor, tool_use_id)`). When the backend (claude-sdk, fake)
calls it with the full result each time one delegation ends, `ctx.emit_replies(target, {result port: text})` evaluates the target's reply edges
(result port = the first output port of the target node type). Other attributes (for example `request_input`) are passed through to `ctx`.

`composable=true`: `contribute(plan, ctx)` returns `DelegationContribution(subagents=…, wrap_sink=…)` (the sink wrapping above).

Static checks at save time: `declared_names` is `{"subagent": [target node ids]}`, and `static_issues` is an empty list.
When the node is a delegator, the `validate` of the `agent` node calls the two optional methods of the registered delegation strategies through `ac-teams.delegation_static_issues`
(engine validation = the server's pre-save check path). Name overlaps among strategies to be run together show up before running as `delegation.duplicate_<group>_names`.

## Mixed delegation

When one delegator's targets span several delegation strategies (for example a `subagent` edge + a `delegate` edge), they are run together only when every strategy's descriptor is
`composable` and has `contribute` (`ComposableDelegation`). The backend capability each strategy needs
(`requires_backend_capability`) is checked (`delegation.backend_unsupported`), subagents, platform tools, and options are concatenated with `merge_contributions`
(overlapping tool or subagent names and conflicting option values fail,
for example `delegation.duplicate_host_tool_names`), and the delegator's backend is called **once**. The sink is wrapped with each strategy's `wrap_sink`.
Mixing in a strategy that cannot be combined fails with `agent.mixed_strategies` (details `strategies`, `not_composable`) (team validation
`team.mixed_strategies` blocks it first).

**Note:** replies of subagents (target nodes) come only from backends that send `on_subagent_result` notifications (claude-sdk, fake).
With backends that do not, there are no replies even if `reply` edges leave the target node (the delegator's replies are normal).

## Agent tool providers

A general extension point through which other features give tools to the model of an agent node. The agent node does not know what the tools mean.
Providers (`ToolProvider`: `id` + `provide(ctx) -> ToolProvision`) are put into the service `TOOL_PROVIDERS` (a list).
They are put in per Run with `start(services=...)` (in the integrated server, items of the run scope port `runs.scopes` put them in),
and child Runs (nested teams) inherit the parent's services. Without the service, or when it is empty, runs are the same as now.

Agent node order: compute the bundle → `provide` for each provider (context `ToolProvisionContext`: run, root run, team, node,
`node_path`, agent, iteration, effective bundle, backend capabilities, `emit`, cancel token) → append the provided tools after the delegation tools →
remove the consumed slots (`consumed_slots`) from the backend request bundle (and their `resource.slot_unsupported` warnings too).
Warnings (`log.warning`, details `code`) are `ToolProviderCodes`.

| Code | When | Result |
| --- | --- | --- |
| `tools.provider_failed` | `provide` raised (only the type name is recorded) or returned an invalid result | Only that provider is skipped |
| `tools.duplicate_name` | The name overlaps a delegation tool or an earlier provided tool | The provided tool is removed |
| `tools.backend_capability_missing` | The backend's `capabilities.host_tools` is false | All provided tools are removed; the run continues |
| `tools.instructions_unsupported` | The provider has instructions but the backend's `capabilities.resource_slots` lacks `instructions` | The instructions are removed (one per provider, details `provider`, `backend`); tools and the run continue |

**Provider instructions**: `ToolProvision.instructions` (a list of texts, empty by default) are appended at the end of the request bundle slot `instructions`
in provider order. The backend appends this slot after the agent instructions and resource instructions, so they come "after the effective system instructions"
(no provider id header is added). The source is `BundleSource(ref="tool_provider:<id>")`, so
it shows in `agent.context_prepared` as a `tool_provider:<id>` item (kind `instructions`, byte count and hash).
When a provider gives no instructions, the request is the same as before. The pure function `attach_instructions(bundle, [(id, text)])` does the same
on its own.

Among delegates, `sdk-subagents` targets are inside the delegator session and get no separate provisioning, while `host` targets have their own NodeRun and are provisioned with their own
bundle. When delegating with one strategy, the provided tools come before the delegation tools that the strategy's `run` adds
(name collision checks use the strategy's `declared_names`, or else read the delegation tool names in advance through `contribute`).

The test and model provider `agent_console_nodes_core.testing.EchoToolProvider` (one tool that returns the input `text`,
one event per call; with `slot`, it gives the tool only when that slot exists and consumes the slot; with `instructions`, it gives instructions too):

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_nodes_core import ToolProvisionContext, provide_tools
>>> from agent_console_nodes_core.testing import EchoToolProvider
>>> from agent_console_runtime import CancelToken

>>> async def emit(type, payload):
...     print(type, payload["chars"])
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="pl", node_path=("pl",),
...     agent_id="pl", call=0, iteration=0, bundle=ResourceBundle(),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken(),
... )
>>> provision = provide_tools([EchoToolProvider("echo", tool_name="echo", prefix="> ")], ctx)
>>> [tool.name for tool in provision.host_tools]
['echo']
>>> result = asyncio.run(provision.host_tools[0].handler({"text": "hi"}))
echo.called 2
>>> result.text
'> hi'

>>> from agent_console_nodes_core import attach_instructions
>>> provision = provide_tools([EchoToolProvider("notes", instructions=["노트는 도구로 고치세요."])], ctx)
>>> bundle = attach_instructions(None, provision.sourced_instructions())
>>> bundle.slots["instructions"], [s.ref for s in bundle.sources["instructions"]]
(['노트는 도구로 고치세요.'], ['tool_provider:notes'])

```

## Minimal usage (app assembly)

```python
>>> import asyncio
>>> from agent_console_contracts import Agent, Graph, WorkspaceSettings
>>> from agent_console_nodes_core import AGENT_LOOKUP, RESOURCE_TYPES_EXTENSION, WORKSPACE_SETTINGS
>>> from agent_console_resources import load_resource_types
>>> from agent_console_runtime import (
...     GraphRuntime,
...     InMemoryEventBus,
...     Registries,
...     Services,
...     load_registries,
... )
>>> from agent_console_runtime.testing import InMemoryRecorder

>>> registries = Registries()
>>> _ = load_registries(registries)  # nodes, edges, delegation strategies, backends (entry points; here including the fake backend)
>>> _ = load_resource_types(registries.extension(RESOURCE_TYPES_EXTENSION))  # resource kinds
>>> {"agent", "user", "resource"} <= {e.key for e in registries.node_types.list()}
True

>>> agents = {  # usually looked up in the definition store
...     "pl": Agent(id="pl", name="PL", backend="fake-agent", backend_options={"default": {"response": "PL: $prompt"}})
... }
>>> services = Services(
...     {
...         AGENT_LOOKUP: agents.get,  # id → Agent | None
...         WORKSPACE_SETTINGS: WorkspaceSettings(),  # the common layer
...         # RESOURCE_LOOKUP: FunctionResources(find_resource, read_body),
...         # RUN_FILES_ROOT, WORKING_DIRECTORY: run file and project folder paths (strings)
...     }
... )
>>> graph = Graph.model_validate(
...     {
...         "id": "team",
...         "name": "팀",
...         "nodes": [
...             {"id": "you", "type": "user"},
...             {"id": "pl", "type": "agent", "config": {"agent_ref": "pl"}},
...         ],
...         "edges": [
...             {
...                 "id": "m1",
...                 "source": {"node": "you", "port": "says"},
...                 "target": {"node": "pl", "port": "in"},
...                 "kind": "message",
...             },
...             {
...                 "id": "a1",
...                 "source": {"node": "pl", "port": "out"},
...                 "target": {"node": "you", "port": "hears"},
...                 "kind": "reply",
...             },
...         ],
...     }
... )
>>> recorder = InMemoryRecorder()  # in production, ac-store SqliteStorage
>>> runtime = GraphRuntime(registries, recorder, InMemoryEventBus(), services=services)
>>> run = asyncio.run(runtime.run(graph, {"text": "안녕"}))  # conversation turns pass SESSIONS in services= per Run
>>> run.status
'completed'
>>> [e.payload["text"] for e in recorder.events.list(run.id) if e.type == "run.reply"]
['PL: 안녕']

```

## What the app injects

| Name | Type | Without it |
| --- | --- | --- |
| `AGENT_LOOKUP` | `ServiceKey[Callable[[str], Agent \| None]]` | The agent node fails (`agent.lookup_unavailable`); validation is skipped |
| `WORKSPACE_SETTINGS` | `ServiceKey[WorkspaceSettings]` | The common layer is empty |
| `DEFAULT_BACKEND` | `ServiceKey[str]` | Fails when every layer is empty (`agent.no_backend`) |
| `WORKING_DIRECTORY` | `ServiceKey[str]` | With no effective `working_directory` either, `cwd=None`. When present, a relative `working_directory` and `{workspace}` and relative paths in `limits.directories` are resolved to real paths relative to this folder (`resolve_working_directory`, `resolve_paths`, placeholder table `path_placeholders`). Without it, values stay as they are |
| `RESOURCE_LOOKUP` | `ServiceKey[ResourceLookup]` | Attached resources are not delivered + a warning (`agent.resources_unavailable`) |
| `RUN_FILES_ROOT` | `ServiceKey[str]` | The files slot is not delivered + a warning (`files.unavailable`) |
| `SESSIONS` | `ServiceKey[Mapping[str, SessionRef]]` | A new session |
| `TEAM_LOOKUP` | `ServiceKey[TeamLookup]` (`(id, version \| None) -> Graph \| None`) | The `team` node fails (`team.lookup_unavailable`) |
| `TOOL_PROVIDERS` | `ServiceKey[Sequence[ToolProvider]]` (per Run) | No provided tools (the same as now) |
| `RESOURCE_TYPES_EXTENSION` (`"resource_types"`) | `registries.extension(...)` | Attachments drop out as "unknown kind" |

Error codes: `NodesCoreErrorCodes` (`agent.*`, `files.*`, `delegation.*`, `resource.*`, `user.not_reviewable`, `team.*`).

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-nodes-core`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-nodes-core/tests
```

Tests load only the entry points from the installed metadata and use the fake backend to check hierarchical, sequential, parallel (join all), mixed, team member entry, and intermediate reply runs,
settings layers, sessions, allowed interactions, resource bundles (file records), and that registering edge types under other ids gives the same runs.

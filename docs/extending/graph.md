# Team graph and runs

These are the points that change the parts a team (graph) is made of and the decisions made during a run. Node types,
edge types, delegation strategies, condition operators, and the requests a run makes to the user (interaction kinds)
are all plugins. The run engine does not know these names and looks them up in registries, so the built-in
implementations are simply the first implementations registered in the same groups.

The common rules (entry point names, load time, turning on and off) are in [Plugin basics](plugins.md). This page
covers only what differs per point.

| What you want to do | Point |
| --- | --- |
| Put a new box (one piece of work) in the team editor | [node-type](#node-type) |
| Connect two boxes in a new way | [edge-type](#edge-type) |
| Change how a delegator hands work to its delegates | [delegation-strategy](#delegation-strategy) |
| Add a new comparison to conditional edges and condition fields | [condition-operator](#condition-operator) |
| Open a new shape of request to the user during a run (approval, signature, and so on) | [interaction-kind](#interaction-kind) |

## condition-operator

**When to use**: when a conditional edge (`when`), or another extension that reads conditions, needs a decision that
the built-in operators (equals, contains, size comparisons, regular expressions, and so on) cannot express. Its only
dependency is the contract package, so it is the smallest kind of plugin. If this is your first plugin,
[Get started](getting-started.md) walks through this point end to end.

**Minimal shape**: `descriptor` (`ConditionOperatorDescriptor`: `id`, `title`, and optionally `value_schema` and
`applies_to`) and one method, `evaluate(actual, expected) -> bool`.

**Rules**

- `evaluate` is a pure function. It does not read files, the network, or the clock. The same input gives the same
  answer.
- When the type does not match or there is no value, return `False` instead of raising. An exception does not stop
  the run, but that condition item becomes false (evidence `error`), which makes the cause hard to find.
- Announce the shape of the expected value with `value_schema` (JSON Schema). The pre-save check validates the value
  against this schema (a wrong value is a `condition.invalid_value` error), and the screens draw the input field from
  it. Add value checks the schema cannot express with the optional method `check_value(value)`. `applies_to` is only a
  hint for the screens and is not checked.

**Common mistakes**: leaving the prefix off the id so that it collides with a built-in operator name (`eq`, `in`, and
so on). You cannot overwrite a built-in implementation, and your operator drops out as `failed`.

**Data left after removal**: conditions that use the operator stay. The pre-save check reports
`condition.unknown_operator` as a **warning**, and at run time only that item is false (evidence `unknown_operator`)
with one warning event. Running the team is not blocked.

<!-- extdocs:facts condition-operator -->
- Registration: Register in the entry point group `agent_console.condition_operators` (constant `agent_console_conditions:CONDITION_OPERATORS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_conditions:ConditionOperator` — One condition operator. Registration key = `descriptor.id`.
- Built-in implementations: `any_item (agent-console-conditions)`, `contains (agent-console-conditions)`, `eq (agent-console-conditions)`, `exists (agent-console-conditions)`, `gt (agent-console-conditions)`, `gte (agent-console-conditions)`, `in (agent-console-conditions)`, `lt (agent-console-conditions)`, `lte (agent-console-conditions)`, `matches (agent-console-conditions)`, `ne (agent-console-conditions)`
- Examples:
  - package: [examples/extensions/agent-console-example-condition](../../examples/extensions/agent-console-example-condition/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## delegation-strategy

**When to use**: when you want to change how work is handed to the delegates connected by delegation edges. The
built-in implementations hand work to the backend's subagent feature (`sdk-subagents`) or call each delegate as a
separate run (`host`). If the order of handing out work or the way of combining results differs, such as handing out
in turn, voting, or auctions, that is a new strategy.

**Minimal shape**: `descriptor` (`DelegationStrategyDescriptor`), `validate(plan) -> list[Issue]`, and
`async run(plan, ctx) -> AgentResult`. `plan` (`DelegationPlan`) is the delegator's request and the list of delegates.
To actually call a delegate, use `ctx.invoke_node` (each delegate gets its own run history).

**Rules**

- The descriptor values define the team check: `member_fields` (the settings fields read from the delegate nodes),
  `max_depth` (the delegation depth limit), `composable` (whether it can be combined with other strategies on the same
  delegator), and `requires_backend_capability` (the capability the delegator's backend must have). Mixing a strategy
  with `composable = false` with other strategies is a `team.mixed_strategies` error, and a delegator backend without
  the required capability is a `team.backend_capability_missing` error.
- To allow mixing, also implement the optional protocol `ComposableDelegation`.
- The strategy decides whether the delegator fails when one delegate fails. Use your own prefix for failure codes.

**Common mistakes**: creating and calling a backend directly inside `run`. Delegate runs must go through the engine
(`ctx.invoke_node`) so that run history, canceling, and questions carry through.

**Data left after removal**: delegation edges that chose the strategy stay. The pre-save check reports
`team.unknown_strategy` as a **warning**, and at run time the delegator node fails with `agent.unknown_strategy`.

<!-- extdocs:facts delegation-strategy -->
- Registration: Register in the entry point group `agent_console.delegation_strategies` (constant `agent_console_runtime:DELEGATION_STRATEGIES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_runtime:DelegationStrategy` — Delegation strategy. Plugins register it via `agent_console.delegation_strategies`.
  - `agent_console_runtime:ComposableDelegation` — Optional protocol: a delegation strategy that can run combined with others in one delegator.
  - `agent_console_runtime:DelegationPlan` — Delegation run plan: the delegator request + the list of delegates.
- Built-in implementations: `host (agent-console-delegation-host)`, `sdk-subagents (agent-console-nodes-core)`
- Examples:
  - package: [examples/extensions/agent-console-example-delegation](../../examples/extensions/agent-console-example-delegation/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## edge-type

**When to use**: when the relationship between two nodes differs from the built-in edge types (flow, data, condition,
loop, delegation, reply, and so on). Examples are a flow that transforms the value it passes, an edge that allows a
specific interaction, and an edge that receives and handles failures.

**Minimal shape**: `descriptor` (`EdgeTypeDescriptor`) and one method, `activates(source, edge)`. The engine calls it
when the upstream node finishes, and the return value decides whether to wake the downstream node (`Activation`),
block that path (`Blocked`), or do nothing (`None`).

**Rules**

- `scheduling` defines what the engine does. `flow` calls `activates` when the upstream node finishes, `entry` at the
  start of the run (taking the run input to the entry node), and `exit` when the upstream node finishes (the value that
  passes becomes the reply). `none` does not call it (edges the nodes interpret, such as delegation, resources, and
  interaction permissions). The cycle check counts only `flow` edges.
- `connects` lists the pairs of node roles the edge can connect. The team check blocks edges that do not match with
  the error `team.connects_mismatch`. Role names are the `role` strings of node type descriptors.
- For an edge that allows interactions, write the interaction kind ids in `interaction.kinds`. Only nodes this edge
  leaves from can open those requests.
- Add semantic checks of the settings (what the schema cannot express) with the optional protocol `EdgeValidator`.

**Common mistakes**: calling outside systems while transforming values in `activates`. This function must be
synchronous and deterministic. Do slow work in a node.

**Data left after removal**: teams that use the edge stay. The check reports `unknown_edge_type` as an **error**, and
that team is blocked by the pre-run check. Other teams run as usual.

<!-- extdocs:facts edge-type -->
- Registration: Register in the entry point group `agent_console.edge_types` (constant `agent_console_runtime:EDGE_TYPES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_runtime:EdgeType` — Edge type. The engine calls `activates` according to the descriptor's `scheduling`.
  - `agent_console_runtime:EdgeValidator` — Optional edge type capability: semantic check of edge config (after schema, pre-save).
- Built-in implementations: `ask_user (agent-console-nodes-core)`, `data (agent-console-nodes-core)`, `delegate (agent-console-nodes-core)`, `handoff (agent-console-nodes-core)`, `loop (agent-console-nodes-core)`, `message (agent-console-nodes-core)`, `on_error (agent-console-nodes-core)`, `reply (agent-console-nodes-core)`, `subagent (agent-console-nodes-core)`, `uses (agent-console-nodes-core)`, `when (agent-console-nodes-core)`
- Examples:
  - package: [examples/extensions/agent-console-example-edges](../../examples/extensions/agent-console-example-edges/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## interaction-kind

**When to use**: when what a run needs from the user has a different shape from the built-in kinds (question, review,
tool permission). These are exchanges with a fixed request and response shape, such as a signature, choosing among
several items, or entering a number.

**Minimal shape**: a descriptor (`InteractionKindDescriptor`) is all you need: `request_schema` and `response_schema`
(JSON Schema) and screen hints (`ui_hints`). When the entry point points to a descriptor object, the server wraps it
in `StaticInteractionKind`.

**Rules**

- The server and the engine validate the response against `response_schema`. A wrong response is 422
  `validation_failed`.
- If the web knows the renderer name, it shows that screen. If it does not, it shows a form built from the response
  schema, so the kind works without web code. If you need a dedicated screen, see [Web](web.md).
- Only nodes with an outgoing edge that allows the kind (`interaction.kinds` of an [edge-type](#edge-type)) can open
  the request. Without an allowing edge, the request does not open and the backend gets `unavailable` back.

**Common mistakes**: creating only the kind and no allowing edge. The kind shows in the list, but no agent can open
the request. The [example](../../examples/extensions/agent-console-example-interactions/README.md) keeps the kind and
the allowing edge in one package.

**Data left after removal**: if the review settings of a user node choose that kind, the pre-save check reports
`review.unknown_kind` as an **error**. If you also removed the allowing edge, that edge is an `unknown_edge_type`
error. When a backend requests that kind, the request does not open.

<!-- extdocs:facts interaction-kind -->
- Registration: Register in the entry point group `agent_console.interaction_kinds` (constant `agent_console_runtime:INTERACTION_KINDS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_runtime:InteractionKind` — Interaction kind. Engine, server, and web see only `descriptor` (schemas, UI hints).
  - `agent_console_runtime:StaticInteractionKind` — A kind made of a descriptor only (wraps a descriptor object an entry point points to).
- Built-in implementations: `question (agent-console-nodes-core)`, `review (agent-console-nodes-core)`, `tool_permission (agent-console-nodes-core)`
- Examples:
  - package: [examples/extensions/agent-console-example-interactions](../../examples/extensions/agent-console-example-interactions/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## node-type

**When to use**: when a team needs a box that does something other than an agent, user, resource, or nested team.
This is work that takes values from input ports and puts results on output ports, such as transforming text, calling
an outside system, or waiting for a person to do something.

**Minimal shape**: `descriptor` (`NodeTypeDescriptor`: `id`, `title`, `config_schema`, ports),
`resolve_ports(config)`, `validate(config, ctx)`, and `async execute(ctx, inputs) -> NodeResult`.

**Rules**

- `execute` uses only `NodeContext`, not globals, environment variables, or the file system. Emitting events,
  checking for cancellation, and calling other nodes all go through the context. That way you can test with a fake
  context.
- If the ports change with the settings, turn on `dynamic_ports` in the descriptor and compute them in
  `resolve_ports`. Otherwise `static_ports` is enough.
- The descriptor `role` is the role name that `connects` of edge types matches. If you use a new role name, existing
  edge types cannot connect to it, so create an edge type as well.
- A new version with changed behavior can live next to the old one under the same id by raising `version`. If a node
  in a team does not set `type_version`, the highest version is used.
- Add `title`, `description`, and `x-ui` to the settings fields ([Settings schema](plugins.md#settings-schema)).

**Common mistakes**: raising exceptions for failures. Return expected failures as an error in `NodeResult` (a code
under your own prefix). The engine turns exceptions into a generic failure, which hides the cause.

**Data left after removal**: teams with nodes of that type stay. The check reports `unknown_node_type` as an
**error**, and that team is blocked by the pre-run check.

<!-- extdocs:facts node-type -->
- Registration: Register in the entry point group `agent_console.node_types` (constant `agent_console_runtime:NODE_TYPES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_runtime:NodeType` — Node type. The engine knows only this interface and finds concrete types in the registry.
  - `agent_console_runtime:NodeContext` — Context for one node run. Nodes use only this, not globals, env vars, or the file system.
  - `agent_console_runtime:NodeResult` — Result of one node run.
- Built-in implementations: `agent (agent-console-nodes-core)`, `resource (agent-console-nodes-core)`, `team (agent-console-nodes-core)`, `user (agent-console-nodes-core)`, `wiki-update (agent-console-link-wiki-runs)`
- Examples:
  - package: [examples/extensions/agent-console-example-nodes](../../examples/extensions/agent-console-example-nodes/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

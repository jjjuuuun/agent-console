# agent-console-teams

A pure library that computes the **semantics** of team graphs. It interprets entries and replies, delegates, resource attachments, and the allowed interactions (grants) per node,
validates the rules of mixed graphs, and builds each node's effective settings (4 layers + resource attachments, with provenance).

- **It knows no names.** Edge type, node type, delegation strategy, and interaction kind ids are not in this package. Decisions are based on
  - edge descriptors `scheduling` (`entry`, `exit`, `flow`, `none`), `invocation`, `interaction`, `connects`, `default_ports`
  - node type descriptors `role`, `executable`, `binds{kind, field}`
  - delegation strategy descriptors `max_depth`, `allows_outgoing_flow`, `member_fields`, `member_interaction_kinds`, `requires_backend_capability`
  - the settings `delegation.max_depth` and `settings_merge`, the backend's `capabilities.interactions`, and the optional hook `validate_settings`
- **The only entries and replies are explicit edges** (`scheduling=entry/exit`). Nothing is inferred from the graph shape.
  Automatic inference is used only in the **suggestion data** of validation issues (`Issue.suggestions[].patch`).
- Node and edge config keys (for example the node layer settings `settings` and the interaction edge `kinds`) are `TeamConventions` data.
  The defaults match the schemas of the default plugins (`ac-nodes-core`), and plugins that use other keys pass their own.
- It uses no files, databases, or networks. Agent definitions, common settings, resource lookups, backend capabilities, and hooks come in as arguments.

## Installation

```bash
uv sync --all-packages                    # inside the workspace
uv pip install ./packages/py/features/ac-teams     # standalone (dependencies: contracts, graph, registry, resources, settings)
```

## Minimal usage

```python
>>> from agent_console_contracts import Agent, WorkspaceSettings
>>> from agent_console_teams import effective_settings, team_plan, validate_team
>>> from agent_console_teams.testing import Kit

```

In real use, pass the descriptors from the registries (node and edge types, delegation strategies). Here a test descriptor bundle `Kit`
unrelated to the default plugin names is used (person `human-x`, worker `actor-x`, entry `hello`, reply `bye`, delegation `boss`, and so on).

```python
>>> k = Kit()
>>> graph = k.graph(
...     [k.person("me"), k.worker("lead", who="pl", settings={"model": "m-team"}), k.worker("be", who="backend")],
...     [
...         k.edge("m1", "entry", "me", "lead"),
...         k.edge("d1", "invoke", "lead", "be"),
...         k.edge("a1", "exit", "lead", "me"),
...     ],
... )
>>> plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
>>> plan.entry_nodes, plan.answer_nodes  # entry nodes (an entry edge comes in), reply nodes (an exit edge goes out)
(('lead',), ('lead',))
>>> [(link.member, link.strategy) for link in plan.delegates_of["lead"]]  # DelegationLink
[('be', 'inner')]
>>> plan.agent_refs  # node → agent definition id
{'lead': 'pl', 'be': 'backend'}

>>> workspace = WorkspaceSettings.model_validate(  # the common layer, delegation, settings_merge
...     {"agent_defaults": {"model": "m-common", "tools": ["Read"]}}
... )
>>> agents = {"pl": Agent(id="pl", name="PL"), "backend": Agent(id="backend", name="BE")}
>>> validate_team(
...     graph,
...     node_types=k.node_types,
...     edge_types=k.edge_types,
...     strategies=k.strategies,  # delegation strategy descriptors
...     agents=agents,
...     workspace=workspace,
...     resolve_ports=Kit.resolve_ports,  # dynamic port resolution (the app uses the registry implementations)
...     plan=plan,
... )
[]

>>> eff = effective_settings(plan, "lead", agents=agents, workspace=workspace, strategies=k.strategy_map)
>>> eff.value.model, eff.provenance["/model"], eff.value.tools, eff.provenance["/tools/0"]
('m-team', 'node', ['Read'], 'common')
>>> [layer.id for layer in eff.layers], eff.warnings, eff.inapplicable
(['common', 'team', 'agent', 'node'], [], [])

```

### Up to the run bundle (connection order)

```python
from agent_console_teams import node_bundle, node_settings

ns = node_settings(plan, "pl", agents=agents, workspace=ws, resource_types=types, resources=lookup)
# internally: resource_strategies(slot_key_of=attachment_slot_key(...)) → resolve_layers(schema, rules, table)
#       → placed_from_resolved
composed = node_bundle(
    ns, resource_types=types, resources=lookup, accepted_slots=caps.resource_slots
)
composed.bundle.slots, composed.bundle.sources, composed.issues
```

### Working with layers directly

```python
from agent_console_settings import Layer
from agent_console_teams import layers_for, merge_rules, resolve_settings

layers = layers_for(plan, "pl", agent=agent, workspace=ws)  # common → team → agent → node
# adding a layer is inserting one into the list
layers.insert(2, Layer("project", "프로젝트", {"model": "m"}))
ns = resolve_settings(layers, rules=merge_rules(ws, graph))
```

- Layers directly below common are put in with `scope_layers=[Layer(...)]` (`layers_for`, `agent_layers`, `node_settings`,
  `effective_settings`; for example the project folder of a project layer). This package does not know what layers mean, and omitting it changes nothing.
- Layer values are read **only for the fields that are set** (`model_dump(exclude_unset=True)`). Omitted = inherit; `null` and empty lists = set at that layer.
- `settings_merge` is merged in the order common → team and then passed as `rules` (`merge_rules`).
- The common layer is only `agent_defaults`. The old top-level key `default_backend` is not read (move the value to `agent_defaults.backend`).
- Merge problems (`Resolved.issues`), widenings (`find_widenings`), and format errors go to `EffectiveSettings.warnings`, and fields that do not apply
  to delegated nodes (outside the delegation strategy's `member_fields`) go to `EffectiveSettings.inapplicable`.
- User settings groups such as chat, editor, delegation, and interactions come from `user_settings(workspace, graph)` (defaults → common → team).

### Backend hooks

```python
from agent_console_contracts import AgentSettings, InteractionGrant, Issue


class MyHook:  # the SettingsValidator protocol
    def validate_settings(self, effective: AgentSettings, grant: InteractionGrant) -> list[Issue]:
        if asks_user(effective) and "approve" not in grant.kinds:
            return [
                Issue(
                    severity="warning",
                    code="interaction.no_path",
                    message="...",
                    details={"kinds": ["approve"]},
                )
            ]
        return []
```

The hook is called for each agent node that opens its own session (nodes that are not delegated + targets called by strategies with `shares_session` false), together with
that session's grant (`session_grant`: its own + the grants of delegates of same-session strategies, filtered by `member_interaction_kinds`).
If an `interaction.no_path` issue has no suggestion, a suggestion is attached that connects an interaction edge allowing `details.kinds`
to the user-side node. Hook exceptions become `team.validator_failed` warnings.

### Run path (engine results come in as arguments)

It does not import the engine. The app (server, CLI, tests) only assembles in the order below.

```python
from agent_console_teams import (
    merge_validation,
    prepare_run,
    run_blockers,
    team_plan,
    team_rules_apply,
    validate_team,
)

engine = runtime.validate(graph, services=services)  # engine validation (called by the app)
team = []
if team_rules_apply(engine):  # skipped when there is an unknown-type error
    team = validate_team(graph, ..., graph_checks=False, plan=plan)
issues = merge_validation(engine, team)  # for the screen: duplicates with the same meaning removed
blockers = run_blockers(engine, team)  # only the issues that block the run
if not blockers:
    prep = prepare_run(
        graph, plan, workspace
    )  # RunPreparation{grants, interaction_settings, flow_settings}
    await runtime.start(
        graph,
        ...,
        interaction_grants=prep.grants,
        interaction_settings=prep.interaction_settings,
        flow_settings=prep.flow_settings,  # loop and run limits (the effective setting `flow`)
    )
```

- `blocks_run(issue)`: `issue.blocks_run`, or severity error when absent.
- `merge_validation(..., equivalents=DEFAULT_EQUIVALENTS)`: drops a team issue when the same node has an engine error with the same meaning.
  The equivalence table is data `{team code: engine code prefix}` (default `team.agent_not_found` → `agent.not_found`). Pass a table for other plugin combinations.
- `team_rules_apply(engine, skip_prefixes=DEFAULT_TEAM_SKIP_PREFIXES)`: false when an engine error code starts with `unknown`.

### Execution backend pre-check

The resolution order is the settings layers as they are (node → agent → team → common `agent_defaults.backend`
→ the argument `default_backend`). Nodes that use a backend are identified by descriptors (executable nodes bound to an agent definition, or
nodes with `TeamConventions.backend_capability` in `capabilities`). Delegated nodes run in the delegator's session, so
only session owner nodes are blocked. A backend is never chosen automatically.

```python
from agent_console_teams import resolve_backends, unresolved_backends

resolved = resolve_backends(plan, agents=agents, workspace=ws)  # {node_id: backend_id | None}
blocked = unresolved_backends(plan, resolved, agents=agents)  # [UnresolvedBackend(node_id, label)]
```

### Screen summary

```python
from agent_console_teams import bundle_preview, plan_summary, validation_summary

summary = plan_summary(plan)  # TeamPlanSummary{entries, answers, grants}
# label, order, final, and stream of reply slots are read from config through the edge type descriptor reply_fields (JSON Pointers).
# without a value, the config_schema default at that location; without that, label = edge label, final = true, stream = false.
# this package has no config key names of reply edges.

validation_summary(
    merge_validation(engine, team)
)  # GraphValidationSummary{blocks_run, error_count, ...}

preview = bundle_preview(
    plan,
    "lead",
    resource_types=types,
    resources=lookup,
    backends={"b": caps},
    workspace=ws,
    strategies=strategies,
)
# BundlePreview{bundle, warnings}: slots not accepted (resource.slot_unsupported) + session-shared slots of delegated nodes
# (resource.slot_session_shared, slots not in the session owner backend's capabilities.subagent_slots). x-secret plain text becomes ***.
```

- Backend optional hook `PreviewNotes.preview_notes(effective, bundle) -> list[Issue]`: given `bundle_preview(..., notes={backend
  id: hook})`, the session owner backend's hook is called with the session owner's effective settings and this node's bundle, and the issues are appended (for example claude-sdk
  `observe.hook_probe_wrapped`, hook wrapping on). `catalog_from_registries` collects backends with the hook into
  `TeamCatalog.preview_notes`. Hook exceptions give `team.validator_failed` warnings.

- Run scope that is not enforced: `node_settings(..., backends={id: BackendCapabilities})` (or `resolve_settings`) adds the warning
  `limits.not_enforced` (path `/limits/<field>`) when the effective `limits` has a value but the item with **the same name** in the effective `backend`'s `capabilities.enforce` is not true.
  It is skipped when `limits` does not apply at this place (the delegation strategy's
  `member_fields`). Standalone function `limits_warnings(value, enforce)`. There is no field list in the code.

### Rule modules

`validate_team` runs the rule functions in order (`_validate.TEAM_RULES`): `_rules_structure` (edge rules, references) →
`_rules_entry` (entries, replies, reachability) → `_rules_delegation` (delegation) → `_rules_loops` (loops) → `_rules_teams` (nested teams) →
`_rules_interactions` (interactions, backend hooks, reviews) → `_rules_resources` (slots not accepted).
Rules read `TeamCheckContext` (`_check_context`) and accumulate issues with `add`. The computation of allowed edge kinds (descriptor ∩ config) is
one function, `_plan.edge_kinds`, shared by grant computation and validation.

### Finding usages

```python
from agent_console_teams import definition_references

refs = definition_references(
    "resource", "team-guide", graphs=graphs, agents=agents, workspace=ws, node_types=node_descs
)
# DefinitionReference[]: resource nodes (binds) → attachments in the team, node, agent, and common layers
```

It does not know node type names (`binds{kind, field}`, `TeamConventions` keys). When `kind` is a resource kind, settings layer attachments are found too.

### Attachment override checks and `x-secret` masking

```python
from agent_console_teams import agent_attachments, attachment_issues, graph_attachments

placed = graph_attachments(graph, plan=team_plan(graph, node_types=nt, edge_types=et))
issues = attachment_issues(placed, types=resource_types, resources=lookup)
# attachments without a resource are checked with the secret suspicion rules: secret_rules=SecretRules().with_extra(...) (default = the default rules)
# path = relative to the document: /settings/resources/0/config_override/env/API_KEY,
#   /nodes/1/config/settings/resources/0/config_override/..., /edges/3/config/config_override/...
```

- Locations: agent `/resources/<i>`, common settings `/agent_defaults/resources/<i>`, team layer `/settings/resources/<i>`,
  node layer `/nodes/<n>/config/<node_settings_key>/resources/<i>`, resource edges `/edges/<e>/config/<edge_override_key>`
  (only when `plan` is given; whether an edge is a resource edge is decided by descriptors).
- The check is `ac-resources.validate_attachment` (the kind check on the resource config with the override shallowly overlaid). Attachments without overrides are
  not checked, and when the `ref` resource is missing, only a warning is given. Whether to block saving is up to the caller (server: 422 on error).
- Safety nets for display: `mask_effective_secrets(effective, *, types, resources)` (effective settings `value.resources[].config_override`) and
  `mask_node_settings(settings, *, types, resources) -> (NodeSettings, ResourceLookup)` (bundle preview, both overrides and
  resource configs) replace values that are not `secret://` references at `x-secret` locations of the config schema with `***`.

## Validation rules (`TeamIssueCodes`)

| Code | Severity | Basis |
| --- | --- | --- |
| `team.no_entry` | error (`blocks_run`) | No `entry` edge goes to an executable node. Suggestion: make a node without incoming edges the entry |
| `team.no_reply` | warning | No `exit` edge. Suggestion: make a node without outgoing flow the reply |
| `team.unreachable` | warning | An executable node with no incoming `entry`, `flow`, or delegation edge (user-side nodes excluded). The same when only cycle edges that close a loop come in (they do not pass in the first iteration). Suggestion: make it an entry |
| `team.entry_not_executable` | warning | An entry edge goes to an `executable=false` node |
| `team.connects_mismatch` | error | The roles of the edge descriptor `connects` do not match |
| `team.agent_not_found` / `team.resource_not_found` | error / warning | The definition bound through `binds` is missing (only when `agents` and `resources` are given) |
| `team.mixed_invocation` | error | Received through flow or entry and also called through delegation (cycle edges that close a loop are not counted; see `flow.loop_invoked_only`) |
| `team.mixed_strategies` | error | A node's delegates use different delegation strategies, and one of them has a descriptor `composable` that is false (or unknown). Allowed when all are `composable` (mixed delegation). `details.not_composable`. Suggestion: change that edge to a delegation edge type of a strategy that can be combined (strategies already in use first; the strategy override key in the edge config is not carried over) |
| `team.unknown_strategy` | warning | An unregistered delegation strategy |
| `delegation.depth_exceeded` | error | Delegation depth > min(descriptor `max_depth`, setting `delegation.max_depth`). With strategy `max_depth: null`, only the setting. `details.path` = the delegation path. Constant `DELEGATION_DEPTH_EXCEEDED` |
| `team.delegation_cycle` | error | A cycle of delegation edges |
| `team.flow_from_delegate` | error | A flow edge from a delegated node (descriptor `allows_outgoing_flow=false`). `exit` (reply) is allowed |
| `team.backend_capability_missing` | error | The delegator's backend lacks the `requires_backend_capability` capability |
| `team.member_field_ignored` | warning | A delegated node sets a field outside `member_fields` differently from the delegator (for example backend) |
| `interaction.no_path` | warning | Emitted by backend hooks. Suggestion: add an interaction edge |
| `interaction.unsupported_in_delegate` | warning | A delegated node's grant is outside `member_interaction_kinds`. Suggestion: narrow the edge's `kinds` |
| `interaction.unsupported_by_backend` | warning | Outside the session backend's `capabilities.interactions`. Suggestion: narrow it |
| `interaction.kinds_not_allowed` | warning | The edge config `kinds` has kinds the descriptor does not allow |
| `review.dead_end` | warning | The ports of a scheduled node's review decisions (config `review.decisions`) lead nowhere. Suggestion: make them replies |
| `team.validator_failed` | warning | Hook exceptions (including exceptions of delegation strategy static checks, `details{strategy, method}`) |
| `delegation.invalid_config` | error | The delegator node config `delegation[strategy id]` (`TeamConventions.node_delegation_key`) does not match the strategy descriptor's `config_schema`. path `/delegation/<strategy id>/…`. Unknown strategies and nodes that are not delegators are not checked |
| `delegation.invalid_config_schema` | warning | The strategy descriptor's `config_schema` itself is wrong |
| `delegation.duplicate_member` | error | One delegator connects the same target more than once with the same (effective) strategy. An edge issue on the later edge, `details{delegator, member, strategy, edges}` |
| `delegation.duplicate_<group>_names` | error | Only when `delegation_checks` is given: a delegator uses two or more strategies, and the names those strategies declared through `declared_names` overlap within a group (for example `delegation.duplicate_host_tool_names`). Strategies whose `composable` is false are left out |
| `flow.max_iterations_invalid` | error | The effective maximum iterations of a cycle edge (descriptor `cycle`) (edge config `max_iterations` → setting `flow.max_iterations` → descriptor `cycle.max_iterations`, `ac-graph.effective_max_iterations`) is missing or below 1. An edge issue, path `/max_iterations` |
| `flow.loop_invoked_only` | error | A node in a loop region (`ac-graph.loop_regions`) is called only through delegation and has no incoming flow other than cycle edges (not scheduled) |
| `team.recursive` | error | A nested team node (descriptor `binds.kind == TeamConventions.team_kind`) puts back a team that is already on the path while following this team itself or its children and grandchildren. `details.path` = the team id path. Self-references are reported even without lookups |
| `team.nesting_exceeded` | error | Nesting depth (this team = 0) > the effective `delegation.max_nesting` (default data 3, null = unlimited). `details{depth, limit, path}` |
| `team.team_not_found` | error | The `teams=` lookup cannot find the team (pinned version `TeamConventions.node_version_key`). `details{team, version}` |
| `team.child_no_entry` | error | The child team has no entry (the child validation summary in `details.issues`) |

Nested team issues have `node_id` = the nested team node and `path` = `/nodes/<i>/config/<binds.field>` relative to the document. Child teams are
read with `validate_team(..., teams=lookup)` (`TeamLookup = (id, version|None) -> Graph|None`; `LookupError` also means "missing").
Without `teams`, only self-references are checked. While running, the engine blocks the same with the same codes (`team.recursive`, `team.nesting_exceeded`).
Team layer overrides of nested team nodes use `with_team_settings(graph, override)` (only the given values; objects are merged recursively).

Flow cycles are checked by `ac-graph.validate_graph(cycle_edge=descriptor_cycle_edge)`, which runs together when `graph_checks=True` (default).
A cycle is allowed when it has a cycle edge (descriptor `cycle`) (including sending a review rejection back to an earlier node); otherwise it is
a `cycle` issue with a suggestion to change the back edge into a cycle edge type. `none`, `entry`, and `exit` edges are left out of the cycle calculation,
so `user → A → user` is not a cycle.

Edge semantic checks (for example the condition of a condition edge) are an optional capability on the engine side, so this package does not call them directly. In standalone use,
inject them like `validate_team(..., edge_checks=lambda g: validate_edges(g, registries, services))`. The server (the pre-save check
of the runs module) combines engine validation (`validate_graph_with` → `validate_edges`) and team rules (`graph_checks=False`), so it does not
pass them.

Strategy-specific static checks work the same way. The optional methods of strategy objects, `static_issues(config, members)` and
`declared_names(config, members)`(ac-runtime `StaticDelegationChecks`·`DelegationNameDeclarer`, `members` =
`DelegationTarget`) are called only based on whether the methods exist. In standalone use, pass `validate_team(..., delegation_checks={strategy id: strategy object})`
or use `delegation_static_issues(plan, checks, delegators=, agents=)`; the server gets them from engine validation (node type `validate` calls the registered
delegation strategies), so it does not pass them. Strategy issues with an empty `node_id` go to the delegator, and for non-edge issues `/delegation/<strategy id>`
is put in front of `path`. The run-time `validate(plan)` still runs at run time.

### Suggestion data

`Issue.suggestions[{id, label, patch: GraphPatch}]`. The edge type is chosen by descriptor attributes (`scheduling`, `interaction`) and `connects`,
and it connects to the user-side node (the source of the entry or the target of the reply) if there is one; otherwise it creates a new node of the node type with the opposite role in `connects`
(the first type that is not bound to a definition and not hidden) and connects it. Ports are `default_ports` → the first port in the node's port list.
Suggestions that only change the edge type (`SuggestionBuilder.replace_kind`) are `remove_edge_ids` + `add_edges` (same id and ports, new type,
carrying over only the config keys the new type's schema declares). `SuggestionBuilder` lets other validators build suggestions the same way.

## Grant rules

- For each edge leaving the node whose descriptor has `interaction`, the allowed kinds = `interaction.kinds` ∩ the edge config `kinds` (when it is a list).
- Node grant = their union (in order of first appearance). Wait limit = the shortest `timeout_seconds` among the edge configs,
  behavior on timeout = that edge's `on_timeout` (otherwise the first one set). When neither exists, null (follows the setting `interaction.*`).
- `session_grant(plan, delegator, strategies)`: the delegator's grant + the delegates' grants (filtered by the delegation strategy's `member_interaction_kinds`).
  Targets of strategies whose descriptor `shares_session` is false (targets run in their own session, for example `host`) add neither kinds nor wait limits.
  `shares_session(link, strategies)` and `runs_in_own_session(plan, node_id, strategies)` give the same
  decision, and with `prepare_run(..., strategies=)` the engine wait grants are per session too.

## Session totals

- `session_summary(plan, strategies)`: `GraphSessionSummary{nodes, delegated}` for team list and team overview summaries. The session value of an edge =
  for delegation edges, the `session` of the effective delegation strategy (edge config `strategy` → the type default); for other edges, the edge type's `session`.
  Counted = nodes reached by edges whose `opens_session` is not false and that have a session value. Targets whose incoming delegation edges all have the same session value
  are counted under that value in `delegated[value]`. It does not know what the values mean (the screen picks the values it knows). None if there are no session values at all.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-teams`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
UV_LINK_MODE=copy uv run pytest packages/py/features/ac-teams
```

Tests check every rule without the default plugins, using node and edge types and delegation strategy descriptors with **arbitrary names**.
That descriptor bundle is the public submodule `agent_console_teams.testing` (`KITS`, `Kit(names)`), so tests in other projects can use it too.

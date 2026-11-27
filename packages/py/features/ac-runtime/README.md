# agent-console-runtime

The graph execution engine (a token-based asyncio scheduler) and its extension interfaces.
The engine does not know any specific node type, edge type, or backend. Every capability comes in as an implementation registered in `Registries`.

## Installation

```bash
uv sync --all-packages                     # inside the workspace
uv pip install ./packages/py/features/ac-runtime    # standalone
```

Dependencies: `agent-console-contracts`, `agent-console-registry`, `agent-console-graph` (it does not know stores, routing, or plugins)

## Minimal usage

```python
>>> import asyncio
>>> from agent_console_runtime import GraphRuntime, InMemoryEventBus
>>> from agent_console_runtime.testing import (
...     InMemoryRecorder,
...     edge,
...     graph,
...     make_registries,
...     node,
...     reply,
... )

```

In real use, installed types are read with `registries = Registries(); load_registries(registries)` (entry points `agent_console.node_types` /
`edge_types` / `backends`). Here, test types (the `t.step` node and the `t.flow`, `t.entry`, `t.exit` edges) show that the engine
does not know any type.

```python
>>> async def main():
...     registries = make_registries()
...     bus = InMemoryEventBus()
...     runtime = GraphRuntime(registries, InMemoryRecorder(), bus, max_concurrency=4)
...     # the graph must have an entry edge (descriptor scheduling="entry"); otherwise NoEntryError.
...     g = graph(
...         [node("a"), node("b", outputs={"out": "완료"})],
...         [edge("a", "b"), reply("b")],
...         entries=["a"],  # an entry edge from the user slot you → a
...     )
...     events = bus.subscribe()  # pass run_id= to receive only one Run
...     handle = await runtime.start(g, {"text": "hello"}, origin="api")
...     async for event in events:
...         if event.type == "run.reply":
...             print("답변:", event.payload["text"])
...         if event.type == "run.completed":
...             break
...     events.close()
...     run = await handle.wait()  # or runtime.cancel(handle.run_id)
...     print(run.status)
...     await runtime.shutdown(timeout=10)  # app shutdown: cooperative cancel → tasks force-cancelled past the timeout
>>> asyncio.run(main())
답변: 완료
completed

```

**Order of publishing the end**: when `RunHandle.run` shows a final status (`completed`, `failed`, `cancelled`, `interrupted`, parked
`waiting`), that Run's records (every event including replies (`run.reply`), the final Run save, and the `run.<status>` event) are
already saved in the store and published through `event_sink`. While finishing, it shows the previous status (`running` and so on).

`start(..., conversation_id=)` is Run metadata (`Run.conversation_id`). The engine does not know its meaning and only records it, and the same value is copied to that Run's
interactions (`Interaction.conversation_id`) (the chat adapter fills it).

In production, pass `SqliteStorage`/`InMemoryStorage` from `agent_console_store` as the recorder (structural typing).
At server start, `recover_unfinished_runs(storage, sink=bus)` cleans up Runs from the previous process as `interrupted`
(pending interactions become `expired(interrupted)` + `interaction.closed`, and unfinished NodeRuns including waiting ones become `cancelled(interrupted)`).

## Extension interfaces

| Point | Protocol | Key methods |
| --- | --- | --- |
| Node type | `NodeType` | `descriptor`, `resolve_ports(config)`, `validate(config, ValidationContext)`, `async execute(NodeContext, inputs) -> NodeResult` |
| Edge type | `EdgeType` | `descriptor`, `activates(NodeRunView, EdgeSpec) -> Activation \| Blocked \| None`. `Activation.condition` (evidence → `edge.traversed.condition`) and `warnings` (→ `log.warning`); `Blocked(reason, condition, warnings)` = dead path + `edge.skipped`. Optional capability `EdgeValidator.validate_edge(edge, EdgeValidationContext)` (semantic check before saving, called by `validate_graph_with`) |
| Optional hook | `NODE_ACTOR_HOOK = "actor_of"` | `actor_of(config) -> str \| None`: the agent definition id of this node slot. The engine writes it to the `actor` header of that node's `node.*`, `run.reply`, and `ctx.emit` events |
| Optional hook | `NODE_NAME_HOOK = "display_name"` | `display_name(config, services) -> str \| None`: the name to use in user-facing text when the node has no `label` (for example the name of the bound agent definition). Run failure summaries and delegation refusal text call the node by `node_display_name` (label → this hook → the type `title`) and put the id in `details.node_id`. Failure summaries carry over the cause's `ErrorInfo.fix` as is |
| Execution backend | `ExecutionBackend` | `descriptor`, `async list_models()`, `async run(AgentRequest, BackendEventSink, CancelToken) -> AgentResult`. `AgentRequest.run_folder` (the node run folder for artifacts, or None) and `run_context` (`run_id`, `node_path`) are filled by the node (where hook probe records go) |
| Optional sink capability | `SubagentResultListener` | `async on_subagent_result(name, *, text, status, actor, tool_use_id)`: each time one subagent call ends. Backends notify only when `isinstance(sink, SubagentResultListener)`, and the delegation strategy wraps the sink to emit target replies (`emit_replies`) |
| Optional hook | `ConfigurableBackend` (`BACKEND_OPTIONS_HOOK = "from_options"`) | `classmethod from_options(options: Mapping, *, secrets: SecretResolver, environ: Mapping[str, str]) -> ExecutionBackend`. Implemented by backends that can be rebuilt from the app setting `backends.<id>`. The app only checks whether the hook exists, and the backend package interprets the keys (unknown keys raise `ValueError`). If the hook accepts the keyword `host` (`BACKEND_HOST_PARAM`), the app passes `BackendHostContext(workspace_dir=…)` (checked with `accepts_host_context`; app workspace = the base for relative paths the app manages and for the one-per-app subscription credentials folder. Project folders are not passed) |
| Optional capability | `StatusCapableBackend` / `ProbeCapableBackend` (with descriptor `capabilities.status` and `probe`) | `async status(BackendCheckContext) -> BackendReadiness` (no model or network calls, finishes quickly), `async probe(BackendCheckContext, timeout_s) -> BackendProbeResult` (one shortest real call; failures are `ok=false` + `reason`). `BackendCheckContext` has `backend_id`, `clock`, `has_secret(name)` (existence only, no value). The lookup service `BackendReadinessService(backends, redact=, has_secret=, probe_timeout_max_s=)`: without the capability, status `unknown` and probe raises `ProbeUnsupportedError`; time limits and truncation; concurrent probes of the same backend are merged; response text is masked; logs contain only id, ok, reason, and duration. Service text is data (`texts=ReadinessTexts(...)`); a sentence with a value (`probe_timeout`, `{seconds}`) is also sent as source template + values in the response `text_templates` (only entries whose filled text equals the field are kept, and they are masked with the field), so the web can translate it. Text you change is not translated (it no longer matches the catalog key); to translate it, put your template as a `text` key in a catalog folder (`mod-i18n.catalog_dirs`) |
| Optional capability (model discovery) | `ModelDiscoveryCapableBackend` (with descriptor `capabilities.model_discovery`) | `async discover_models(BackendCheckContext, timeout_s) -> ModelDiscoveryResult(ok, models, method, reason, unsupported, details)`: lists the models the account can use **without calling a model**. Failures are `ok=False` + `reason` (`ModelDiscoveryReasons`, open vocabulary); "cannot list with this sign-in" is `unsupported=True`. `list_models()` keeps meaning "the administrator's configured list". See [Backend model lists](#backend-model-lists) |
| Optional capability (sign-in) | `LoginCapableBackend` / `LogoutCapableBackend` (with descriptor `capabilities.login`, `logout`, and `login_methods`) | `async start_login(BackendLoginContext, method_id) -> LoginDriver`, `async logout(BackendLoginContext, method_id) -> BackendLogoutResult`. `LoginDriver`: `progress() -> LoginProgress` (phase, message, open_url, needs_code, code_label, accepts_keys, screen, warnings, reason, details, fixes), `async wait_changed(timeout)`, `async send_text`, `send_key`, `async cancel()`, `secrets_to_mask()`. Refusing to start raises `LoginRefusedError(code, message)`. The session service `BackendLoginService(backends, redact=, environ=, timeout_default_s=, timeout_max_s=, heartbeat_s=, retain_s=, screen_max_lines=)`: one session for the whole server (`LoginBusyError`), optional `on_account_change(backend_id)` after a session ends or a sign-out returns, time limit → `expired`, lost heartbeat → `cancelled` (reason `heartbeat`), driver `cancel` on cancel and `aclose` (shutdown hook), response masking (input values and their fragments of 5 or more characters through `mask_values` + the injected `redact`), logs contain only session id, backend id, method, phase, reason, and duration. A driver reports sentences with values as `LoginProgress.text_templates` (JSON Pointer in the session response, such as `/message` or `/warnings/0` → `TextTemplate` list); the service keeps only entries that match the field (`matching_text_templates`), carries warning templates over when it stops a session, and masks them with the field. Service text is data (`texts=LoginTexts(...)`, `expired` `{minutes}` and `logout_timeout` `{seconds}` are sent as templates too); changed text is not translated unless your catalog folder (`mod-i18n.catalog_dirs`) has it as a `text` key. `compact_number(x)` gives the value that prints like the old `{x:g}`. Test helpers `agent_console_runtime.testing_login` (`ManualLoginDriver`, `LoginBackendStub`) |
| Secret provider | `SecretProvider` | `get_secret(name) -> str \| None` (default implementation `EnvSecretProvider(environ)`) |
| Delegation strategy | `DelegationStrategy` | `descriptor: DelegationStrategyDescriptor`, `validate(DelegationPlan) -> list[Issue]`, `async run(DelegationPlan, NodeContext) -> AgentResult`. Registry `registries.delegation_strategies` (= `extension(DELEGATION_STRATEGIES_EXTENSION)`), entry point `agent_console.delegation_strategies`. Optional protocol `ComposableDelegation` (`contribute(plan, ctx) -> DelegationContribution`, descriptor `composable`): the node merges the results of several strategies with `merge_contributions`, adds them to the request with `apply_contribution`, and calls the backend once (mixed delegation). Optional protocols at save time: `StaticDelegationChecks` (`static_issues(config, members) -> list[Issue]`, static rules beyond the schema) and `DelegationNameDeclarer` (`declared_names(config, members) -> {group: [names]}`, example groups `DelegationNameGroups`, conflict code `duplicate_names_code(group)`); targets are `DelegationMemberView` (static fields) |
| Interaction kind | `InteractionKind` | `descriptor: InteractionKindDescriptor` (request and response schemas, `expire_response`, screen hints). Registry `registries.interaction_kinds` (= `extension(INTERACTION_KINDS_EXTENSION)`), entry point `agent_console.interaction_kinds` (loaded by `load_registries`; even if it points to a descriptor object, it is wrapped in `StaticInteractionKind`) |
| Storage | `RunRecorder` | `runs.save/save_node_run/list_node_runs/interrupt_unfinished`, `events.append/append_many/last_seq`, `interactions.save/get/close/close_pending` (`InteractionWriter`; `close` is conditional on pending, and if already closed, raises an exception with `code == "interaction_closed"` and an `interaction` attribute) |
| Publishing | `EventSink` | `publish(event)` (must not block) |
| Child Run preparation | `ChildRunPreparer` | `(ChildRunRequest) -> ChildRunPreparation \| Awaitable[...]`. `GraphRuntime(child_preparer=)` (can be swapped through the attribute). Raise `GraphValidationError` to block |

Registry keys must equal the descriptor `id` (looked up by `NodeSpec.type` and `EdgeSpec.kind`).
Extension points the runtime does not know (for example classifiers defined by plugins) are held with `registries.extension("my_classifiers", validator=as_x)`.
With a validator attached, entry points, modules, `register(registries)` plugins, and direct `register` calls all go through the same check (rejection →
`InvalidExtensionError`, `failed` in loaders). The default registries (nodes, edges, backends, secret providers, delegation strategies, interaction kinds) already have
`as_node_type` and the like attached.

```python
from agent_console_runtime import load_registry_plugins, session_refs

# settings plugins.modules: register(registries) plugins. Keys not in enabled are removed and reported as "disabled"
reports = load_registry_plugins(["my_pkg.plugin:register"], registries, enabled=None)

# sessions of the saved conversation (contract SessionRef) → node service SESSIONS value (engine SessionRef)
services = services.with_(SESSIONS, session_refs(conversation_sessions))
```

### NodeContext

`run`, `graph`, `node`, `config`, `attempt`, `iteration`, `actor`, `registries`, `backends`, `services`, `secrets`,
`cancel`, `clock`/`now()`, `node_path`, `child_path(node_id)`, `await emit(type, payload, raw=, evidence=, actor=, node_path=)`,
`await emit_replies(node_id, outputs, status=, actor=)`,
`await request_input(InteractionRequest) -> InteractionOutcome`, `interaction_grant`, `incoming(port=None) -> list[Incoming]`,
`previous_session_id`, `await invoke_node(node_id, inputs, by_edge=, max_depth=None, tool_use_id=None) -> NodeRunView`, `call`, `invoked_by`,
`await run_child(graph, input=None, graph_version=None, services=None) -> ChildRunResult`.

- `incoming`: the values that came into this node (one `Incoming{port, edge_id, source_node, source_port, value}` per traversed edge, in incoming edge order).
  For compatibility, the `inputs` of `execute` hold only the first value per port. Use this to get all values merged by join `all`.
  In loop iterations (see "Loops" below), values that arrived before the previous iteration and remain get `carried=True`, and the new value comes first in `inputs`.
- `iteration`: the loop iteration (from 0). `previous_session_id`: the `backend_session_id` of the same node's result in the previous iteration (None if absent).

- `emit`: the engine fills the header fields (run_id, seq, ts, attempt). `run.*`, `node.*`, and `edge.*` are engine-only.
  Known types have their contract payload format checked. `NodeContext` satisfies `BackendEventSink`, so `backend.run(req, ctx, ctx.cancel)`.
  Omitting `actor` uses the node's actor, and omitting `node_path` uses `[node]`. Events of a delegate (subagent) are emitted
  with `node_path=ctx.child_path(target)` and `actor=target agent`. A path that does not start with this node's path raises `ValueError`.
- `emit_replies`: evaluates the reply edges (`scheduling = exit`) of the target nodes reached from this node through `invocation` edges and emits `run.reply`
  (targets are not scheduled, so the delegation strategy calls it per result). Raises `ValueError` if it is not a call target.
- `services`: typed lookup of app-provided services. The plugin that uses a service defines and publishes `ServiceKey[T]("name")`, and the app injects with the same key.
- `secrets`: `resolve("secret://name")`, `resolve_refs(obj)`. Resolved values are masked as `[REDACTED]` in events and error messages.

### Platform tools (`HostTool`, runtime only)

A delegation strategy builds tools for the model and puts them into `AgentRequest.host_tools`, and a backend that declares `capabilities.host_tools`
calls `handler` for each model call. It is not a contract type and does not appear in `AgentRequest.model_dump()`.

- `HostTool(name, description, input_schema, handler, call_handler=None)`, `HostToolResult(text, is_error=False)`,
  `HostToolHandler = Callable[[dict], Awaitable[HostToolResult]]`,
  `HostToolCallHandler = Callable[[dict, str | None], Awaitable[HostToolResult]]` (a handler that also receives the call id)
- Shared by backends: `await call_host_tool(tool, args, cancel=, tool_use_id=None)` (exceptions → error results (type name only); run cancellation →
  the handler is cancelled and an error result is returned; outside cancellation propagates as is. If the tool has `call_handler`, it is called with the call id the backend
  knows), `duplicate_host_tool_names(tools)`, `object_input_schema(schema)`
- Delegation tool call id: passed with `invoke_node(tool_use_id=)`, it goes into `tool_use_id` of the target NodeRun's `node.*` payload,
  so the delegator's tool call event and the target run are linked by explicit id (null if unknown).

```python
>>> import asyncio
>>> from agent_console_runtime import HostTool, HostToolResult, call_host_tool
>>> async def handler(args):
...     return HostToolResult(text=f"맡김: {args['task']}")
>>> tool = HostTool("delegate", "다른 에이전트에게 맡긴다", {"type": "object"}, handler)
>>> asyncio.run(call_host_tool(tool, {"task": "검토"}))
HostToolResult(text='맡김: 검토', is_error=False)

```

### Session record archiving and restore

When a backend's optional method `session_archive()` returns a `SessionArchive` (`files`, `status`, `restore`), the assembly (a link module) archives the source
of a conversation node's session in the project folder and restores it in another app to continue. The status values are the contract `KnownSessionStates`
(`available`, `relocatable`, `missing`; the assembly adds `archived` and `not_applicable`). `BackendSessionArchives(lookup)` finds it by backend id
(None if absent = `not_applicable`), and `JsonlFolderSessionArchive(root, key)` is a shared implementation for the shape `<root>/<cwd key>/<session>.jsonl` + `<session>/`
(it handles only that session's files, and restore writes only to `<root>/<current key>/`. Name checks and link skipping are `copy_files` and `session_files_in`).

### Backend model lists

`merge_models(configured, discovered)` is a pure function: the configured list comes first and in its order, models only the lookup
found follow in the backend's order, and the same `id` (exact string match) is one entry where non-empty configured `title`,
`description`, `context_window` and configured `attributes` keys win. `sources` says where each entry came from.

`BackendModelCatalogService(backends, *, enabled=, disabled_backends=, ttl_s=, failure_ttl_s=, timeout_s=, limits=, redact=,
has_secret=, clock=, monotonic=)` serves `catalog(backend_id, refresh=) -> BackendModelCatalog` and `models(backend_id)`:
a per-backend memory cache (success `ttl_s`, failure `failure_ttl_s`), one lookup for concurrent requests, the last good list as
`stale` while a new lookup runs or after it fails, `failed` + warning issue `backend.model_discovery_failed`
(`details.backend_id`, `reason`) instead of an error, `disabled` and `unsupported` states, length limits `ModelListLimits`
(over-long ids are dropped), masking through `redact`, and logs with only backend id, state, reason, method, count, and
duration. `invalidate(backend_id=None)` clears the cache (for example after sign-in), `aclose()` stops lookups in progress.

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, BackendDescriptor, ModelInfo
>>> from agent_console_runtime import BackendModelCatalogService, ModelDiscoveryResult

>>> class Listing:
...     descriptor = BackendDescriptor(
...         id="b", title="B", capabilities=BackendCapabilities(model_discovery=True)
...     )
...     async def list_models(self):
...         return [ModelInfo(id="m-2", title="Pinned")]
...     async def discover_models(self, ctx, timeout_s):
...         return ModelDiscoveryResult(ok=True, models=[{"id": "m-1"}, {"id": "m-2", "title": "API"}])
...     async def run(self, req, sink, cancel): ...

>>> catalog = asyncio.run(BackendModelCatalogService(lambda: {"b": Listing()}).catalog("b"))
>>> catalog.discovery.state, [(m.id, m.title, m.sources) for m in catalog.models]
('ok', [('m-2', 'Pinned', ['config', 'discovered']), ('m-1', None, ['discovered'])])

```

## Scheduler semantics

The engine does not know edge type or node type names. It looks only at the edge descriptor `scheduling` and the node descriptor `executable`
(`agent_console_graph.schedule_view`).

| `scheduling` | Engine behavior | Topology and cycles |
| --- | --- | --- |
| `entry` | `activates` is called when the Run starts. The source appears as a successful result whose output is `{source port: Run input dict}`. The passed value goes into the input port of the target node (the entry) | Excluded |
| `flow` | When the source ends (succeeded or failed), `activates` → if it passes, the value goes into the target input port; otherwise dead | Included |
| `exit` | When the source ends (succeeded or failed), `activates` → if it passes, `run.reply` (if the value is a `Reply`, label, order, and final; strings as is; anything else as JSON) | Excluded |
| `none` | Not called (the node interprets it, for delegation, resources, allowed interactions, and so on) | Excluded |

- When a Run starts, the graph is deep-copied and frozen, and `graph_version = graph_hash(graph)`. It is validated before starting by default (`GraphValidationError`).
- **The only entries are explicit `entry` edges.** Nodes without incoming edges are never inferred as entries. If there is no `entry` edge into an executable node,
  no Run is created (`NoEntryError`, issue code `no_entry`, even with `validate=False`).
- Scheduled nodes = nodes with `executable=true` and at least one incoming `entry` or `flow` edge. The rest (call targets, `executable=false` nodes such as resources,
  nodes not fully connected, user slots with only entry and reply edges) get neither NodeRuns nor events.
  `flow` edges coming from unscheduled nodes are dead from the start.
- Replies (`exit`) go out right after the source node's `node.completed`/`node.failed`, before downstream flow. Passing a reply edge does not "handle" a failure.
  `entry` and `exit` edges do not emit `edge.traversed` (they are linked through the `edge_id` of `run.reply`).
- join `any` (default): runs right away on the first edge that passes (inputs are only what arrived; later arrivals are ignored). `all`: runs when no edges are open and at least one passed.
  If all incoming edges are dead, the node is settled as `skipped` and that propagates downstream (dead-path elimination). Nodes never reached are `skipped` too.
- A failed node is "handled" if at least one of its outgoing edges passes. If there is an unhandled failure, the Run is `failed` (`node_failed`); otherwise `completed`.
- The concurrency limit `max_concurrency` applies to the whole runtime (all Runs combined). Nodes waiting for interactions give their slot back.
- Cancellation: the `CancelToken` propagates to running nodes (`on_cancel` callback) → after `cancel_grace` seconds the remaining tasks are cancelled with asyncio → running and queued nodes become `cancelled`, unreached nodes `skipped`, and the Run `cancelled`.
- All records are serialized into one queue per Run and executed on a worker thread, and consecutive events are batched with `append_many`, **saved and then published**.

## Loops: cycle edges

The engine does not know edge names and looks only at the edge type descriptor `cycle` (cycle edges). Validation is `validate_graph(cycle_edge=descriptor_cycle_edge)`:
every flow cycle must have at least one cycle edge (otherwise `cycle`).

- **Loop region** (`agent_console_graph.loop_regions`): the nodes on the flow paths from `t` to `s` of a cycle edge `e(s → t)` (computed with every cycle edge left out).
- When `s` ends and `e.activates` passes: if the number of times `e` has opened the region so far, `k`, is below the limit `m`, the region is opened again.
  Region nodes become pending as **new NodeRuns** (`iteration` = previous + 1), flow edges inside the region open, and `t` gets the value of `e` (`edge_id = e` in `ctx.incoming`).
  Event `loop.iteration{edge_id, iteration (= the new iteration of t), nodes}`. If `k ≥ m`, `e` is dead with `loop.exhausted{edge_id, iteration = k, max_iterations = m}`.
- Limit `m` = edge config `max_iterations` → `max_iterations` of `start(flow_settings=)` (otherwise the constructor's `flow_settings`) → descriptor `cycle.max_iterations`
  (`effective_max_iterations`). If it is not an integer or is below 1, the region is not reopened (pre-save validation blocks it).
- If other nodes in the region are still running, queued, or in a live wait, reopening waits until they finish (iteration boundary = when the region is quiet).
- **Edges leaving the region** activate downstream right away when they pass in that iteration. Downstream runs only once (if it already finished, it is not reopened).
  If they do not pass, they are not settled as dead while the region can still reopen; they wait (for example, approval after two rejections: the downstream of the approval side is not skipped early).
  When the loop ends (the cycle edge does not pass, the limit is reached, or the source node is skipped), they become dead then.
- **Nested loops**: when the outer region reopens, the counts of the cycle edges inside it go back to 0.
- **Safety limit**: if the number of node runs (activations) in one Run exceeds `flow.max_node_runs` (default 200, None = unlimited), the Run is `failed`
  (`ErrorInfo.code = flow.max_node_runs_exceeded`, `details.limit`). Running nodes become `cancelled` with the same error.
- Unhandled failures from earlier iterations remain and make the Run `failed`. `totals` is the sum of usage across all iterations.
- Restart recovery and resuming: the NodeRun key is (run_id, node_id, attempt, iteration, call), so only unfinished iterations become `cancelled` (payload `iteration`).
  `resume_options` looks at the last iteration per node. A resumed Run counts loop iterations from 0 again.

```python
>>> import asyncio
>>> from agent_console_contracts import FlowSettings
>>> from agent_console_runtime.testing import BUILDERS as b, make_harness
>>> h = make_harness()  # the test edge `t.loop` has a descriptor cycle (max_iterations 3)
>>> g = b.graph(
...     [b.node("draft"), b.node("check", outputs={"out": "again"})],
...     [b.edge("draft", "check"), b.edge("check", "draft", kind="t.loop")],
...     entries=["draft"],
... )
>>> run = asyncio.run(h.make().run(g, flow_settings=FlowSettings(max_iterations=1)))
>>> sorted((nr.node_id, nr.iteration) for nr in h.recorder.runs.list_node_runs(run.id))
[('check', 0), ('check', 1), ('draft', 0), ('draft', 1)]

```

## Call NodeRuns: `ctx.invoke_node`

Used when a delegation strategy (for example the standalone delegation `host`) runs the target of an `invocation` edge as **its own NodeRun**.
The target node type's `execute` runs along the same path as scheduled nodes (interactions, events, records, cancellation). The engine does not know edge or strategy names.

- Allowed: only when `by_edge` is an edge from the calling node to `node_id`, its descriptor has `invocation`, and the target is executable
  (otherwise `ValueError`). A context created outside the engine raises `RuntimeError`.
- Records: the target NodeRun's `iteration` = the calling node's iteration, `call` = the order in which this Run called that node (from 0, or from 1 for nodes that are also scheduled),
  `invoked_by` = the calling node's path. `node.*` events have `node_path = [...calling node path, target]` and payload `call`. The target's reply (`exit`) edges are
  evaluated by the engine, which emits `run.reply`. The target's `ctx.node_path` is the same path, so events, interactions, and further calls (depth 2) inside the target continue beneath it.
- Result: `NodeRunView` (`status`, `outputs`, `error`, `call`; the in-memory original). A target failure is a result, not an exception, and does not count as a Run failure (the caller decides).
  `usage` is added to the Run's `totals`. The next call to the same target receives the previous call's `backend_session_id` as `ctx.previous_session_id`.
- Concurrency: the same target runs serially, different targets concurrently (within the runtime's `max_concurrency`). While calling, the caller gives up its slot and takes it again when done
  (no deadlock even with `max_concurrency=1`).
- Waiting: if the target waits for an interaction and the caller has nothing else to do, the Run is `waiting` (the caller's NodeRun stays `running`).
- Limits: counted toward the total node run limit (`flow.max_node_runs`). If the depth (`len(path) - 1`) exceeds the smaller of `max_depth` and `delegation_settings.max_depth`
  (`GraphRuntime(delegation_settings=)`/`start(delegation_settings=)`) or the target is already on the path, it does not run and returns
  a `failed` result (`error.code` = `delegation.depth_exceeded` or `delegation.cycle`) + `log.warning`.
- Cancellation and interruption: follows the Run's cancel token. The target NodeRun becomes `cancelled` (`error.code = interrupted` when interrupted). Restart recovery also turns unfinished call NodeRuns
  into `cancelled` with events `node_path = invoked_by + [node]` and payload `call`. Resuming (`resume_options`, `resume_seed`) does not look at call NodeRuns.

```python
>>> import asyncio
>>> from agent_console_runtime.testing import BUILDERS as b, make_harness
>>> h = make_harness()  # the test edge `t.invoke` (invocation `t.invoker`) + the delegator `t.lead`
>>> g = b.graph(
...     [b.node("lead", type="t.lead", calls=["dev", "dev"]), b.node("dev")],
...     [b.edge("lead", "dev", kind="t.invoke", sp="alt", tp="in2")],
...     entries=["lead"],
... )
>>> run = asyncio.run(h.make().run(g))
>>> sorted((nr.node_id, nr.call, nr.invoked_by) for nr in h.recorder.runs.list_node_runs(run.id))
[('dev', 0, ['lead']), ('dev', 1, ['lead']), ('lead', 0, None)]

```

## Child Runs: `ctx.run_child`

A node (for example a nested team node) runs another graph as a **child Run** and waits for the result. The engine does not know node or team names.

- Child Run: `parent_run_id` = the parent, `parent_node_id` = the calling node, `root_run_id` = the top Run (grandchildren get the root id too; the root itself is null),
  `origin` = the parent's value, `conversation_id` = null (not a conversation turn). It is registered in the same runtime, so `get`, `cancel`, `respond`, `pending`, and `shutdown`
  handle it as is, and it uses the same store, event publishing, and concurrency limit.
- Preparation: if there is `GraphRuntime(child_preparer=)`, it receives `ChildRunRequest{graph, input, parent, node_id, node_path, ancestors, services}`
  and returns `ChildRunPreparation{services, interaction_grants, interaction_settings, flow_settings, delegation_settings, checked}`
  (None = the parent Run's values; no allowed interactions). Without it, or with `checked=False`, the engine validates. If blocked (validation errors, no entry, the preparer refuses), no child Run
  is created and the result is `failed` (`error.code = validation_failed`, `details.issues`).
- Limits: if the nesting depth (root = 0) exceeds `delegation_settings.max_nesting` (the contract default 3 if absent), `team.nesting_exceeded`; if the child graph id
  is already on the Run path, `team.recursive`. Both return a `failed` result without a child Run + `log.warning` (`node_path` = the calling node).
- Events: the parent Run gets `run.child_started{child_run_id, node_id, graph_id}` and `run.child_finished{child_run_id, node_id, status = child status}`.
  Child replies stay only as the child Run's `run.reply` and do not flow into the parent chat (the parent's replies come from the node's reply edges).
- Result: `ChildRunResult{run_id, status, replies (reply payloads), totals, error}`. A child failure is a result, not an exception.
  `totals` is not added to the parent's totals automatically; it is included when the node returns it as `NodeResult.usage`.
- Waiting and slots: while waiting, the calling node gives up its slot (no deadlock even with `max_concurrency=1` and two levels of nesting). If the child only waits for interactions,
  the parent Run is `waiting` too (the calling node stays `running`). Interactions inside the child have `Interaction.root_run_id` = the root and `conversation_id` = the root conversation.
- Cancellation and interruption: cancelling or interrupting (shutting down) the parent propagates to the child the same way, and the parent ends after the child ends (after `run.child_finished`). Children the node
  left without waiting also stop when the parent ends. Restart recovery (`recover_unfinished_runs`) cleans up child Runs as `interrupted` like any Run.
- Run folders: `ctx.run.id` of nodes in a child Run is the child Run id: `<Run file root>/<child Run>/<node>` (the ac-nodes-core `run_folder` rule as is).

```python
>>> import asyncio
>>> from agent_console_runtime.testing import BUILDERS as b, make_harness
>>> h = make_harness()  # the test node `t.nest`: runs config `graph` with ctx.run_child
>>> child = b.graph([b.node("A", outputs={"out": "자식 답"})], [b.reply("A")], "child", entries=["A"])
>>> parent = b.graph(
...     [b.node("N", type="t.nest", graph=child.model_dump(mode="json"))],
...     [b.reply("N")],
...     "parent",
...     entries=["N"],
... )
>>> run = asyncio.run(h.make().run(parent))
>>> [(r.graph_id, r.parent_node_id, r.root_run_id == run.id) for r in h.recorder.runs.list() if r.parent_run_id]
[('child', 'N', True)]
>>> [r.text for r in h.probe.children[0].replies]
['자식 답']

```

## Interactions while running (live wait)

```python
outcome = await ctx.request_input(
    InteractionRequest(kind="<registered kind id>", title="…", payload={...})
)
if outcome.status == "answered":
    ...  # expired and cancelled are results too, not exceptions (response = expire_response)

await runtime.respond(run_id, interaction_id, {"answer": "…"})  # the app (server, CLI)
runtime.pending(run_id=None)  # waiting list (stored copies with secrets masked)
```

- `NodeContext` satisfies `InteractivePort`. Backends open requests only when `isinstance(sink, InteractivePort)`.
- The engine does not know kind names. Kinds are looked up in `registries.interaction_kinds` (`UnknownExtensionError` if absent),
  and responses are validated against the response schema (request value > descriptor default) (`ResponseValidationError.issues`, the ac-graph validator).
  Grants (`start(interaction_grants=)`, `ctx.interaction_grant`) are used only as time limit defaults and do not enforce kinds.
- State: the first request → NodeRun `waiting` (`node.waiting`, `wait.reason` = the kind, `wait.data.interaction_ids`), and the concurrency slot is given back.
  When all open requests are closed, the slot is taken again → `node.resumed{waited_ms}` → the result goes to the requester. One node can open several requests.
  When there are no running or queued nodes and some nodes are waiting, the Run is `waiting` (`run.waiting`), and `run.resumed` when it moves again.
- Events: `interaction.requested{interaction}` · `interaction.answered{interaction_id, kind, answered_by, response_preview}` ·
  `interaction.closed{interaction_id, kind, status, reason}`. `interaction.*` is a prefix reserved for the engine.
- Response races: the one that started closing first in memory + a conditional update in the store. The loser gets `InteractionClosedError(interaction)`.
  Requests of finished Runs or other processes are checked in the store and raise `InteractionClosedError`/`UnknownInteractionError`.
- Time limits: request `timeout_seconds` and `on_timeout` > grant > `interaction_settings` (`start(...)` > constructor) > unlimited with `expire`.
  `expire` → `expired(timeout)`; `cancel_run` → `cancelled(timeout)` and then the Run is cancelled (reason `interaction_timeout`).
  Timers use the injected `clock` and `sleep` (`testing.ManualClock`).
- Closing: Run cancellation → `cancelled(cancelled)` (closed before the grace period so the node can receive the result and clean up);
  the node ends while waiting → `cancelled(node_finished)`; restart → `recover_unfinished_runs` gives `expired(interrupted)`.
- Secrets: stored copies, events, and the return values of `respond`/`pending` are masked copies; the requester (`InteractionOutcome.response`) gets the original.

## Resuming interrupted runs

- `GraphRuntime.start(graph, input, seed={노드: 입력}, resumed_from=원래_run_id, origin="resume")`:
  starts the seed nodes with those inputs, without entry injection. Upstream nodes of the seed nodes (nodes reached by following flow edges backward)
  are not run and are left as `node.skipped` (payload `reason = "resumed"`, `SkipReasons.RESUMED`), and downstream continues
  as usual. If a seed node is not a scheduled node, `GraphValidationError` (`seed_not_scheduled`). The engine does not know node
  names; whether a node may run again (descriptor `rerunnable`) is checked by the caller.
- Pure functions: `resume_options(run, node_runs, events, graph=, node_types=)` (interrupted nodes + the state right before the interruption +
  `rerunnable`), `resume_issues(options, node_ids)`, `resume_seed(node_runs, node_ids)`, `interrupted_status`.
- `ResumeService(runs, events, graph_of=, node_types=, starter=)`: `options(run_id)`, `await resume(run_id,
  node_ids)`. Not an interrupted Run, a child Run (has `root_run_id`; resuming the root makes the calling node create a new child),
  already resumed (`runs.list(resumed_from=)`), or the team at that time is missing: all raise
  `RunNotResumableError` (409 `run_not_resumable`); nodes that cannot be chosen raise `GraphValidationError` (issues per node).
  How to start the new Run (whether it is a conversation turn and so on) is decided by the injected `starter`.
- Limitation: the saved input is `NodeRun.inputs` (the first value per port), so per-edge values (`ctx.incoming`) are empty.

## Handling secret values

- Nodes resolve secrets with `ctx.secrets.resolve(...)`. The resolver remembers resolved values.
- **Every stored record** (Runs, NodeRun inputs, outputs, and errors, interactions, RunEvents) is stored and published as a copy with resolved values masked as `[REDACTED]`
  at the single storage path (`RunJournal.save`/`event`).
  The final Run that `wait()` returns is a masked copy too.
- `SecretResolver(providers, *, min_redact_chars=4, extra_redact=None)`: with `extra_redact(text) -> text`, after resolved
  secrets are masked, it is applied once more to every string (masking unresolved plain-text tokens). The engine does not know suspicion rules;
  the server plugs in `redact_suspected` from `ac-secret-rules`, and the workspace setting `secrets.redact_suspected_in_logs` turns it off.
- Secret values shorter than `min_redact_chars` (default 4) would damage normal text, so they are not masked. Instead, a warning log with the secret's **name**
  is written once when it is resolved (the value is never logged).
- `Run.input` is stored as a masked copy too. If the input contains a string equal to a secret, the stored copy (and the Run from `wait()`) differs from the original.
- Values passed to downstream nodes (edge values) live only in engine memory, so they are not masked (nodes need the original values).
- Limitation: masking applies only to **values resolved by this resolver**. Secrets before resolution (or obtained another way), values recorded before resolution,
  and transformed values (encoded, partly cut) cannot be masked. Backends must also mask the provider's raw messages (`raw`) themselves.
- **Inputs before resolution are not masked**: if the user writes a secret value directly into a Run input (console input, `input` of `POST /runs`),
  and the resolver has never resolved that value through `secret://`, it is an unknown value and is stored and shown as is.
  (If the resolver is shared through `GraphRuntime(secrets=…)` and the same value has already been resolved, it is masked.)
- **`secret://` is resolved only when the whole string is a reference**: `"secret://API_KEY"` becomes the value, but
  a string mixed with other text such as `"Bearer secret://API_KEY"` is not resolved and stays as is.

## Behavior on store failures

- When recording fails, later records of that Run are discarded (events that were not saved are not published either) and the run ends.
- `handle.wait()`/`runtime.run()` raise `RecorderError` (the cause in `__cause__`). If it fails during `start()`, `start()` raises.
- The Run in the store stays in its last saved state (usually `running`). At the next server start, `recover_unfinished_runs` cleans it up as `interrupted`.
- Even if nobody calls `wait()`, the engine retrieves task exceptions and logs them (no "Task exception was never retrieved").

## Process group utilities

Child processes started with `process_group_kwargs()` are terminated as a group with `terminate_process_group(popen)` / `await aterminate_process_group(proc)`
(POSIX: SIGTERM → grace → SIGKILL; Windows: CTRL_BREAK → grace → `taskkill /T /F`). Ported from agent_bench `terminate`.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-runtime`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-runtime/tests
```

Tests register only the test-only `t.*` node and edge types from `agent_console_runtime.testing` to check that the engine knows no specific type.
The entry, reply, and delegation types (`t.user`, `t.res`, `t.lead`, `t.entry`, `t.exit`, `t.tie`, `t.call`, delegation strategy `t.inline`)
can be added to any registry bundle (including a stack assembled from real plugins) with `register_scheduling_types(registries)`;
the call NodeRun types (edge `t.invoke`, delegation strategy `t.invoker`, which runs targets with `ctx.invoke_node`; delegator config `calls`, `parallel`, `max_depth`)
with `register_invocation_types(registries)`; and the child Run node `t.nest` (config `graph`, `version`, `input_key`)
with `register_child_types(registries)` (`make_registries` adds them all).
Build test graphs with explicit entries using `graph(..., entries=[...])` and `with_entries(graph, entry(dst, key=...))`.
`agent_console_runtime.testing` (in-memory recorder, `StepClock`, `SequentialIds`) can be used in plugin tests too.
Sinks for backend adapter tests live in one place, `agent_console_runtime.testing_sink`: `ValidatingSink` (contract validation and subpath checks),
`ListeningSink` (+ recording `SubagentResultListener`), `InteractiveSink` (+ `InteractivePort`, a response function). The `testing` modules of fake and claude-sdk re-export them.

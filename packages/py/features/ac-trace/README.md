# agent-console-trace

Builds the **delegation flow** of one run ("who handed work to whom, and when it came back") from its RunEvents,
and counts **"who handed to whom, how many times"** across runs. A pure library that depends only on `agent_console_contracts`.

- `build_trace(events, *, edge_kinds=, call_edges=, node_runs=, children=) -> Trace`
  - Node run = a `node` span (its own NodeRun and session, one per attempt and loop iteration, `iteration`).
  - A call NodeRun invoked by a delegator (standalone delegation) = a **child** `node` span of the delegator span (separate session, `call`, one per
    call). The delegator → call link is included too (edge id and kind from `call_edges`; since it is parent-child, the screen does not draw it
    as an arrow). The delegated task preview comes from `node_runs` (the call NodeRun input).
  - Subagent = a **child** `delegated` span of the delegator span (same session id, delegated task, result preview, usage).
  - Handoff = an arrow `TraceLink` between sibling `node` spans (`edge.traversed`). The arrival span gets the handoff order `order`.
    A cycle edge (loop) is a link to the next iteration's span (`kind` = edge type).
  - Interaction = a child `interaction` span of the requesting span ("waiting for the user", `interaction_id`).
  - Child run (nested team) = `children` (child run id → that run's trace) is attached under the node span that emitted `run.child_started`.
    Spans and links of the child run carry `run_id`, and span ids are `run:<child run>/<original id>`.
- `handoff_matrix(traces) -> HandoffMatrix`: counts per (sender, receiver, kind), most frequent first.
  It moves the handoff edges query of agent_bench `log_store` (sender, receiver, via, count, in descending count) onto the delegation flow.

## Linking principle: explicit ids only

Events close in time are not linked as cause and effect (the agent_bench `link_events` principle). Without a link key, an item is left without a parent.

| Relation | Link key |
| --- | --- |
| Node span | `node_path == [node]` of `node.*` + `attempt` + payload `iteration` |
| Call span | `node_path` of `node.*` (delegator path + target) + payload `call`. Parent = the span of the path prefix (NodeRun `invoked_by`) |
| Events inside a call span | The **open** call span with the same path (the engine runs the same target serially, so there is one per path). Not attached to finished calls |
| Events inside a loop iteration span | The most recent iteration span of that node (a node runs only one iteration at a time) |
| Child run group | `run.child_started.child_run_id` → the span that the event's `node_path` points to. Attached without a parent if there is none |
| Parent of a delegated span | `agent.subagent_started.tool_use_id` = the parent's `agent.tool_call.tool_use_id`, otherwise the `node_path` prefix |
| End of a delegated span | `agent.subagent_stopped.subagent_id` (otherwise `tool_use_id`) |
| Interaction span | `interaction_id` of `interaction.requested/answered/closed`; the parent is the interaction's `node_path` and `attempt` |
| Handoff arrow | The source and target node ids of `edge.traversed` |

When several delegations are open on the same path and the path alone cannot tell which one, the item is attached one level up (the delegator node) instead of to the most recent one.

## Installation

```bash
uv sync --all-packages                    # inside the workspace
uv pip install ./packages/py/features/ac-trace     # standalone, from another project (needs ac-contracts)
```

## Minimal usage

```python
>>> from agent_console_contracts import RunEvent
>>> from agent_console_trace import build_trace, handoff_matrix

```

In real use, pass the events from the store (`event_repo.list(run_id)`). Here one pl → qa handoff is built by hand.

```python
>>> def events(run_id):
...     rows = [
...         ("node.started", ["pl"], {"status": "running"}),
...         ("node.completed", ["pl"], {"status": "succeeded"}),
...         (
...             "edge.traversed",
...             [],
...             {
...                 "edge_id": "h1",
...                 "source": {"node": "pl", "port": "out"},
...                 "target": {"node": "qa", "port": "in"},
...             },
...         ),
...         ("node.started", ["qa"], {"status": "running"}),
...         ("node.completed", ["qa"], {"status": "succeeded"}),
...     ]
...     return [
...         RunEvent(
...             event_id=f"{run_id}-{seq}",
...             run_id=run_id,
...             seq=seq,
...             ts=float(seq),
...             node_path=path,
...             attempt=1 if path else None,
...             actor=path[0] if path else None,
...             type=type,
...             payload=payload,
...         )
...         for seq, (type, path, payload) in enumerate(rows, start=1)
...     ]
>>> edge_kinds = {"h1": "handoff"}  # optional: show the edge type on arrows (graph edge.id → kind)
>>> trace = build_trace(events("r1"), edge_kinds=edge_kinds)  # Trace{spans, links}
>>> [s.id for s in trace.spans]
['node:pl#1', 'node:qa#1']
>>> [(link.source, link.target, link.kind) for link in trace.links]
[('node:pl#1', 'node:qa#1', 'handoff')]

>>> matrix = handoff_matrix(build_trace(events(r), edge_kinds=edge_kinds) for r in ["r1", "r2"])
>>> for cell in matrix.cells:  # "who handed to whom, how many times" across runs
...     print(cell.source, "→", cell.target, cell.kind, cell.count)
pl → qa handoff 2

```

Span kind names are the constants `SPAN_KIND_NODE`, `SPAN_KIND_DELEGATED`, and `SPAN_KIND_INTERACTION`; span ids are built with
`node_span_id`, `call_span_id`, `delegated_span_id`, `interaction_span_id`, and `child_span_id`.
Calls rejected for exceeding depth or for cycles have no NodeRun (only `log.warning`), so they have no span.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-trace`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-trace
```

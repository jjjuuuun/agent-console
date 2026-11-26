# agent-console-link-runs-trace

Runs and trace link module. It builds the delegation flow (`ac-trace`) from run history (`runs.reader`, `runs.events`).

- `GET /runs/{id}/trace`: spans (nodes, calls, delegations, waiting for the user) and handoff arrows. Edge types and call edges (`call_edges`, when a delegator and target pair has exactly one edge) are added from the team as it was at run time (the version history of the optional port `definitions.lookup`, or the current definition when it is missing). Child runs (nested teams) are read recursively starting from the direct children and attached as a group under the node span that called them (`run_id`). The delegated task of a call span comes from the NodeRun input.
- `GET /runs/handoffs`: "who handed off to whom, how many times" across several runs (the filters are the same as the run list). Each run counts only its own flow (child runs appear separately in the list, so nothing is counted twice).
- Both routes take an optional `?project=<id>` and then read only from that project's records (the optional method `for_project` of `runs.reader` and `runs.events`; without it, runs are filtered by their `project_id`, the same policy as the run list `GET /runs?project=`). An unknown project returns 404 `project.not_found`. Without the query, handoff totals come from the host records and the flow comes from wherever run history finds the run. The team at run time of a run with a `project_id` is read only from that space's store through the optional port `definitions.spaces` (when the space cannot be opened, there are no edge types; it does not fall back to the library).
- When this link is off, the routes return 404 and the web app hides the flow tab and the handoff view of the run detail (web role `runs:trace`).

## Install

```bash
pip install agent-console-link-runs-trace
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-runs-trace
```

## Minimal usage

Build a flow from run history with `TraceViews`, without HTTP.

```python
>>> from agent_console_contracts import Run
>>> from agent_console_store import InMemoryStorage
>>> from agent_console_link_runs_trace import TraceViews
>>> storage = InMemoryStorage()
>>> storage.runs.save(Run(id="r1", graph_id="g", graph_version="v", status="completed",
...                       input={}, origin="api", created_at=1.0))
>>> views = TraceViews(storage.runs, storage.events)
>>> views.trace(views.require_run("r1")).run_id
'r1'
>>> views.handoffs(graph_id=None, conversation_id=None, agent_id=None, status=None, limit=10).runs
1
>>> views.in_project("p1").handoffs(
...     graph_id=None, conversation_id=None, agent_id=None, status=None, limit=10).runs
0

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `runs.reader` | `get(run_id)`, `list(graph_id=, status=, conversation_id=, agent=, parent_run_id=, project_id=, limit=)`, `list_node_runs(run_id)`, optional `for_project(id)` |
| Required | `runs.events` | `list(run_id, since_seq=)`, optional `for_project(id)` |
| Optional | `definitions.lookup` | `get_version(kind, id, hash).content`, `get(kind, id).document` |
| Optional | `definitions.spaces` | `open(space)` → a definition store (`ac-store.DefinitionSpaces`) |

## Standalone run

```bash
python -m agent_console_link_runs_trace [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_runs_module` (reads run history from the database in the state folder).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

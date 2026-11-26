# agent-console-link-runs-usage

Runs and usage link module. It connects run history (`runs.reader`, `runs.events`) to the usage module (`mod-usage`).

- `usage.event_query`: run event queries (the usage source context, for example `usage.rate_limit` of the `run-events` source). `MergedEventQuery` merges the app records (`runs.events`) with **the record databases of registered projects (excluding unregistered ones)** and returns them in descending ts order. Account windows (5-hour, weekly) are per account, so they are not split by project, and the window events of runs in a project exist only in that folder's record database. When either of the optional ports `projects.lookup` and `records.spaces` is missing, only the app records are read. Spaces that cannot be read (missing or broken folders) are skipped.
- `usage.token_rollups`: token totals for platform runs (`IncrementalTokenRollups`). For each run it reads only after the last event seq it applied (the watermark), and finished runs are not read again until a new event arrives (`runs.event` subscription). It is an in-memory cache, so a restart recalculates. After operations that shrink the records (retention cleanup), call `invalidate()`. Only root runs are counted (`ac-usage.counts_toward_usage`): the usage of child runs of a nested team is already included in the root through the `usage` of the calling parent node (no double counting).
- Token total sources: the app records, plus one per registered project record database when the optional `projects.lookup` and `records.spaces` are present (`project_rollup_sources`; unregistered projects are excluded, and spaces that cannot be read are skipped with a warning). The cache and watermarks are kept separately per `(source key, run_id)`. `rollups(project_id=None)` is the whole account (the latest `limit` runs of each source merged by creation time into `limit` runs); with `project_id`, it is that project's records plus the old runs in the app records with the same `Run.project_id` (`GET /usage?project=`). Old runs in the app records are read directly with the store condition (`list(project_id=, root_only=True, limit=)`) as the latest `limit` runs of that project, so they are not crowded out by many other runs. When `runs.reader` has the optional method `for_project(None)` (read only the app records), that is used. Without the ports, only the app records are read.
- Query count: runs to read again (first time, not finished, new events) are read in batches per source. When `runs.reader.list_node_runs_many` and `runs.events.list_many` exist, even the first total takes one run list query, one event query, and one NodeRun query per source (per `RUN_BATCH_SIZE` runs of the store); otherwise they are read per run (the result is the same). Each source (project record database) needs its own queries because the database files are separate.
- When this link is off, the usage screen shows only external sources (statusline and so on), and the token totals are an empty list (web role `usage:tokens`).

## Install

```bash
pip install agent-console-link-runs-usage
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-runs-usage
```

## Minimal usage

```python
>>> from datetime import UTC
>>> from agent_console_contracts import NodeRun, Run, Usage
>>> from agent_console_store import InMemoryStorage
>>> from agent_console_link_runs_usage import IncrementalTokenRollups
>>> storage = InMemoryStorage()
>>> storage.runs.save(Run(id="r1", graph_id="g", graph_version="v", status="completed",
...                       input={}, origin="api", created_at=1.0))
>>> storage.runs.save_node_run(NodeRun(run_id="r1", node_id="a", status="succeeded",
...                                    started_at=1.0, usage=Usage(input_tokens=7)))
>>> rollups = IncrementalTokenRollups(storage.runs, storage.events)
>>> [(row.graph_id, row.usage.input_tokens) for row in rollups.rollups(limit=10, tz=UTC)]
[('g', 7)]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `runs.reader` | `list(root_only=, limit=, project_id=)`, `list_node_runs(run_id)`, optional `list_node_runs_many(run_ids)` and `for_project(None)` (app records only) |
| Required | `runs.events` | `list(run_id, since_seq=, type_prefix=)`, `latest_by_type(...)`, optional `list_many(since, type_prefixes=)` |
| Optional | `projects.lookup` | `list_projects()` (`id`, `archived`) |
| Optional | `records.spaces` | Space name (`records_space_prefix` + project id) → record database handle. When the optional `batch()` (`BatchRecordsSpaces`) exists, one total or query runs inside that block (even with more projects than the pool limit, connections are not evicted and reopened during the pass) |
| Subscribes | `runs.event` | Marks the run that has a new event |
| Provides | `usage.event_query` / `usage.token_rollups` | `MergedEventQuery` (app + project records) / `IncrementalTokenRollups` (app + project records, a cursor per source) |

Setting `modules.options.link-runs-usage.records_space_prefix` (default `project:`; when not set, it inherits `link-projects-records.space_prefix`).
The number of project record databases kept open at the same time is not a setting of this link but of the records link, `modules.options.link-projects-records.max_open_spaces` (default 8).
When there are more registered projects than that, one total opens each project once, and the next total reopens only the projects beyond the limit.

## Standalone run

```bash
python -m agent_console_link_runs_usage [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_runs_module` (reads run history from the database in the state folder). To start the usage routes too: `--with mod-usage`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

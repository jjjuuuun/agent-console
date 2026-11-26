# agent-console-link-logs-runs

Logs and runs link module. It connects run history (`runs.reader`, `runs.events`) to the logs (`logs.ingest` and `logs.query` of `mod-logs`).

- Runtime source `platform-runs` (port `logs.sources`, on by default): indexes this console's run events (RunEvent) as the same normalized events as Claude Code session logs. For each run it reads only after the last event seq it read (the watermark). Run history is only read.
  - Classifier `platform-run-event` (set directly by the source, without a registry): the type → category and field map is **data**. Default = package data `run_event_map.yaml`; override = the setting `logs.sources[id=platform-runs].config.event_map` (whole entries per key). Types not in the map get the category `other`.
  - Sessions: the session id announced by an event matched by a `session_from` rule in the map (by default `agent.session_started`) is attached to the events of that node and its child nodes (subagents); otherwise the NodeRun `backend_session_id` is used. It becomes the event's `session` and `correlation.session`.
  - Project spaces (folder record databases): when the optional port `projects.lookup` is present, the link reads the shared (app record) runs and also, for every registered project (including unregistered ones), the runs of that space (`runs.reader.list(project_id=)`; finding and opening spaces is done by `mod-runs` through `records.spaces`). The index query attaches the session `project_id` from the event `cwd` (the project folder a project run uses), so `?project=<id>` filters it. When one space cannot be read, only that space is skipped. When the projects module is off, only shared runs are read. When you use only the parts: `platform_runs(runs, events, project_ids=lambda: [...])`.
  - hook and MCP: `hook.*` and `mcp.*` events emitted by collectors appear in the categories `hook` and `mcp`. MCP calls are paired by `tool_use_id` (start and completion). An event that carries only a duration, such as `hook.finished`, produces a start event (evidence `inferred`) and an end event through the map's `duration_ms`, so the timeline shows its duration.
  - Tokens: the default map does not use `agent.usage` as a token sample (when the same session is also read through the Claude Code session log source, it would be counted twice). To use it, add a `usage` pointer to the map (see "Run-level tokens" below).
  - Architecture map inputs: context preparation `agent.context_prepared` (category `context`; only resource ids, kinds, byte counts, and hashes), model call duration (start and end events when `agent.usage` has `duration_ms`), MCP server evidence `correlation.mcp_server`, and delegation call id evidence `correlation.tool_use_id` (`node.*` of the calling NodeRun). `from`, `to`, and `via` of `node.started` are filled only for delegation calls (payload `call`; conditional values).
  - Memory: memory tool calls `memory.*` (`link-memory-runs`) get the category `memory`, the document marker `{kind: memory, path: <scope kind>/<scope id>/<key>, action: read·written·removed·searched}` (calls with an unknown scope get no marker), and the evidence `tool_use_id` and `memory_scope`. Writing `"memory.*": {}` in the `event_map` setting turns this off, and the category becomes `other`.
  - Wiki: wiki tool calls `wiki.*` (`link-wiki-runs`) get the category `wiki`, the document marker `{kind: wiki, path: <wiki id>/<page path>, action: read·read_links·written·removed·searched·listed}` (a move produces two markers, the old path `moved_from` and the new path `moved_to`; searches and lists without a page and denials with an unknown wiki get no marker), status `denied` or `rule_rejected` → block, and the evidence `tool_use_id` and `wiki`. The payload does not contain the page body or the search text. Writing `"wiki.*": {}` in the `event_map` setting turns this off, and the category becomes `other` (the events remain).
- Subscribes to `runs.event` and schedules collection for that run (debounced; administrator option `debounce_seconds`, default 1 second).
- `GET /runs/{id}/logs?<LogFilter>` → `LogEventPage` (`total` is always filled): the **external session events** of that run's session ids. Platform run events (another tab of the run detail) are left out by default; when you pass `source` explicitly, that is used.
- Scope kinds (port `logs.scope_kinds`): the log query filter `scope=run:<run id>` = the platform run events of that run (`run_id`) ∪ the events of that run's sessions (NodeRun `backend_session_id` + the `session` of indexed platform events, the same calculation as `/runs/{id}/logs`). `scope=run-tree:<run id>` = the same calculation for that run and all child runs below it (nested teams, `parent_run_id`). Delegates (calling NodeRuns) are inside the same run, so they are in `run`. A missing run or an empty value returns 422 (`details.path = scope`). The event list, totals, session list, and timeline all follow the same scope. Parts: `RunScopeKind`, `run_scope_kinds(runs, logs, kinds=)` (kind ids are arguments), `run_sessions`, and `run_tree_ids`.
- When this link is off, the logs screen has no platform runs and the *Session logs* tab of the run detail is hidden (web role `logs:runs`). `scope=run:` and `run-tree:` become unknown scope kinds (422). The link is also off when `mod-logs` or `mod-runs` is off (required ports).

## Install

```bash
pip install agent-console-link-logs-runs
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-logs-runs
```

## Minimal usage

Without a server, collect in-memory run history through the `platform-runs` source and query it (in a real setup, the store of `mod-runs` and the SQLite index of `mod-logs`).

```python
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex
>>> from agent_console_link_logs_runs import platform_runs
>>> from agent_console_link_logs_runs.testing import MemoryRunRecords, run_event, run_record

>>> records = MemoryRunRecords()                 # shaped like runs.reader and runs.events
>>> records.runs.save(run_record("r1"))
>>> records.events.append(
...     run_event(1, "agent.session_started", {"session_id": "s1", "backend": "fake-agent"}),
...     run_event(2, "mcp.call_started", {"server": "docs", "tool": "find", "tool_use_id": "t1"}),
...     run_event(3, "mcp.call_completed", {"server": "docs", "tool": "find", "tool_use_id": "t1"}),
... )
>>> item = platform_runs(records.runs, records.events)   # source + classifier (same default map)
>>> index = MemoryLogIndex()
>>> ingestor = LogIngestor(index, LogRegistries())
>>> ingestor.add_runtime_source(item.source, classifier=item.classifier)
>>> ingestor.scan().new_events
3
>>> ingestor.scan().new_events                    # seq watermark: 0 when there are no new events
0
>>> timeline = index.timeline("s1", query_context(None))
>>> [(e.category, e.stage, e.duration_ms) for e in timeline.events]
[('system', 'info', None), ('mcp', 'start', 1000.0), ('mcp', 'complete', 1000.0)]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Map (`run_event_map.yaml`)

```yaml
types:
  "*": {category: other, title: "{type}"}          # key: a type or a glob (exact name, then longer globs first)
  mcp.call_completed:
    category: mcp
    stage: complete
    tool: "mcp__{/payload/server}__{/payload/tool}" # template: {/JSON pointer}, {type}, {node}, {parent_node}, {thread}, {actor}, {run_id}
    call_id: "{/payload/tool_use_id}"
    status: {pointer: /payload/is_error, map: {"true": error}, default: ok}
  hook.finished: {category: hook, duration_ms: /payload/duration_ms}   # a finished span -> start and end events
  agent.session_started: {category: system, session_from: /payload/session_id}
  agent.text_delta: {skip: true}
```

Value rules (`category`, `status`, `from`, `to`, and so on) are template strings or conditional values `{pointer, map, default}`; the matched `map` value and `default` are templates too. For example, fill the receiving side only for a calling NodeRun:

```yaml
  node.started:
    to: {pointer: /payload/call, map: {"null": ""}, default: "{node}"}
```

### List values (`each`)

`tags`, `correlation` values, and `documents` can produce one item per element of a list in the event. The form is
`{each: <list pointer>, ...item template}`. Inside the item template, `{./key}` and `{.}` (the element itself) and
`pointer: ./key` in conditional values refer to the element (`/…` still refers to the event).

- `tags`: `{each, value}` items can be mixed into a list of literal tags (or a single `{each, value}`).
- `correlation`: evidence name → a template string (one value, as before) or `{each, value}` (several values).
- `documents` (new key): one document template `{path, kind?, action?}` (values are templates or conditional values) or a list of them. When a template
  has `each`, it produces one document per element. They appear in the list body in the shape of the contract `LogDocumentRef`.
- Items whose result is empty (for documents, items with an empty `path`) are dropped, and duplicate items are kept once. So you can filter elements with
  `default: ""` in a conditional value. When the list is empty, is not a list, or its elements are not objects, there are no items.
- The existing value forms (literal tags, template string evidence) mean the same as before.

The default map turns the resources attached during context preparation (`agent.context_prepared`) into documents. Architecture map cell conditions
see only the list body (the payload is in `detail`), so this conversion is what lets the default architecture map's Rules cell count platform runs.
The resource kind id → document kind mapping is data (kind `rule` → `rules`; rule resources are the first documents).

```yaml
  agent.context_prepared:
    category: context
    documents:
      - each: /payload/resources        # rule resources only (other kinds get an empty path and are dropped)
        kind: rules
        path: {pointer: ./kind, map: {rule: "{./id}"}, default: ""}
        action: read
      - each: /payload/resources        # the rest (document kind = resource kind id)
        kind: "{./kind}"
        path: {pointer: ./kind, map: {rule: ""}, default: "{./id}"}
        action: read
  x.done:
    tags: [done, {each: /payload/labels, value: "label:{.}"}]
    correlation: {resource: {each: /payload/resources, value: "{./id}"}}
```

The pure functions `resolve_strings` and `resolve_documents` (module `event_map`) apply the same rules without a server.

All rule keys and the JSON Schema are in `RULE_SCHEMA` (the settings form is the `event_map` of the source descriptor `config_schema`). The link still works when the file is emptied or deleted (every type becomes `other`).

## Run-level tokens

Adding platform run tokens to the log totals is **off by default**. When the backend is Claude Code, the same session is also read through the `claude-code` source (session logs), so tokens would be counted twice. If you use only backends that do not write Claude Code session logs, or you need run-level totals, replace the whole `agent.usage` rule in the user settings and add a `usage` pointer.

```yaml
logs:
  sources:
    - id: platform-runs
      config:
        event_map:
          agent.usage:
            category: usage
            title: 사용량
            model: "{/payload/model}"
            duration_ms: /payload/duration_ms
            usage:
              input_tokens: /payload/usage/input_tokens
              output_tokens: /payload/usage/output_tokens
              # Write long pointers on the next line as a folded scalar (>-). The value is the same one-line string.
              cache_read_input_tokens: >-
                /payload/usage/cache_read_tokens
              cache_creation_input_tokens: >-
                /payload/usage/cache_creation_tokens
```

`agent.usage` carries running totals during a run, so without a `message_id` the sample key is always `<run_id>:<node path>:<attempt>` and only the last value remains (no double counting). When this is on, the token metrics of the architecture map show values instead of "Not collected".

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `logs.ingest` | `request_scan(source_ids, ref_hint=)` |
| Required | `logs.query` | `events(flt, with_total=)`, `aggregate(request)` |
| Required | `runs.reader` | `get(run_id)`, `list(parent_run_id=, project_id=, limit=)`, `list_node_runs(run_id)` (optional `for_project(id)`, `descendants(root)`) |
| Required | `runs.events` | `list(run_id, since_seq=, limit=)`, `last_seq(run_id)` |
| Optional | `projects.lookup` | `list_projects()` (the `id` of each item); when present, runs in registered project spaces are collected too |
| Subscribes | `runs.event` | schedules collection for that run (debounced) |
| Provides | `logs.sources` | `PlatformRunsLogSource(source, classifier)` |
| Provides | `logs.scope_kinds` | `RunScopeKind` (`id`, `resolve(value) -> LogScope`): `run` and `run-tree` |

Administrator option (`modules.options.link-logs-runs`): `debounce_seconds` (1.0; 0 = immediately). Source settings (user data `logs.sources[id=platform-runs].config`): `max_runs` (200; the number of recent runs to look at during collection, separately for shared records and for each project space) and `event_map`.

The `pending_bytes` of the source status is "the number of events not read yet" for this source (because the unit is the seq within a run).

## Standalone run

```bash
python -m agent_console_link_logs_runs [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_logs_module` (an in-memory index; scheduling collection collects immediately) and `testing.runs_module` (empty in-memory run history). To start it with real runs and logs: `--with mod-logs --with mod-runs --with mod-definitions`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

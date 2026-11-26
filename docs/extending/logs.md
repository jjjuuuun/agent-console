# Logs

The log screen indexes several sources (Claude Code session logs, the run events of this console, hook records, the
jsonl of other tools) into normalized events of the same shape and shows them. The flow is: **a source reads the raw
data → a classifier turns one row into event drafts → the index stores them**. Sources only read raw data. Category
names (`tool`, `llm`, `error`, and so on) are open strings that classifiers produce, and their names and colors on
screen are defined by the user setting `logs.taxonomy` (data).

| What you want to do | Point |
| --- | --- |
| Read a new log file or format | [log-source](#log-source) + [log-classifier](#log-classifier) |
| Classify the same raw data differently | [log-classifier](#log-classifier) |
| Show the data of another server feature as logs | [runtime-log-source](#runtime-log-source) |
| Record hooks and tool calls in more detail during runs | [collector](#collector) |
| Add a new scope (`scope=<kind>:<value>`) to log queries | [log-scope-kind](#log-scope-kind) |
| Add a new filter name to log queries | [log-filter-predicate](#log-filter-predicate) |
| Change the category and title of run events (no code) | [Run event mapping table](#run-event-mapping-table) |

Sources are configured in the workspace setting `logs.sources`. The `id` of an entry is the source id, `config` is a
value that matches the source's `config_schema`, and `config.classifier` chooses the classifier (`{id?, config?}`;
when the id is empty, the `format` of the source descriptor is used).

## collector

**When to use**: when you run with the Claude Agent SDK backend and want to collect more than the default records
(hook runs, MCP tool calls). Examples are call counts per tool name, input summaries of a specific hook, and response
time distributions. This point is defined by that backend package, so it does not apply to other backends. With
another backend, the backend emits events itself.

**Minimal shape**: subclass `BaseClaudeSdkCollector` and override only the methods you need:
`on_message(message, ctx)` (for each model response and result message), `on_hook(event, data, tool_use_id, ctx)`
(for each hook), `hook_events(config)` (the hook names to receive), and `config_problems(config)` (the settings check).
The `backend` of the descriptor (`CollectorDescriptor`) is the id of the backend that uses this collector.

**Rules**

- Do not interfere with the run. Only watch; do not change or block messages. The backend swallows exceptions and
  records them as one warning event per run.
- Keep the state of one run in `ctx.state`. Do not keep per-run values on the collector object (runs happen at the
  same time).
- Emit events with a `type` under your own prefix. The backend sends them out as run events, so they show as they are
  on the run screens and on the log screen (the `platform-runs` source). Give them log categories and titles with the
  [run event mapping table](#run-event-mapping-table).
- Do not include raw tool input or output, secrets, or paths. Carry only names, counts, times, and result status.
- It is turned on with `observe.collectors.<id>` (`enabled`, `config`) in agent, team, or common settings. Collectors
  that are not set are off.

**Common mistakes**: writing the `config` shape only in the descriptor `config_schema` and not checking it in
`config_problems`. If the schema is missing or loose, wrong settings are silently ignored at run time.

**Data left after removal**: `observe.collectors.<id>` in the settings stays. Validation reports
`observe.unknown_collector` as a **warning**, and runs go ahead. When the settings do not match the collector schema,
the warning is `observe.collector_config_invalid`. Events already emitted stay in the run history.

<!-- extdocs:facts collector -->
- Registration: Register in the entry point group `agent_console.collectors` (constant `agent_console_backend_claude_sdk.collectors:COLLECTORS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_backend_claude_sdk.collectors:ClaudeSdkCollector` — Protocol for claude-sdk observation collectors.
  - `agent_console_backend_claude_sdk.collectors:BaseClaudeSdkCollector` — Common collector base: no-op defaults for every method and settings model validation.
  - `agent_console_backend_claude_sdk.collectors:CollectorContext` — Context for one run and one collector. The backend creates a new one per run.
- Built-in implementations: `mcp-calls (agent-console-backend-claude-sdk)`, `sdk-hooks (agent-console-backend-claude-sdk)`
- Examples:
  - package: [examples/extensions/agent-console-example-collector](../../examples/extensions/agent-console-example-collector/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## log-classifier

**When to use**: when you want to split the rows a source reads into different categories, titles, or evidence, or
when a new source needs a matching classifier. One source can have several classifiers, chosen in settings.

**When no code is needed**: if the rows are JSON, the built-in classifier `mapped-jsonl` fills in the fields from
settings alone (`fields`: draft field → JSON pointer, `defaults`, `value_maps`, `correlation`, `usage`,
`skip_if_missing`).

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
logs:
  sources:
    - id: mapped-jsonl
      enabled: true
      config:
        roots: ["~/tool-logs"]
        classifier:
          config:
            fields: {title: /msg, time: /ts, category: /level}
            value_maps: {category: {ERROR: error, WARN: error}}
            defaults: {category: other}
```

**Minimal shape**: `descriptor` (`LogClassifierDescriptor`: `id`, `title`, and optionally `formats` and
`config_schema`) and `classify(record, ctx) -> list[LogEventDraft]`.

**Rules**

- It is **stateless per row**. It decides by looking at one row only. Information that needs neighboring rows
  (session ids and so on) is carried in the raw row `RawRecord` by the source.
- One row can become several events (several tool calls in one response), and a row to drop is an empty list. Do not
  drop malformed rows; emit them as drafts in a diagnostic category (so they can be found in the index).
- Do not hard-code category or status names. Take the mapping from the classifier's settings data.
- **Do not count the tokens of the same response twice.** If the raw data splits one response into several rows (the
  same message id), put the message id on the token sample so it is counted once. When two sources read the same
  session (run events and session logs), only one of them emits tokens.
- When the raw format changes, do not edit the classifier; add another one with a new id (version). The old
  classifier keeps reading the old raw data.

**Common mistakes**: putting raw prompts or tool output into titles as they are. Keep titles short. The index masks
values that look like secrets, but it cannot mask strings the classifier changed (encoded, partial).

**Data left after removal**: sources that chose that classifier fail at the next collection, and the server reports
`logs.unknown_classifier` as a **warning** (with the source id and classifier id). Other sources keep collecting, and
events already indexed stay.

<!-- extdocs:facts log-classifier -->
- Registration: Register in the entry point group `agent_console.log_classifiers` (constant `agent_console_logs:LOG_CLASSIFIERS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_logs:LogClassifier` — Log classifier. Stateless, one record at a time.
  - `agent_console_logs:ClassifyContext` — Context passed to a classifier.
  - `agent_console_logs:LogEventDraft` — Event draft a classifier built from one raw record: `LogEvent` without uid, seq, observed_at.
- Built-in implementations: `claude-code (agent-console-logs-claude)`, `hook-probe (agent-console-hook-probe)`, `mapped-jsonl (agent-console-logs)`, `normalized-v1 (agent-console-logs)`
- Examples:
  - package: [examples/extensions/agent-console-example-log-source](../../examples/extensions/agent-console-example-log-source/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## log-filter-predicate

**When to use**: when you want to add a new filter name to log event queries. This is for applying another feature's
decisions to the log table. The built-in implementation is `arch`, `arch_group`, and `arch_sources` (only events in
architecture map cells), added by the logs and architecture map link.

**Minimal shape**: a link module provides a `LogFilterExtension` on the port `logs.filter_predicates`
(multi-provider): `fields` (the filter names it accepts and their display information, listed in `filters` of
`GET /api/v1/logs/schema`) and `build(values, context) -> EventPredicate` (one event → true or false).

**Rules**

- Add your own prefix to filter names so they do not collide with built-in filters or other extensions. On a
  collision, only the one collected first stays and the later one drops out.
- Raise `ValueError` for wrong values. The server turns it into 422.
- `build` is called once per query, and the predicate is called once per event. Finish expensive preparation in
  `build` and keep the predicate light.

**Common mistakes**: querying other modules inside the predicate. That sends as many queries as there are events.

**Data left after removal**: no user data is left. When the link is off, the filter name becomes an unknown filter
and the query returns 422. Links and saved queries that used the filter fail, and only those queries.

<!-- extdocs:facts log-filter-predicate -->
- Registration: A server module provides the port `logs.filter_predicates` (symbol `agent_console_mod_logs.ports:LOG_FILTER_PREDICATES`, multiple: yes).
- Interface:
  - `agent_console_logs:LogFilterExtension` — One filter extension (port `logs.filter_predicates`).
- Built-in implementations: `link-logs-architecture`
- Examples:
  - reference: [packages/py/links/ac-link-logs-architecture](../../packages/py/links/ac-link-logs-architecture/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## log-scope-kind

**When to use**: when you need a new scope that narrows a log query to "events that belong to something". The
built-in implementations are `run` (one run) and `run-tree` (a run and all its child runs) of the logs and runs link.
The query is `scope=<kind>:<value>`.

**Minimal shape**: a link module provides a `LogScopeKind` on the port `logs.scope_kinds` (multi-provider): `id` (the
kind name, without `:`) and `resolve(value) -> LogScope`. A scope is the union of session ids and run ids.

```python
>>> from agent_console_logs import LogScope
>>> scope = LogScope.of(sessions=["s-1"], run_ids=["r-1", ""])
>>> scope.contains("s-1", ""), scope.contains("", "r-1"), scope.contains("s-2", "r-2")
(True, True, False)

```

**Rules**

- Raise `ValueError` for a target that does not exist or an empty value. The server turns it into 422
  (`details.path = scope`).
- The event list, aggregates, the session list, and the timeline all use the same scope. Keep the scope computation
  in one place (`resolve`).
- Choose a kind name that does not collide with other links. On a collision, only the one collected first stays.

**Common mistakes**: selecting events directly in `resolve`. A scope returns only session and run ids; the index
selects the events.

**Data left after removal**: links made with that scope get an unknown scope kind and return 422. Events and the
index stay as they are.

<!-- extdocs:facts log-scope-kind -->
- Registration: A server module provides the port `logs.scope_kinds` (symbol `agent_console_mod_logs.ports:LOG_SCOPE_KINDS`, multiple: yes).
- Interface:
  - `agent_console_logs:LogScopeKind` — One scope kind (port `logs.scope_kinds`).
- Built-in implementations: `link-logs-runs`
- Examples:
  - reference: [packages/py/links/ac-link-logs-runs](../../packages/py/links/ac-link-logs-runs/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## log-source

**When to use**: when you want to see the logs of other tools on the log screen. Examples are the session files of
another agent CLI and the text logs of an in-house tool. If the rows are JSON, first see whether the built-in source
`mapped-jsonl` (which reads folders from settings alone) is enough.

**Minimal shape**: `descriptor` (`LogSourceDescriptor`: `id`, `title`, `format`, and optionally `config_schema`,
`default_enabled`, `reads_paths`, `setup_help`), `discover(ctx)` (the list of raw data to read), and
`read(ref, cursor, ctx, budget=, final=)` (read up to the budget after the cursor). For line-based files, subclass
`JsonlFileSource` and change only `parse_line`. The base class handles incremental reads, holding back unfinished
lines, detecting file rotation, and opening files read-only.

**Rules**

- **Raw data is read-only.** Do not write, rename, or lock it. Use the read-only open of the base class.
- Take the folders to read from settings (`roots` and so on), not from code. The app does not read outside registered
  project folders (roots outside them are reported with `logs.out_of_scope`).
- Read incrementally. Return a cursor (a byte offset and so on); the next collection continues after it. Do not read
  more than `budget` at once.
- A source that copies raw conversation text into the index sets `default_enabled = false`. It reads only after the
  user turns it on.
- The descriptor `format` is the default classifier id. The matching classifier usually lives in the same package.
- When the raw data is split into several files, as with subagent logs, `discover` finds them all and puts the
  information that links sessions on the rows.

**Common mistakes**: dropping malformed lines. Do not drop them; pass them on as rows so the classifier emits
diagnostic events (so you can find where things broke).

**Data left after removal**: the source disappears from the source list. Its entry in the setting `logs.sources` and
the events already indexed stay, but nothing new is collected. The index is cleaned up after the retention period
(`modules.options.mod-logs.retention_days`).

<!-- extdocs:facts log-source -->
- Registration: Register in the entry point group `agent_console.log_sources` (constant `agent_console_logs:LOG_SOURCES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_logs:LogSource` — Log source. Only reads the originals.
  - `agent_console_logs:LogSourceContext` — Context passed to a source (everything injected, no globals).
  - `agent_console_logs:RawRecord` — One raw record.
- Built-in implementations: `claude-code-jsonl (agent-console-logs-claude)`, `hook-probe-jsonl (agent-console-hook-probe)`, `mapped-jsonl (agent-console-logs)`, `normalized-v1 (agent-console-logs)`
- Examples:
  - package: [examples/extensions/agent-console-example-log-source](../../examples/extensions/agent-console-example-log-source/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## runtime-log-source

**When to use**: when you want to show the data of another server feature as logs. The built-in implementation is
`platform-runs` (the run events of this console) of the logs and runs link. That data can be read only through another
module's port, not from files, so it cannot be built as an entry point source.

**Minimal shape**: a link module provides a `RuntimeLogSource` (two attributes, `source` and `classifier`) on the port
`logs.sources` (multi-provider). The source and the classifier follow the same protocols as
[log-source](#log-source) and [log-classifier](#log-classifier), and the source names its classifier directly instead
of going through the registry.

**Rules**

- Keep the source id from colliding with entry point sources. On a collision, that runtime source is not attached and
  a `logs.source_failed` warning (reason `logs.runtime_source_rejected`) is recorded.
- Subscribe to the moment new data appears (for example, run event notifications) and schedule a collection. If you
  rely only on periodic collection, the screens lag behind.
- Only read the other module's data.
- Keep classification rules as data (a mapping table), not code. The mapping table of `platform-runs` is an example
  (below).

**Common mistakes**: the source importing the other module's package. Use only the objects received through ports
([Link modules](links.md)).

**Data left after removal**: when the link is off, the source disappears and the events already indexed stay. The
entry in the setting `logs.sources` also stays, unused.

<!-- extdocs:facts runtime-log-source -->
- Registration: A server module provides the port `logs.sources` (symbol `agent_console_mod_logs.ports:LOG_SOURCES`, multiple: yes).
- Interface:
  - `agent_console_mod_logs.ports:RuntimeLogSource` — ``logs.sources`` port entry: a source reading another module's data, with its classifier.
- Built-in implementations: `link-logs-runs`
- Examples:
  - reference: [packages/py/links/ac-link-logs-runs](../../packages/py/links/ac-link-logs-runs/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## Run event mapping table

The `platform-runs` source maps run events (the `type` of `RunEvent`) to log events with a mapping table. The mapping
table is data. The defaults are a data file of the logs and runs link package, and the workspace setting
`logs.sources[id=platform-runs].config.event_map` overrides them **entirely** per key (type). Plugins also use this
table to give their own events a category
([Contracts and events](contracts-events.md#categories-on-the-log-screen)).

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
logs:
  sources:
    - id: platform-runs
      config:
        max_runs: 200
        event_map:
          "acme.*": {category: tool, title: "acme {type} {/payload/status}"}
          acme.call_finished:
            category: tool
            stage: complete
            call_id: "{/payload/call_id}"
            status: {pointer: /payload/ok, map: {"true": ok}, default: error}
            duration_ms: /payload/duration_ms
            tags: [tool]
          acme.noise: {skip: true}
```

**Keys**: a type name or a glob (`*`, `?`). Exact names come first, then the single longest matching glob. When no
rule matches, the category is `other`. Writing an empty rule such as `"memory.*": {}` turns off the default rule, so
the category becomes `other`.

**Values**: string templates fill in `{/JSON pointer}` (relative to the event JSON) and the names `{type}`, `{node}`,
`{parent_node}`, `{thread}`, `{actor}`, and `{run_id}`. Missing values are empty strings. A conditional value
`{pointer, map, default}` turns the pointer value into a string (`true`, `false`, `null`, and numbers in JSON
notation), looks it up in `map`, and otherwise uses `default` (or the value as read, when there is no default). The
`map` values and `default` are templates too.

| Key | Value | Meaning |
| --- | --- | --- |
| `category`, `title`, `stage`, `status`, `tool`, `call_id`, `via`, `model`, `message_id`, `role` | Template or conditional value | The log event field of the same name |
| `from`, `to` | Template or conditional value | Sender and receiver (none when empty) |
| `tags` | List of strings, or a list value `{each, value}` | Tags. `tool` is the agreed tag for tool calls (the same call is indexed only once) |
| `correlation` | Evidence name → template or list value | Evidence that links events (`session` and `call_id` are automatic when they have values) |
| `documents` | One document template `{path, kind, action}` or a list | Documents the event points to. With `each`, one per element; dropped when `path` is empty |
| `duration_ms` | Pointer | Duration of a finished span. When present, two events are emitted: the start (estimated) and the end |
| `session_from` | Pointer | This event announces the node's session id (the session of events of that node and its child nodes) |
| `cwd_from` | Pointer | This event announces the run folder (the basis for grouping later events of the same run by project) |
| `usage` | Token item (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) → pointer | Token sample |
| `skip` | `true` | Not indexed |

A list value `{each: <list pointer>, value: <item template>}` creates one item per element of a list inside the
event. Inside the item template, `{./key}` and `{.}` (the element itself), and `pointer: ./key` in conditional values,
are relative to the element. Empty items are dropped, and duplicate items are kept once.

**Avoid counting tokens twice**: the default mapping table does not use the tokens of run events as samples, because
the same session would be counted twice if it is also read through the Claude Code session log source. To see per-run
tokens in an environment where the session log source is off, add `usage` to the rules of the events that carry
tokens.

A malformed mapping table (including unknown keys) fails the source settings schema check, so collection for that
source fails, and the server reports the warning `logs.source_failed` (error code `logs.invalid_config`). Other
sources keep collecting.

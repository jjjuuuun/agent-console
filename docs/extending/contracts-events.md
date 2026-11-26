# Contracts and events

The shapes of the data that the server, the web, and plugins exchange (definitions, settings, descriptors, REST
requests and responses, run events) live in one place: the contract package `agent-console-contracts`. This page
explains how plugins use the contract, how to match versions, and how to publish your own data that the contract does
not have.

## One source of truth

- The contract is a set of Pydantic models. JSON Schema is generated from them, and the web's TypeScript types
  (`@agent-console/contracts`) are generated from that schema. Nobody writes the same shape by hand in two languages.
- When you change the contract inside the source repository, change the generated output too.

```bash
uv run poe contracts          # regenerate JSON Schema → TS types
uv run poe contracts-check    # check that the generated output matches the current code (fails if it differs)
```

- Plugins import and use the contract models (descriptors, issues, events). Do not change the fields of contract
  models, and do not add your own models to the contract package.

## Versions

The contract has two layers of versions.

| What | Where | Used for |
| --- | --- | --- |
| Package version | The `agent-console-contracts` distribution version (0.x) | Plugin dependency ranges. Compatible within the same minor. Pin to one minor, as in `>=0.16,<0.17` |
| Submodule versions | `CONTRACT_VERSIONS` (feature group → semver) | Tracking changes per group. Adding a field is a minor change, a breaking change is major. A server module reports the submodules it uses and their versions in the descriptor field `contracts` |

The current version table is generated in [contract submodule versions](reference.md#contract-submodule-versions).

```python
>>> from agent_console_contracts import CONTRACT_VERSIONS
>>> sorted(CONTRACT_VERSIONS)[:4]
['architecture', 'chat', 'common', 'definitions']
>>> all(v.count(".") == 2 for v in CONTRACT_VERSIONS.values())
True

```

## Open strings and `Known*` constants

Kind names are not fixed lists (enums) in the contract. Node types, edge types, resource kinds, backend ids, log
categories, and issue codes are all **open strings**. That is why a plugin can use a new name without changing the
contract.

- The only fixed vocabulary left in the contract is values that carry engine meaning (run status, the scheduling mode
  of an edge, and so on).
- The names the built-in implementations use are collected in documentation constants `Known*` (for example,
  `KnownIssueCodes`, `KnownInteractionKinds`, `KnownLogCategories`). These constants are only lists of "values already
  known", not allow lists. Values that are not in them are accepted and shown as they are.

```python
>>> from agent_console_contracts import Issue, KnownIssueCodes
>>> KnownIssueCodes.CONDITION_UNKNOWN_OPERATOR
'condition.unknown_operator'
>>> Issue.model_validate({"severity": "warning", "code": "mine.too_long", "message": "글이 깁니다"}).code
'mine.too_long'

```

## Publishing data the contract does not have

Plugins outside the repository do not change the contract. They publish their own data in these ways.

| Need | How |
| --- | --- |
| Your own REST response shape | A Pydantic model in your own package (the module's `models.py`). For error codes, use the known codes of the contract |
| Your own issues and warnings | A contract `Issue` with a `code` under your prefix (`mine.too_long`) + a human-readable `message` + `details` if needed |
| Error details | Your own keys in `details` (an object) of the error body |
| Settings | A descriptor `config_schema` (JSON Schema) or a module `settings_schema` |
| Things that happen during a run | Event types under your prefix (below) |

## Plugin-owned events

During a run, nodes, backends, and tool providers emit events with `emit(type, payload)` on the run context. If the
contract knows the type, the event is checked against that shape. If it does not, the event is stored and delivered as
a generic `RunEvent`.

- Start the type with your prefix (`<prefix>.<name>`, for example `example_notes.read`). The types the contract knows
  are listed in [known RunEvent types](reference.md#known-runevent-types). Do not use those names.
- Do not put content, secrets, or raw exception text in the payload. Carry only status, counts, and correlation ids
  (`tool_use_id`).
- The web shows unknown types as they are, in a neutral color. They appear in the run history without any web code
  changes.

```python
>>> from agent_console_contracts import KNOWN_RUN_EVENT_TYPES, parse_run_event
>>> "run.started" in KNOWN_RUN_EVENT_TYPES
True
>>> event = parse_run_event(
...     {"event_id": "e1", "run_id": "r1", "seq": 1, "ts": 0.0, "node_path": ["writer"],
...      "type": "mine.checked", "payload": {"status": "ok", "count": 2}}
... )
>>> type(event).__name__, event.type, event.payload
('RunEvent', 'mine.checked', {'status': 'ok', 'count': 2})

```

### Categories on the log screen

Run events are also indexed for the log screen. Which category, title, and status a type shows with is decided by
**mapping table data**, not by code. Types that are not in the mapping table show as category `other`. To give your
events a category, the user adds mapping entries to the settings of the run history log source (each key overrides
the default mapping).

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
logs:
  sources:
    - id: platform-runs
      config:
        event_map:
          "mine.*": {category: tool, title: "내 도구 {/payload/status}"}
          mine.checked:
            category: tool
            status: {pointer: /payload/status, map: {"ok": ok}, default: error}
```

Value templates insert event values with `{/JSON pointer}`, `{type}`, and `{node}`. All keys and rules of the
mapping table are on the [Logs](logs.md) area page.

## Web types

Web packages use the generated types of `@agent-console/contracts`. Web extensions do not define contract shapes on
their own. Keep your own data that the contract does not have in your own types on the web extension side. See
[Web](web.md).

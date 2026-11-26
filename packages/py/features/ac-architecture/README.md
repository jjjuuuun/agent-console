# agent-console-architecture

A pure library for the observed architecture map. It takes log events (contract `LogEvent`) and an architecture map profile (contract `ArchitectureProfile`)
and builds a **self-contained, ready-to-draw** `ArchitectureView` that counts calls, errors, tokens, and duration for each cell and edge.

- No cell, edge, category, tool, or source names are in the code. What to count (`when`, condition data), where to draw it (coordinates), and which source
  fills which cell (`coverage`) are all profile data. Conditions are `ConditionSpec` from `agent-console-conditions`.
- An edge is counted only when one event that recorded that hand-over matches its condition. Neighbors in time are not connected.
  Edges known only by order (`kind: structural`) have no metrics.
- Metric states are `observed` (including 0), `inferred` (estimated), and `not_collected` (value null). **Null is never filled with 0**.
- You use it on its own, without the server, the web app, or a log index. It does not know `agent-console-logs`: error categories, source kinds, and token samples are arguments.

Public API (summary):

| What | Functions |
| --- | --- |
| Read profiles | `load_default_profiles(path=None)`, `parse_profiles_document(text)`, `profiles_from_mapping(data)` |
| Merge | `merge_profiles(defaults, plugins, user, *, include_defaults=None) -> ProfileCatalog` (`pick(requested)` does not raise even when nothing or zero profiles are requested) |
| Validate | `profile_issues(profile, *, operators, filters=None, profile_id=None, unlisted_paths=())`, `check_profile_data(data, ...)`, `unlisted_path_issues(profile, unlisted_paths)` (warning `architecture.condition_path_unlisted` when a condition path is under one of the given prefixes; the caller passes the prefixes as data) |
| Project | `project_architecture(events, profile, *, profile_id, operators, source_kinds, tokens, error_categories, max_seq, notes, matches)` (`events` = `LogEvent` or its JSON rows, `matches` = precomputed judgements, for caching repeated projections) |
| Incremental projection | `ArchitectureTally(profile, *, profile_id)`: add only new events with `add_event(event, match)` and `add_row(row, match)`, and draw with `view(source_kinds=, tokens=, notes=)` (the same as projecting the same events at once. Source kinds are a `view` argument, so changing them does not recount. Duration sums use `math.fsum`) |
| Judge | `ProfileMatcher`, `event_membership(...)`, `selector_predicate(profile, selector, *, profile_id, operators, matcher)`, `format_arch`, `parse_arch` |
| Plugins | entry point `agent_console.architecture_profiles` → `load_profile_plugins(registry)`, `plugin_sources(registry)` |
| Test tools | `agent_console_architecture.testing`: `make_event`, `make_events`, `rename_profile_ids`, `demo_profile` (a synthetic profile YAML for tests only), `load_sample(name)` (collected samples: events, tokens, source kinds, `SAMPLES`) |

## Default profile

The package's default profile data is one profile in `src/agent_console_architecture/data/default_architecture.yaml`,
`agent-architecture` (16 cells, 21 edges, 3 areas).
It is only a default the feature needs to work, and it is user data:

- Turn off: setting `architecture.include_defaults: false` (all) or `architecture.profiles.agent-architecture: null` (this profile only)
- Change: write the whole profile again with the same id (it is replaced as a whole per id). You can also use another file as the default with `load_default_profiles(path)`.
- Conditions look only at the event body that list queries return (`detail` and `raw` are not used). The category, tag, and tool name patterns match the default classification data
  (the `ac-logs-claude` classifier settings, `ac-link-logs-runs` `run_event_map.yaml`), so change them together if you change the classification data.
- It has the collection range per source kind (`coverage`) and a source priority (`source_priority: [claude-code-jsonl, platform-runs]`).
  Even when the same run is read from both platform records and session logs, each cell and edge counts only one source, so the same tool call is counted once.

```python
>>> from agent_console_architecture import load_default_profiles, project_architecture
>>> from agent_console_architecture.testing import load_sample
>>> from agent_console_conditions import default_operators
>>> default = load_default_profiles()["agent-architecture"]
>>> sample = load_sample("run_with_session_log")
>>> view = project_architecture(
...     sample.events, default, profile_id="agent-architecture", operators=default_operators()[0],
...     source_kinds=sample.source_kinds, tokens=sample.tokens,
... )
>>> dispatch = next(c for c in view.cells if c.id == "dispatch")
>>> dispatch.metrics["count"].value, dispatch.selector.arch_sources
(4.0, ['claude-code-jsonl'])

```

For a range that keeps being collected, add only new events to the running tally.

```python
>>> from agent_console_architecture import ArchitectureTally, ProfileMatcher
>>> matcher = ProfileMatcher(default, default_operators()[0])
>>> tally = ArchitectureTally(default, profile_id="agent-architecture")
>>> for event in sample.events:
...     tally.add_event(event, matcher.match(event))
>>> tally.view(source_kinds=sample.source_kinds, tokens=sample.tokens) == view
True

```

The matcher (`ProfileMatcher`) uses the "top-level key items that must be true" of cell and edge conditions (`ac-conditions`
`necessary_items`) to filter out, per value of the most used key (for example `/category`), cells and edges that cannot match, and identical judgement
results share one object (the result is the same as without filtering, checked by a differential test).

## Dependencies: what / why / alternatives

- **ruamel.yaml**: reads profile documents (YAML). It is the repository's standard YAML tool, so it is not a new dependency. Alternative: PyYAML.
- Internal: `agent-console-contracts` (models), `agent-console-conditions` (condition evaluation and validation, operator extensions),
  `agent-console-registry` (plugin loading).

## Installation

```bash
pip install agent-console-architecture
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-architecture
```

## Minimal usage: jsonl events → architecture map

```python
>>> import json
>>> from agent_console_architecture import parse_profiles_document, project_architecture, selector_predicate
>>> from agent_console_conditions import default_operators
>>> from agent_console_contracts.logs import LogEvent

>>> profiles = parse_profiles_document('''
... profiles:
...   flow:
...     cells:
...       ask:   {label: 질문, x: 100, y: 60, when: {all: [{path: /category, op: eq, value: input}]}}
...       work:  {label: 작업, x: 400, y: 60, when: {all: [{path: /category, op: eq, value: tool}]},
...               metrics: [count, errors, duration], group_by: /tool}
...     edges:
...       - {id: hand, from: ask, to: work, kind: structural}
...       - {id: run, from: ask, to: work, label: 실행, when: {all: [{path: /tags, op: contains, value: call}]}}
...     error_when: {all: [{path: /status, op: eq, value: failed}]}
... ''')
>>> lines = [
...     '{"uid": "u1", "seq": 1, "source": "s", "observed_at": 0, "category": "input"}',
...     '{"uid": "u2", "seq": 2, "source": "s", "observed_at": 0, "category": "tool", "tool": "Read", "tags": ["call"], "duration_ms": 40}',
...     '{"uid": "u3", "seq": 3, "source": "s", "observed_at": 0, "category": "tool", "tool": "Read", "status": "failed"}',
...     '{"uid": "u4", "seq": 4, "source": "s", "observed_at": 0, "category": "note"}',
... ]
>>> events = [LogEvent.model_validate(json.loads(line)) for line in lines]
>>> operators, _ = default_operators()
>>> view = project_architecture(events, profiles["flow"], profile_id="flow", operators=operators)

>>> work = view.cells[1]
>>> {name: m.value for name, m in work.metrics.items()}
{'count': 2.0, 'errors': 1.0, 'duration': 40.0}
>>> [(g.key, g.metrics["count"].value) for g in work.groups]
[('Read', 2.0)]
>>> [(e.id, e.kind, {n: m.value for n, m in e.metrics.items()}) for e in view.edges]
[('hand', 'structural', {}), ('run', 'observed', {'count': 1.0, 'errors': 0.0})]
>>> view.unassigned.metrics["count"].value, view.max_seq
(1.0, 4)

```

Clicking a cell picks the same count with a judge function that filters the event table.

```python
>>> keep = selector_predicate(profiles["flow"], work.selector, profile_id="flow", operators=operators)
>>> work.selector.arch, [e.uid for e in events if keep(e)]
('flow:cell:work', ['u2', 'u3'])

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

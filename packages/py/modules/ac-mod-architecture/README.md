# agent-console-mod-architecture

Architecture map feature module (`mod-architecture`). It merges architecture map profiles in the order package defaults → plugins →
user settings (the `architecture` section of the workspace settings) and exposes them through REST and ports.
It does not know about logs or runs. Events are passed in by the caller (the body of a standalone projection, or a link module that uses this module's ports).

| What | Details |
| --- | --- |
| REST | `GET /architecture/profiles` (`ArchitectureProfileList`; turned-off profiles come last with `disabled: true`), `GET /architecture/profiles/{id}` (`ArchitectureProfileDetail`), `POST /architecture/profiles/check` (`ArchitectureProfileCheckRequest` → `ArchitectureProfileCheckResult`), `POST /architecture/project` (`ArchitectureProjectRequest` → `ArchitectureView`) |
| Errors | `architecture.profile_not_found` (404; looking up an id that does not exist, or projecting when there are no profiles at all), `architecture.scope_too_large` (422; the body has more events than `max_request_events`) |
| Provided ports | `architecture.catalog` (merged profiles, operators, checks, projection; shape `ArchitectureCatalog`), `server.warnings` (format problems in the saved `architecture` section, `architecture.settings_invalid`) |
| Optional ports | `workspace.settings` (reads the user settings section; without it, only default and plugin profiles), `architecture.profile_checks` (several providers; the results of `check(profile, profile_id) -> list[Issue]` are added to the `issues` count of the list, the `problems` of the detail, and the check response. For example, the warning of `link-logs-architecture` about condition paths outside the list body) |
| Administrator options | `modules.options.mod-architecture.{max_request_events, max_scope_events}` |
| User settings | The workspace settings `architecture` (contract `ArchitectureSettings`: `include_defaults`, `default_profile`, `profiles`). When the settings change, they are merged again on the next request |
| Plugins | Entry point `agent_console.architecture_profiles`. The host plugin loader (`architecture` of `agent_console.host_plugin_loaders`) reads them into the `architecture_profiles` extension of the host bundle |
| Web role | `architecture` (the *Architecture map* section of the web settings screen requires this role; without the module there is no section) |

- Even with no profiles at all (`include_defaults: false` and so on), the list returns 200 with an empty list ("no architecture map rules").
- When part of the user section is broken (a file edited by hand), the valid parts are used and the rest is reported as warnings. A broken user
  profile is left out, and the default or plugin profile with the same id is shown as it is.
- When the module is off, the routes above return 404 and other features keep working.

## Dependencies: what, why, alternatives

- In-house: `agent-console-architecture` (pure functions for merging, checking, and projection), `agent-console-conditions` (condition
  operators), `agent-console-modkit` (module, host), `agent-console-registry` (registries),
  `agent-console-store` (reading `settings.yaml` in a standalone run, `testing.local_settings_module`).
- External: FastAPI and pydantic (common to server modules). No new external dependencies.

## Install

```bash
pip install agent-console-mod-architecture
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-architecture
```

## Minimal usage: the catalog service without a server

```python
>>> from agent_console_conditions import default_operators
>>> from agent_console_contracts.logs import LogEvent
>>> from agent_console_mod_architecture import ArchitectureCatalogService

>>> operators, _ = default_operators()
>>> section = {"profiles": {"flow": {"cells": {
...     "ask":  {"label": "질문", "when": {"all": [{"path": "/category", "op": "eq", "value": "input"}]}},
...     "work": {"label": "작업", "when": {"all": [{"path": "/category", "op": "eq", "value": "tool"}]}},
... }}}}
>>> service = ArchitectureCatalogService(
...     defaults=dict, settings=lambda: section, operators=lambda: operators
... )
>>> [(p.id, p.origin, p.issues) for p in service.profile_list().profiles]
[('flow', 'user', 0)]

>>> events = [
...     LogEvent(uid="u1", seq=1, source="s", observed_at=0, category="input"),
...     LogEvent(uid="u2", seq=2, source="s", observed_at=0, category="tool"),
... ]
>>> view = service.project(events)
>>> [(c.id, c.metrics["count"].value) for c in view.cells]
[('ask', 1.0), ('work', 1.0)]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Standalone run

```bash
python -m agent_console_mod_architecture --config standalone.json --port 0
```

Without `--with`, a small settings module (`local-settings`) that reads the workspace `settings.yaml` is attached.
Write user profiles in the `architecture` section of that file.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

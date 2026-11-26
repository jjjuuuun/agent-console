# agent-console-mod-definitions

Agent Console definitions feature module. It plugs the store and CRUD routes for workspace definitions (agents, teams, resources, common settings)
into the server, and exposes the ports and the save notification topic that other modules use.

- Routes: `/agents` and `/agents/{id}`, `/graphs`, `/graphs/{id}`, and `POST /graphs/{id}/duplicate`, and `/settings`.
  Responses are the saved document + `ETag` (`version_hash`), with optimistic locking through `If-Match` (required for graph saves: 428 when missing, 412 when different).
- Provided ports: `definitions.store` and `definitions.lookup` (the same file store), `workspace.settings` (`() -> WorkspaceSettings`),
  `secrets.rules` (`() -> SecretRules`), `definitions.checks` (checks the secret rule regular expressions of the common settings),
  `server.warnings` (the plain-text secret scan `secret.plain_found`, and the info `settings.ignored_key` for old top-level keys left in the common settings, for example `projects`
  (`details.key`; reading and startup are not blocked; `ignored_settings_issues`)), and `definitions.save_warnings` (plain-text secret warnings for one saved
  definition, carried in the `X-Console-Issues` header of the create, save, and duplicate responses for agents and teams; the resources module
  uses the same calculation. Saving is allowed; the text is the setting `plain_secret_save_message`). Topic `definitions.saved{kind, id, version_hash}`.
- Optional ports: `definitions.checks` (several providers; pre-save checks, 422 on error. Saves into a space `?project=` use the optional method `space_issues` of the check, or `issues` without it), `graphs.validation`, `graphs.entry_labels`, and
  `graphs.session_summary` (validation summaries, entry names, and session totals `session_summary` of the team list; null without them. Validation summaries of a space list use the provider's optional method `space_summaries`, or null without it), `definitions.spaces` (space name → definition store),
  and `definitions.kind_contributions` (several providers, definition kind contributions; below).
- Kind contributions: when another module provides `KindContribution(DefinitionKind(...))`, kinds with `library=True` are added to the library
  store (at build, and once more in the startup hook after all builds finish). Kinds with `library=False` are not put in the library,
  so library requests for that kind (for example the version routes) return 404, and they go only into project spaces (the space kinds are
  computed by `mod-projects` from the same port). A contribution with the same name as a default kind leaves a warning log and is skipped. The reference
  extraction of contributions (`references`) is read directly from the same port by `mod-projects`, which builds the copy plans.
- Spaces (`?project=<name>`): the agent and team routes (list, get, create, save, delete, duplicate) use that space's store. Without the port,
  409 `feature_unavailable` (nothing is written to the library); an unknown space returns 404 `project.not_found`. Without the query, the library.
  This module does not know what the name means (a project). Save notifications for spaces are published by the provider with `space` in `definitions.saved`.
- Version history: the legacy tables of the host database handle (`BaseServices.database`; the legacy lineage is applied at startup), or memory without it.
- The plain-text scan cache is dropped on `definitions.saved` and on deletes (the calculation lock and a short state lock are separate to prevent deadlocks and stale caches).
- Settings `modules.options.mod-definitions`: `max_content_bytes` (the total size limit for definition bodies, formerly `resources.max_content_bytes`) and
  `plain_secret_issue_codes` (check issue codes to move into the plain-text scan).
- Removed settings keys (the host refuses to start with a `settings.removed_key` error): the old top-level `resources` (points to the new location),
  and `presets` and `modules.options.mod-presets` of the removed presets feature (asks you to delete them).
- Web roles: `definitions:agent`, `definitions:graph`, and `settings`.

## Install

```bash
pip install agent-console-mod-definitions
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-definitions
```

## Minimal usage

Assembling it creates the definition store port, and every save publishes `definitions.saved`. Without a host database handle, version history is kept in memory with a warning (`definitions.versions_memory`).

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_mod_definitions import (
...     DEFINITIONS_SAVED, DEFINITIONS_STORE, SERVER_WARNINGS, WORKSPACE_SETTINGS, module)
>>> root = Path(tempfile.mkdtemp())
>>> base = BaseServices(paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"))
>>> assembly = assemble([module], base=base)
>>> saved = []
>>> _ = assembly.services.events.subscribe(DEFINITIONS_SAVED, lambda item: saved.append(item.id))
>>> store = assembly.port(DEFINITIONS_STORE)
>>> _ = store.create("agent", {"id": "rev", "name": "리뷰어", "token": "ghp_PlainToken123456"})
>>> saved
['rev']
>>> assembly.port(WORKSPACE_SETTINGS)().agent_defaults.backend is None
True
>>> [(w.code, w.path) for w in assembly.ports(SERVER_WARNINGS)[0]()]
[('secret.plain_found', '/token'), ('definitions.versions_memory', None)]

```

Kind contributions: when a contributing module provides a kind, it appears in the library store (kinds with `library=False` do not).

```python
>>> from agent_console_modkit import KindContribution
>>> from agent_console_modkit.testing import fake_module
>>> from agent_console_store import DefinitionKind
>>> from agent_console_mod_definitions import KIND_CONTRIBUTIONS
>>> def contribute(ctx):
...     ctx.provide(KIND_CONTRIBUTIONS, KindContribution(DefinitionKind("note-template", "note-templates")))
...     ctx.provide(KIND_CONTRIBUTIONS, KindContribution(DefinitionKind("note", "notes", library=False)))
>>> kinds = fake_module("kinds", provides=[KIND_CONTRIBUTIONS], on_build=contribute)
>>> root2 = Path(tempfile.mkdtemp())
>>> paths2 = Paths(base_dir=root2, workspace=root2 / "ws", state=root2 / "state")
>>> lib = assemble([module, kinds], base=BaseServices(paths=paths2)).port(DEFINITIONS_STORE)
>>> [k for k in lib.kinds() if k.startswith("note")]
['note-template']

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

Standalone run (the same modkit host, 127.0.0.1 by default). Version history is in `console.sqlite3` in the state folder.

```bash
python -m agent_console_mod_definitions [--with ID] [--config PATH] [--port 0] [--check]
```

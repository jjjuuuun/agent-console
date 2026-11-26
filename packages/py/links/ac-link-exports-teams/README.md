# agent-console-link-exports-teams

Agent Console exports and team semantics link module. It provides `exports.dependencies` (the definitions a definition uses) so that
exports (`mod-exports`) include the agents and resources of a team and the resources of an agent.

- Required port: `definitions.lookup`. Optional: `workspace.settings` (attachments of the common layer are added to the dependencies too) and
  `settings.scope_layers` (several providers, scope id → settings layers; when exporting from a project space, the common attachments of that scope's layers are added too). No routes.
- Teams are resolved with the descriptors of the host base service `registries`.
- When exporting from a project space, `for_lookup(space store, scope=project id)` builds the same calculation for that space (it does not look in
  the shared library). Common attachments of the `scope` layers (for example the project settings layer) are added to the dependencies. When a layer provider
  raises an error, only that provider's layers are left out and the export continues (logged).
- When this link is off, exports contain only the selected items, without adding dependencies automatically.

## Install

```bash
pip install agent-console-link-exports-teams
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-exports-teams
```

## Minimal usage

```python
>>> from agent_console_store import InMemoryDefinitionStore
>>> from agent_console_link_exports_teams import TeamExportDependencies
>>> store = InMemoryDefinitionStore()
>>> _ = store.create("agent", {"id": "alice", "name": "A", "resources": [{"ref": "doc"}]})
>>> deps = TeamExportDependencies(store)
>>> [(d.kind, d.id) for d in deps.dependencies("agent", "alice")]
[('resource', 'doc')]
>>> space = InMemoryDefinitionStore()  # based on another store (a project space)
>>> _ = space.create("agent", {"id": "alice", "name": "A", "resources": [{"ref": "notes"}]})
>>> [(d.kind, d.id) for d in deps.for_lookup(space).dependencies("agent", "alice")]
[('resource', 'notes')]
>>> from agent_console_teams import Layer  # scope id -> scope layers (for example common attachments of the project settings layer)
>>> scoped = TeamExportDependencies(
...     store, scopes=lambda scope: [Layer(scope, scope, {"resources": [{"ref": "guide"}]})]
... )
>>> [(d.kind, d.id, d.shared) for d in scoped.for_lookup(space, scope="app").dependencies("agent", "alice")]
[('resource', 'notes', False), ('resource', 'guide', True)]

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

Standalone run. Without `--with`, it attaches `testing.local_definitions_module` (a file store in the workspace).

```bash
python -m agent_console_link_exports_teams [--with ID] [--config PATH] [--port 0] [--check]
```

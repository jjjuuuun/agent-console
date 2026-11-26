# agent-console-link-definitions-teams

Agent Console definitions and team semantics link module. It connects the definition store to the `ac-teams` calculations.

- Routes: `GET /agents/{id}/usages` and `GET /resources/{id}/usages` (where an item is attached), `GET /agents/{id}/effective-settings`,
  `GET /graphs/{id}/plan` and `POST /graphs/plan` (draft), `GET /graphs/{id}/nodes/{node}/effective-settings` and
  `POST /graphs/effective-settings`, `GET /graphs/{id}/nodes/{node}/bundle-preview` and `POST /graphs/bundle-preview`.
  Plain text in `x-secret` fields and resolved secret values are masked.
- Provided ports: `graphs.entry_labels` (entry names in the team list), `graphs.session_summary` (session totals in the team list,
  `ac-teams.session_summary`; delegation strategies come from the host registries), `definitions.usages` (`usage_count` in the resource list),
  `definitions.dependencies` (the definitions a document uses, `TeamDocumentDependencies`: team → agents, resources, and child teams;
  agent → resources. It is used to order writes so that used definitions come first when several definitions are written at once. No default
  module consumes it today),
  `definitions.references` (several providers; the reference extraction function of the same calculation, `(kind, doc) -> [(kind, id)]`,
  `TeamDocumentDependencies.references`. Project checks and move plans receive it).
- Required port: `definitions.lookup`. Optional: `workspace.settings`, `resources.lookup` and `resources.types` (empty when missing),
  `secrets.redact` (without it, suspected values are masked with `secrets.rules`), `secrets.rules`, `settings.scope_layers` (the layers of `?project=` for effective settings),
  and `definitions.spaces` (routes that read saved items read teams, agents, and resources from the space of `?project=`; resources use `StoreResourceLookup` over that space's store, or an empty lookup when `resources.lookup` is missing. Without the port, the library is used).
- Descriptors: the host base service `registries` (nodes, edges, delegation strategies, backends) is read on every request (`catalog_from_registries`).
- Web role (`WEB_ROLES`): `definitions:teams`. The draft previews of the team editor (`POST /graphs/plan`, `effective-settings`, `bundle-preview`) and the agent usage panel (`GET /agents/{id}/usages`) turn on with this role.
- When this link is off, the routes above return 404 (the web app hides those panels), and entry names, session totals, and usage counts in lists are null.

## Install

```bash
pip install agent-console-link-definitions-teams
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-definitions-teams
```

## Minimal usage

`TeamViews` works without a server. Pass a definition reader (a store) and a descriptor catalog.

```python
>>> from agent_console_store import InMemoryDefinitionStore
>>> from agent_console_teams import TeamCatalog
>>> from agent_console_teams.testing import Kit
>>> from agent_console_link_definitions_teams import TeamViews
>>> kit = Kit()
>>> store = InMemoryDefinitionStore()
>>> graph = kit.graph([kit.person(), kit.worker("a", "alice")], [kit.edge("e1", "entry", "me", "a")])
>>> _ = store.create("graph", graph.model_dump(mode="json", exclude_none=True))
>>> catalog = TeamCatalog(node_types=tuple(kit.node_types), edge_types=tuple(kit.edge_types))
>>> views = TeamViews(store, catalog=lambda: catalog)
>>> [(r.kind, r.id, r.node_ids) for r in views.references("agent", "alice")]
[('graph', 'team', ['a'])]
>>> views.entry_labels(graph)
['A']

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
python -m agent_console_link_definitions_teams [--with ID] [--config PATH] [--port 0] [--check]
```

# agent-console-mod-exports

Agent Console exports feature module. It plugs the export library `agent-console-exports` into the server.

- Routes: `GET /exporters`, `POST /exports/plan` (no writes), `POST /exports/archive` (a zip response; nothing is written to the server
  disk), `GET /exports/roots` (token required), and `POST /exports/write` (only under allowed roots; default `on_conflict=fail`).
- Required port: `definitions.lookup` (definition reading). Optional ports: `exports.dependencies` (without it, only the selected items are exported),
  `secrets.rules` (without it, the default suspicion rules), and `projects.folders` and `definitions.spaces` (below).
- Project assembly: when `projects.folders` is present, the folder write roots are the registered project folders (root id =
  registration id), and the administrator `roots` are not used. The source to export is the space of the query `?project=` (default) or `source=library` (shared library);
  without `project`, the shared library. An unregistered id returns 404 `project.not_found`. Zip downloads work as before. For a project space source,
  the definitions used together are looked up only in that space's store: when the `exports.dependencies` value also has `for_lookup(lookup, *, scope)`
  (`ScopedExportDependencies`), the calculation built from the space store and scope (`scope` = project id) is used; otherwise only the selected items (the shared library
  calculation is not mixed in). The scope is used to add the common attachments of that project's settings layer to the dependencies (the provider knows what the scope means).
- Settings `modules.options.mod-exports` (the old top-level `exports` points to the new location with a `settings.removed_key` error): `roots`, `home`,
  `protected_in_home`, `protected`, `options`, and `expose_paths`. Relative paths are relative to `base_dir`.
- Web role: `exports`.

## Install

```bash
pip install agent-console-mod-exports
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-exports
```

## Minimal usage

Without the definition reading port, the module is off (with the reason reported). Assemble it with a providing module.

```python
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_exports import module
>>> from agent_console_mod_exports.testing import local_definitions_module
>>> assemble([module]).report[0].missing
('definitions.lookup',)
>>> [(r.id, r.state.value) for r in assemble([module, local_definitions_module()]).report]
[('local-definitions', 'active'), ('mod-exports', 'active')]

```

The catalog adapter needs only the definition reading port (missing definitions are None).

```python
>>> import tempfile
>>> from agent_console_store import DEFAULT_KINDS, FileDefinitionStore
>>> from agent_console_mod_exports import LookupExportCatalog
>>> store = FileDefinitionStore(tempfile.mkdtemp(), DEFAULT_KINDS)
>>> _ = store.create("agent", {"id": "a", "name": "A", "backend": "fake-agent"})
>>> catalog = LookupExportCatalog(store)
>>> catalog.document("agent", "a")["name"], catalog.document("agent", "ghost")
('A', None)

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

Standalone run (the same modkit host, 127.0.0.1 by default). Without `--with`, it attaches `testing.local_definitions_module`
(a file store in the workspace folder). To use another provider, pass `--with <module id>`.

```bash
python -m agent_console_mod_exports [--with ID] [--config PATH] [--port 0] [--check]
```

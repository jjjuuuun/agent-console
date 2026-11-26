# agent-console-mod-versions

Agent Console versions feature module. It plugs the definition version list, comparison, and revert routes and the retention count into the
server. The version history itself is kept by the definition store (`agent-console-store`).

- Routes (per collection, default `/agents` `/graphs` `/resources` `/settings`): `…/{id}/versions`,
  `…/versions/{hash}`, `…/versions/{a}/diff[/{b}]`, `…/versions/{hash}/files[/{path}]`, and
  `POST …/versions/{hash}/restore` (`If-Match` required: 428 when missing, 412 when different, 422 on check errors).
- Required port: `definitions.store`. Optional ports: `definitions.checks` (several providers; checks before revert and secret locations; for a space `?project=`, the optional method `space_issues`)
  and `secrets.rules` (the default suspicion rules without it). Subscribed topic: `definitions.saved` (applies the retention count).
- Settings `modules.options.mod-versions` (the old top-level `versions` points to the new location with a `settings.removed_key` error): `max_per_definition` (number of versions to keep per definition;
  empty = keep all; applied on save and on startup), `collections` (the version route table), and `secret_issue_codes`.
- Web role: `versions`.

Spaces: when the optional port `definitions.spaces` is present, every version route uses the version history of the space given by `?project=<name>`.
When a `definitions.saved` entry has a `space`, the retention count is applied in that space too. Without the port, 409
`feature_unavailable`; an unknown space returns 404.

## Install

```bash
pip install agent-console-mod-versions
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-versions
```

## Minimal usage

With a retention count, every save notification (`definitions.saved`) deletes old versions (the current version stays).

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_mod_versions import DEFINITIONS_STORE, module
>>> from agent_console_mod_versions.testing import local_definitions_module
>>> workspace = Path(tempfile.mkdtemp())
>>> config = ModulesConfig(options={"mod-versions": {"max_per_definition": 2}})
>>> assembly = assemble([module, local_definitions_module(workspace=workspace)], config)
>>> store = assembly.port(DEFINITIONS_STORE)
>>> saved = store.create("agent", {"id": "a", "name": "0", "backend": "fake-agent"})
>>> for name in ("1", "2", "3"):
...     saved = store.save("agent", {"id": "a", "name": name, "backend": "fake-agent"},
...                        expected_version=saved.version_hash)
>>> len(store.list_versions("agent", "a"))
2

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
(a file store in the workspace folder, with versions in memory). To use another provider, pass `--with <module id>`.

```bash
python -m agent_console_mod_versions [--with ID] [--config PATH] [--port 0] [--check]
```

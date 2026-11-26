# agent-console-mod-resources

Agent Console resources feature module. It plugs the resource library routes and the lists of resource types and merge strategies into the
server, and exposes the resource lookup and type ports that other modules use.

- Routes: `/resources` and `/resources/{id}` (CRUD; type check errors return 422), `/resources/{id}/content` (body),
  `/resources/{id}/files[/{path}]` (bodies of multiple files; writable only for types with `content.multi_file`), `/resource-types`, and `/merge-strategies`.
  When a segment of a file path is a reserved name (setting `reserved_file_names`, default `.git` and `_bundle`, case-insensitive), the file is saved and
  the warning issue `resource.reserved_file_name` (`path` = JSON Pointer `/files/<file path>`, `details = {path, name}`, the file path in the message) is returned in the `X-Console-Issues` header.
  Where a resource is attached (`/resources/{id}/usages`) is added by `link-definitions-teams`.
- Required port: `definitions.store`. Optional ports: `definitions.usages` (`usage_count` in the list; null without it), `definitions.checks` (several providers, pre-save definition checks: on create and save, errors return 422 `validation_failed`, and warnings and info are saved and carried in the `X-Console-Issues` header. For example `memory.unknown_scope_kind` of a memory resource. Without it, only the type check), and `definitions.save_warnings` (adds the plain-text secret warning `secret.plain_found` of the saved document to the same header. Without it, only the check issues).
- Provided ports: `resources.lookup` (`ac-resources.ResourceLookup` + `FileContentLookup`) and `resources.types` (type registry).
- The type registry is the `resource_types` extension of the host base service `registries`. Without it (standalone run), the entry points and
  the workspace `resource-types/*.yaml` are read directly. The body size limit is enforced by the definition store (`mod-definitions`).
- Settings `modules.options.mod-resources`: `types_extension`, `declarative_dir`, `content_files` (format → body file name),
  `default_content_file`, and `reserved_file_names` (path segment names to warn about; an empty list means no warnings).
- Web role: `definitions:resource`.

Spaces: when the optional port `definitions.spaces` is present, `/resources` and `/resources/{id}/…` use the store of the space given by `?project=<name>`
(`usage_count` in a space list is null). Without the port, 409 `feature_unavailable`; an unknown space returns 404.

## Install

```bash
pip install agent-console-mod-resources
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-resources
```

## Minimal usage

Assembled with a module that provides a definition store, the resource lookup port reads that store.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_resources import RESOURCES_LOOKUP, module
>>> from agent_console_mod_resources.testing import local_definitions_module
>>> workspace = Path(tempfile.mkdtemp())
>>> assembly = assemble([module, local_definitions_module(workspace=workspace)])
>>> lookup = assembly.port(RESOURCES_LOOKUP)
>>> lookup.get_resource("guide") is None
True
>>> (workspace / "resources").mkdir()
>>> _ = (workspace / "resources" / "guide.yaml").write_text(
...     "id: guide\ntype: instruction\nname: 안내\nconfig: {}\n", encoding="utf-8")
>>> lookup.get_resource("guide").name
'안내'

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
python -m agent_console_mod_resources [--with ID] [--config PATH] [--port 0] [--check]
```

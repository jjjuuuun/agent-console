# agent-console-link-definitions-resources

Agent Console definitions and resources link module. It provides the pre-save definition check (`definitions.checks`).

- Resource definitions: the check of that resource type (`ac-resources.validate_resource`; issue paths are relative to the document, `/config/...`).
- Agents, teams, and common settings: the type check of the result after applying each resource attachment's `config_override`
  (plain text in `x-secret` fields is rejected; when the resource does not exist, the suspected-secret rules apply). The resource
  edges of a team are resolved through the descriptors (host `registries`).
- This check is used by the pre-save checks of the definition save routes and version revert, and by the plain-text scan of `/server-info`
  (the definitions module collects the plain-text issues of the checks).
- Required ports: `definitions.lookup` and `resources.types`. Optional: `resources.lookup` (without it, resources are looked up through
  `definitions.lookup`), `secrets.rules`, and `definitions.spaces`. No routes.
- Checks for saving into a space (for example a project, `?project=`) use the optional method `space_issues(space, kind, document)`.
  An attachment `ref` is resolved only against the resources of that space's store; it does not fall back to the library (`resources.lookup`).
  Consumers (the definitions and versions modules, the validation routes) call this method when it exists and `issues` otherwise.
- When this link is off, definitions are saved without resource checks (the definitions module logs a warning at startup).

## Install

```bash
pip install agent-console-link-definitions-resources
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-definitions-resources
```

## Minimal usage

The checker works without a server. Pass the resource type registry, the resource lookup, and the team resolver as functions.

```python
>>> from agent_console_resources import InMemoryResources, new_resource_types
>>> from agent_console_link_definitions_resources import DefinitionChecker
>>> checker = DefinitionChecker(
...     types=new_resource_types, resources=InMemoryResources, plan_of=lambda graph: None)
>>> agent = {"id": "a", "name": "a",
...          "resources": [{"ref": "later", "config_override": {"token": "ghp_abcdefghijk"}}]}
>>> [(i.severity, i.path) for i in checker.issues("agent", agent)]
[('warning', '/resources/0/ref'), ('error', '/resources/0/config_override/token')]
>>> checker.issues("agent", {"id": "b", "name": "b"})
[]
>>> spaced = DefinitionChecker(
...     types=new_resource_types, resources=InMemoryResources, plan_of=lambda graph: None,
...     space_resources=lambda space: InMemoryResources())
>>> [(i.severity, i.path) for i in spaced.space_issues("p1", "agent", agent)]
[('warning', '/resources/0/ref'), ('error', '/resources/0/config_override/token')]

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

Standalone run. Without `--with`, it attaches `testing.local_sources_module` (a file store and the installed resource types).

```bash
python -m agent_console_link_definitions_resources [--with ID] [--config PATH] [--port 0] [--check]
```

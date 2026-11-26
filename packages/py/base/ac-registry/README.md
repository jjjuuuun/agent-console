# agent-console-registry

A typed registry (`Registry[T]`) and plugin loading (entry points, explicit module paths, `register(target)` plugins).
The base package that lets every Agent Console extension point (node types, execution backends, classifiers, and so on) use the same registration method.

- **No global state**: the caller creates the registry and injects it.
- **Knows no extension point**: entry point group names and extension point names are not in this package. The caller passes them all.
- **Load failures are reports, not exceptions**: loaders return a `LoadReport` per item (import failure, missing attribute, validation failure, duplicate key).
- Registering the same `(key, version)` twice raises `DuplicateKeyError`. Only `register(..., replace=True)` overwrites.
  Entry points are read in `(name, value)` order, so when one group has the same name twice, the one whose value (module path) sorts first stays and the later one is
  `failed` (regardless of the order passed in). Different versions stay together, and a lookup without a version returns the latest.
- **Validators belong to the registry**: attach one with `Registry(name, validator=as_x)` (or `set_validator`) and
  entry points, modules, `register(target)` plugins, and direct `register` calls all go through the same check.
  A rejection raises `InvalidExtensionError` (loaders report `failed`).

## Installation

```bash
uv sync --all-packages                        # inside the workspace
uv pip install ./packages/py/base/ac-registry      # standalone, from another project
```

## Minimal usage

```python
>>> import types
>>> from agent_console_registry import Registry, UnknownExtensionError, load_modules, load_plugins

>>> node_types: Registry[str] = Registry("node_types")  # the name is used in messages
>>> node_types.register("echo", "echo v1", source="직접")
RegistryEntry(key='echo', version=1, item='echo v1', source='직접')
>>> node_types.register("echo", "echo v2", version=2)
RegistryEntry(key='echo', version=2, item='echo v2', source='')
>>> node_types.get("echo"), node_types.get("echo", 1)  # no version = latest
('echo v2', 'echo v1')

```

Local modules that are not installed are read as `"pkg.mod:attr"` or `"key=pkg.mod:attr"`. The example below injects an import function
to use a fake module (in real use, omit it and `importlib.import_module` is used).

```python
>>> fake = types.ModuleType("my_local.nodes")
>>> fake.upper = "UPPER"
>>> fake.plugin = lambda target: target.register("lower", "lower")
>>> modules = {"my_local.nodes": fake}
>>> reports = load_modules(
...     ["upper=my_local.nodes:upper", "my_local.missing:x"], node_types, import_module=modules.__getitem__
... )
>>> [(r.key, r.status) for r in reports]  # failures come back as reports instead of exceptions (shown on screen without killing the server)
[('upper', 'loaded'), ('x', 'failed')]

```

A plugin that registers into several registries at once is `obj.register(target)` or `obj(target)`. With `enabled`,
registered keys not in that set are removed; with `disabled`, keys in that set are removed; both are reported as `disabled`
(when `enabled` is given, `disabled` is subtracted from it). The report's `reason` tells which list caused it.

```python
>>> reports = load_plugins(
...     ["my_local.nodes:plugin"],
...     target=node_types,
...     enabled={"echo", "upper"},
...     watch=lambda: [node_types],
...     import_module=modules.__getitem__,
... )
>>> [(r.key, r.status) for r in reports]
[('plugin', 'loaded'), ('lower', 'disabled')]
>>> reports[1].reason
'not in enabled'
>>> [(e.key, e.version) for e in node_types.list()]  # ascending key order, latest per key (all_versions=True for all)
[('echo', 2), ('upper', 1)]
>>> try:
...     node_types.get("nope")
... except UnknownExtensionError as exc:  # a KeyError subclass
...     print(exc)
[node_types] 등록되지 않은 확장: key='nope'

```

A registry with a validator checks items no matter how they come in (the value the validator returns is what gets registered, for example class → instance).

```python
>>> from agent_console_registry import InvalidExtensionError
>>> sizes: Registry[int] = Registry("sizes", validator=int)
>>> sizes.register("a", "3").item
3
>>> try:
...     sizes.register("b", "x")
... except InvalidExtensionError as exc:  # not registered
...     print("b" in sizes)
False

```

Installed packages are read with `load_entry_points("my_app.node_types", registry, enabled=None, validate=..., version_of=...)`
(the caller chooses the group name). In the plugin package's `pyproject.toml`:

```toml
[project.entry-points."my_app.node_types"]
echo = "my_plugin.nodes:echo_node"
```

## Public API

| Name | Description |
| --- | --- |
| `Registry[T](name="registry", *, validator=None)` | `register(key, item, *, version=1, source="", replace=False) -> RegistryEntry[T]`, `unregister(key, version=None)`, `get(key, version=None) -> T`, `get_entry(key, version=None)`, `versions(key) -> list[int]`, `list(*, all_versions=False) -> list[RegistryEntry[T]]`, `validator`, `set_validator(v)`, `in`, `len` |
| `Validator[T]` | `Callable[[Any], T]`; rejects by raising, and feeding a passed value back in gives the same value (idempotent) |
| `RegistryEntry[T]` | `key`, `version`, `item`, `source` (frozen) |
| `load_entry_points(group, registry, *, enabled=None, disabled=(), validate=None, version_of=None, entry_points=None) -> list[LoadReport]` | `entry_points` lets tests inject a list of `EntryPoint`. `disabled` takes precedence over `enabled` |
| `load_modules(paths, registry, *, validate=None, version_of=None, import_module=importlib.import_module) -> list[LoadReport]` | |
| `load_plugins(paths, target, *, enabled=None, disabled=(), watch=None, import_module=...) -> list[LoadReport]` | The shape of `target` is unknown to it. `enabled` and `disabled` apply to keys newly added to the registries that `watch()` returns |
| `excluded_reason(name, enabled, disabled=()) -> str \| None` | The reason to leave it out (`REASON_DISABLED` = `"in disabled"`, `REASON_NOT_ENABLED` = `"not in enabled"`) or None |
| `LoadReport` | `source`, `status` (`loaded`/`failed`/`skipped`/`disabled`), `key`, `version`, `error`, `reason` (why `skipped` or `disabled`), `ok` |
| Exceptions | `RegistryError` ⊃ `DuplicateKeyError`, `InvalidExtensionError` (a `TypeError` subclass), `UnknownExtensionError` (a `KeyError` subclass) |

## Dependencies

| What | Why | Alternatives |
| --- | --- | --- |
| (none) standard library `importlib.metadata`, `importlib` | Enough for entry point discovery and explicit module loading, and editable installs in a uv workspace are picked up right away | `pluggy` (a hook-call model, too much for "look up the implementation per type"), `stevedore` (more dependencies) |

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-registry`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/base/ac-registry/tests
```

Tests do not depend on actually installed packages. They check entry point registration two ways: by injecting `EntryPoint`, and with a test-only
`*.dist-info/entry_points.txt` created in `tmp_path`.

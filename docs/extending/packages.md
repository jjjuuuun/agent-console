# Creating packages

An extension comes in as one package. A package does one job, separates its public API from its internal
implementation, and still installs and passes its tests when you take it outside the repository. This page covers two
cases separately: creating a plugin package outside the source repository, and adding a built-in package inside it.

## Outside the repository (plugin authors)

### Minimal `pyproject.toml`

```toml
[project]
name = "my-console-notes"                    # your own name. Do not use the agent-console- prefix
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "agent-console-contracts>=0.16,<0.17",   # write a range for each server package you use
]

[project.entry-points."agent_console.node_types"]   # extension point = entry point group
"mine.note" = "my_console_notes:NoteNode"          # name = registration id

[build-system]
requires = ["uv_build>=0.8.17,<0.9"]
build-backend = "uv_build"
```

Put one folder named after the import name under `src/` (`src/my_console_notes/__init__.py`). For a walkthrough from
start to finish, see [Get started](getting-started.md).

### Naming rules

| What | Rule | Example |
| --- | --- | --- |
| Distribution name | Your own name. Avoid `agent-console-*`, which the server distribution uses | `my-console-notes` |
| Import name | The distribution name with `-` replaced by `_`. Avoid `agent_console_*` | `my_console_notes` |
| Registration id (entry point name) | Your prefix + a dot + a name, so that it does not collide with built-in implementations | `mine.note`, `acme.relay` |
| Event type, issue code | Start with your prefix | `mine.note_saved`, `mine.too_long` |
| Server module id | The recommended forms are `mod-<name>` for feature modules and `link-<a>-<b>` for link modules | `mod-notes`, `link-notes-runs` |

The prefixes on registration ids, events, and issue codes keep plugins from colliding with each other. When a group
has two entries with the same name, only one is registered ([Plugin basics](plugins.md#names-and-duplicates)).

### Dependency ranges

- Depend on server packages **by name and version range** only. Do not use path dependencies (`path = "../.."`) or
  paths relative to the repository.
- A 0.x package promises compatibility only within the same minor version. Pin to one minor, as in `>=0.16,<0.17`.
- Match the range of the contract (`agent-console-contracts`) to the contract version of the installed server. For
  versions and submodule versions, see [Contracts and events](contracts-events.md#versions).
- Depend only on what you use. A condition operator needs only the contract, and a node type uses the protocols of the
  runtime (`agent-console-runtime`). Put server packages you use only in tests in the dev dependencies.

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "agent-console-conditions>=0.1,<0.2",    # only when the tests check with the evaluator
]
```

The in-house packages are not on PyPI. When you install or run `uv sync`, pass the wheelhouse as a search path
(`--find-links <wheelhouse>`). For details, see [Distribution](distribution.md).

## Inside the repository (built-in packages)

### Python

```bash
uv run poe new-package --kind feature ac-notes
uv run poe new-package --kind module ac-mod-notes --id mod-notes
uv run poe new-package --kind link ac-link-notes-runs --id link-notes-runs
```

| Kind | Folder | What |
| --- | --- | --- |
| `base` | `packages/py/base/` | A thin layer that almost every package uses, such as contracts and registries. Avoids depending on other in-house packages |
| `feature` | `packages/py/features/` | Feature libraries. They do not know the server framework, the module kit, or server modules |
| `kit` | `packages/py/kit/` | The module kit. It knows only the base layer |
| `module` | `packages/py/modules/` | Server modules. Each plugs one feature library into the server. Runs standalone with `python -m <import name> --check` |
| `link` | `packages/py/links/` | Link modules. Each connects the public ports of two server modules |

`new-package` creates the folder from a template, adds the name to the workspace members and the root
`[tool.uv.sources]`, and updates the import rule lists. Names are aligned as folder `ac-<name>`, distribution
`agent-console-<name>`, and import `agent_console_<name>`. Use `--dep` and `--dev-dep` for dependencies, and
`--dry-run` to see only the files it would create.

After you create it:

- **Import rules**: write what is allowed and forbidden between packages, per group, in `importlinter.rules.toml` (for
  example, "feature modules do not know each other"). After a change, apply it with `uv run poe importlinter-sync`. New
  packages join the group rules automatically.
- **Portability**: `uv run poe pkg-lint` checks for paths outside the package, per-package `[tool.uv.sources]`,
  imports of other packages' `tests`, required files, and tool settings. The check that really copies the package
  outside the repository and runs it is `uv run poe portability --package <folder name>`.
- **Extension point declarations**: if you created a new entry point group constant or a new port, add
  `[tool.agent-console.extension-points.<slug>]` to that package's `pyproject.toml`. If it is missing,
  `uv run poe extpoints-check` fails. For the declaration format, look at packages that already declare one (each row
  of the [extension point reference](reference.md#extension-points) is one declaration).

### TypeScript

```bash
pnpm new-package --kind lib notes-view
pnpm new-package --kind config my-config
```

- `lib` goes in `packages/ts/lib/`, and `config` is a shared configuration package. If the package uses React
  components, pass `--dom`.
- A package's `exports` point to the sources with the `development` condition and to `dist` with `types` and
  `default`. Write in-house dependencies as `^x.y.z` ranges (the `workspace:` protocol is not allowed).
- `pnpm pkg-lint` checks paths, exports, dependency declarations, and that README examples are in sync, and
  `pnpm portability --package <name>` installs, builds, and tests the package outside the repository.

For web extensions as a whole, see [Web](web.md).

## README and tests

Every package has a README and tests. The README has at least the following.

| Section | Contents |
| --- | --- |
| What it does | One or two paragraphs. Which extension points it uses |
| Install | The install command (including the wheelhouse search path) |
| Minimal use | An example that works without a server. For Python, write it as a `>>>` doctest so the tests run it too |
| Registration and settings | The entry point table, settings keys |
| Install and remove | Install and uninstall commands, restarting, the data and warnings left after removal |
| Test | The command that runs the tests |

Leave one blank line after the expected output of a doctest (so the closing fence line is not read as output). To see
what an example README really looks like, open any example in the [example index](../../examples/extensions/README.md).

Export the public API from the package root (`__init__.py`, `src/index.ts` for TypeScript), with type hints and short
documentation (purpose, arguments, return value, exceptions). Do not import other packages' `_` modules or `tests`. If
you need test doubles, use the public `testing` module of that package ([Testing](testing.md#4-assembly-tests)).

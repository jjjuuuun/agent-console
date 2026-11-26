# Testing

Test extensions without starting a server. The server packages publish their test tools, so plugins outside the
repository use the same tools. The levels below go from light to heavy. Levels 1 to 3 are enough for most plugins.

| Level | What it checks | Tools |
| --- | --- | --- |
| 1. Unit | The decisions and transformations of your implementation | pytest, the feature library of the target point |
| 2. Registration | The entry point is read and passes the checks | Inject an `EntryPoint` into the registry loader |
| 3. Contract test suites | The implementation keeps the meaning of an injection point | `*ContractTests` |
| 4. Assembly | Server modules and links fit with other modules | Module kit `assemble` + double modules |
| 5. Portability | The package folder installs and tests on its own | Wheelhouse + a copy |
| 6. Screens | It shows up on the real screens with a running server | E2E |

## 1. Unit

The protocol of a point lives in a feature library (a package you use without the server). For example, test a
condition operator directly with the evaluator `agent_console_conditions`, and node and edge types with the engine
`agent_console_runtime`. With the clock, recorder, and harness (`make_harness`) of `agent_console_runtime.testing`, the
engine runs deterministically without storage.

Take external calls (models, network, file system) through the constructor or arguments, and pass fakes in tests.

## 2. Registration

You can test entry point loading without installing anything. The loader takes a list of `EntryPoint` objects. This
is also where you check that duplicate names, import failures, and failed checks come out as reports instead of
exceptions.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_conditions import (
...     CONDITION_OPERATORS_GROUP, load_condition_operators, new_operator_registry,
... )
>>> def ep(name, value):
...     return EntryPoint(name, value, CONDITION_OPERATORS_GROUP)
>>> registry = new_operator_registry()
>>> reports = load_condition_operators(registry, entry_points=[
...     ep("mine.same", "agent_console_conditions.builtin:EQ"),
...     ep("mine.same", "agent_console_conditions.builtin:NE"),       # same name: the later one fails
...     ep("mine.broken", "no_such_package:Op"),                      # import failure
...     ep("mine.not_op", "agent_console_conditions:CONDITION_OPERATORS_GROUP"),  # not an operator
... ])
>>> [(r.key, r.status) for r in reports]
[('mine.broken', 'failed'), ('mine.not_op', 'failed'), ('mine.same', 'loaded'), ('mine.same', 'failed')]
>>> [entry.key for entry in registry.list()]
['mine.same']

```

To test reading the real entry points of an installed package, install the package in development mode
(`uv pip install -e .`) and call the loader without arguments ([Get started](getting-started.md#6-test)).

## 3. Contract test suites

**Injected implementations** such as stores and indexes have many rules to keep. Points like these publish a test
suite class. Create a subclass and fill in the one method that builds your implementation, and pytest runs every test
in the suite.

```python
from agent_console_wiki.testing import WikiSearchContractTests


class TestMyIndex(WikiSearchContractTests):
    def make_index(self, tmp_path, **options):
        return MyIndex(tmp_path / "idx", **options)
```

| Suite | Point | Import |
| --- | --- | --- |
| `WikiSearchContractTests` | Wiki search index | `agent_console_wiki.testing` |
| `WikiHistoryContractTests` | Wiki page history store | `agent_console_wiki.testing` |
| `WikiPagesContractTests` | Wiki page storage | `agent_console_wiki.testing` |
| `MemoryStoreContractTests` | Memory store | `agent_console_memory.testing` |
| `LogIndexContractTests`, `PurgeContractTests` | Log index | `agent_console_logs.testing` |

To see whether a point has a suite, check whether the "Example kinds" column of the
[extension point reference](reference.md#extension-points) is `contract-tests`. An example that passes a suite:
[agent-console-example-wiki-search](../../examples/extensions/agent-console-example-wiki-search/README.md).

## 4. Assembly tests

Assemble server modules and links without a server, using the module kit's `assemble`. If you need other modules,
use **double modules** instead of the real ones. The doubles are in each package's public `testing` module.

| Double | Where | What it provides |
| --- | --- | --- |
| `fake_module(id, provides=, requires=, optional=)` | `agent_console_modkit.testing` | An empty module with only ports |
| `echo_module` | `agent_console_modkit.testing` | A small module with REST, WS, settings, and an optional port |
| `example_plugin_loader`, `open_recording_database` | `agent_console_modkit.testing` | Doubles for a host plugin loader and a DB factory |
| `static_settings_module(settings)` | The `testing` module of each server module that reads settings (for example, `agent_console_mod_wiki.testing`) | The common settings port with fixed values |
| `local_settings_module`, `library_module`, `records_module` | Same | Workspace settings, the definition store, the project record space |

To check REST after assembly, pass the result to `agent_console_modkit.host.create_host_app` and call it with
`TestClient`. Examples are in [Server modules](modules.md#turning-on-and-off) and
[Link modules](links.md#adding-items-to-multi-provider-ports). Things to check:

- When a module is off, only its paths return 404 and the rest stays the same
- A missing required port gives `unsatisfied`, and a missing optional port returns 409 only for that behavior
- Wrong administrator options make only this module `failed`
- `/health` returns 503 before the startup hooks finish

Module packages also test `python -m <import name> --check` (standalone run, then `/health` 200, then exit).

## 5. Portability

A package folder copied outside the repository must still install and pass its tests. In-house dependencies come from
the wheelhouse.

```bash
# inside the repository
uv run poe wheels                                   # → dist/wheelhouse
uv run poe portability --package <package folder name>   # copy to a temporary folder → uv sync → ruff, mypy, pytest
uv run poe portability --wheels                     # rebuild the wheelhouse and check everything

# a plugin outside the repository
uv sync --find-links <wheelhouse>
uv run pytest
```

For TypeScript packages and the `examples/web/` examples, use `pnpm portability --package <name>`. If the tarballs it
needs are not in `dist/npm`, the tool runs `pnpm pack:all` first. After you change package sources, add `--pack` to
rebuild the tarballs.

## Examples in the repository

The example packages under `examples/extensions/` are not workspace members. They are tested with each folder's own
settings, without installing them.

```bash
uv run poe examples                    # mypy and pytest per example folder (including README doctests)
uv run poe check                       # all checks (including the examples step)
```

`poe examples` finds and checks every folder under `examples/extensions/` that has a `pyproject.toml`. A new example
folder is included without adding it to a list, and a folder without `pyproject.toml` makes the step fail. Where it
looks and which commands it runs are in `[examples]` of `scripts/pkgkit/pkgkit_py.toml` (use `--list` to see the
folders it found, and `--package <folder name>` to run just one). An example README must have the required sections
(minimal code, registration, install and remove, test) to pass `uv run poe extpoints-check`.

`uv run poe portability` also copies the examples outside the repository and checks them (they are part of the full
run).

```bash
uv run poe portability --package <example folder name> --wheels   # one example
uv run poe portability --wheels --no-examples              # workspace packages only, without the examples
```

## 6. Screens (E2E)

```bash
pnpm e2e 08-extension                  # ext setup: install the example packages into a temporary folder, start the server, and check
```

The `ext` setup of the E2E tests installs all examples from `examples/extensions/` into a temporary folder and starts
the server. It checks that the examples appear in the server lists (`/node-types`, `/edge-types`,
`/condition-operators`, and so on) and on the screens, and that they run. For a plugin outside the repository, start
your own server and check the same list APIs ([Get started](getting-started.md#5-check)).

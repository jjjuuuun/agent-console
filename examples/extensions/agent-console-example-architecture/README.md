# agent-console-example-architecture

An example that adds a new **architecture map profile** with a single plugin package.
No engine, server, or web code changes. Once installed, it appears in the architecture map profile list (`GET /api/v1/architecture/profiles`)
with `origin: plugin:agent-console-example-architecture`, and it disappears when removed.

Profile `example-minimal` (2 cells, 1 edge)
- The content is not code but the data file `src/agent_console_example_architecture/data/example_architecture.yaml`.
  The format is the same as the workspace setting `architecture.profiles` (contract `ArchitectureProfile`).
- The cell ids and category values are arbitrary values chosen by the example. They are not a user team or the default profile.
- A log source plugin that ships a profile for its own format uses the same entry point.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

The entry point target is a single function without arguments. It returns `{profile id: profile data}` (a mapping or an `ArchitectureProfile`).

```python
>>> def profiles():
...     return {
...         "tiny": {
...             "title": "작은 구조도",
...             "cells": {"all": {"label": "모든 이벤트", "x": 100, "y": 60}},
...         }
...     }

```

The loader (the host plugin loader of `mod-architecture`) calls this function, checks the format, and attaches the origin name
`plugin:<distribution name>`. Below, this package's implementation (`agent_console_example_architecture:profiles`,
which reads the data file) is loaded as if it were registered as an entry point.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_architecture import (
...     ARCHITECTURE_PROFILES_GROUP, load_profile_plugins, new_profile_registry, plugin_sources,
... )
>>> ep = EntryPoint(
...     "example.architecture", "agent_console_example_architecture:profiles",
...     ARCHITECTURE_PROFILES_GROUP,
... )
>>> registry = new_profile_registry()
>>> [report.status for report in load_profile_plugins(registry, entry_points=[ep])]
['loaded']
>>> [(s.origin, sorted(s.profiles)) for s in plugin_sources(registry)]
[('plugin:example.architecture', ['example-minimal'])]

```

When you build the `EntryPoint` directly without installing, there is no distribution information, so the origin name is the entry point name.
When installed, it becomes `plugin:agent-console-example-architecture` (the tests check both).

## Registration

```toml
[project.entry-points."agent_console.architecture_profiles"]   # agent_console_architecture.ARCHITECTURE_PROFILES_GROUP
"example.architecture" = "agent_console_example_architecture:profiles"
```

- The entry point name (`example.architecture`) is the registry key. The server setting `plugins.enabled` (allow list) selects by this name.
- A data file inside the package is distributed with it (`uv_build` default).

The merge order is package defaults (with `include_defaults`) → plugins → user. When you write the same id in the workspace settings,
the user profile wins, and writing null shows it as a turned-off profile (`disabled: true`).

```yaml
architecture:
  default_profile: example-minimal   # the profile the architecture map screen selects first (optional)
  profiles:
    example-minimal: null            # turn off only this profile while it stays installed
```

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-architecture   # install
uv pip uninstall agent-console-example-architecture                        # remove
```

**Restart the server** after installing or removing.
- Install: `GET /api/v1/architecture/profiles` lists `example-minimal` with `origin: plugin:agent-console-example-architecture`,
  and you can choose it in the profile list of the architecture map screen. `POST /api/v1/architecture/profiles/check` shows the check results too.
- Remove: it disappears from the list. When the settings chose this id as `default_profile`, the default profile and a fallback notice appear instead.
- Turn off while installed: remove `example.architecture` from the server setting `plugins.enabled`, or set it to null in `architecture.profiles` as above.

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

```bash
cd examples/extensions/agent-console-example-architecture
uv run --project ../../.. python -m pytest
```

The tests run without installing (`pythonpath = ["src"]`). Installing and removing are simulated by creating and deleting this package's `dist-info` in a temporary folder,
and the list is checked in the same order as server startup (host plugin loader → `mod-architecture` assembly).
The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).

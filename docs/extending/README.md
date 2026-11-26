# Extension guide

Agent Console has an empty engine, and every capability comes in by registration. Node and edge types, execution
backends, log sources, resource kinds, and each server feature are all "implementations registered at an extension
point". The built-in features are registered the same way. This folder explains how to use that path from the outside.

## What do you want to change

Ask the questions below in order. The higher the answer, the less code you write and the lower the maintenance cost.

### 1. Is changing data enough?

If user data such as settings, definitions (agents, teams, resources), document templates, or rules can do the job,
do not write code.

| What you want to change | Where |
| --- | --- |
| Turn server features on and off, per-feature administrator settings | Server settings file `modules.enabled`, `modules.disabled`, `modules.options.<module id>` |
| Agents, teams, resources, common settings | The screens, or the YAML files in the workspace folder |
| Turn off some installed plugins or choose which ones to use | Server settings `plugins.disabled`, `plugins.enabled` ([Plugin basics](plugins.md#turning-plugins-on-and-off)) |
| Resource kinds (without code) | Declarative resource kind YAML ([Resources](resources.md)) |
| Rules such as task syntax, wiki syntax, architecture map profiles, memory scopes | The data section of each area page ([Specs](sdd.md), [Wiki](wiki.md), [Architecture map](architecture.md), [Memory](memory.md)) |

The data points are the rows in the [extension point reference](reference.md#extension-points) whose registration
kind is `data`, `definition`, or `annotation`.

### 2. Do you want one more of an existing kind? Write a plugin

If you are **adding one more item to a kind that already has several**, such as node types, edge types, condition
operators, execution backends, log sources, or usage sources, you need one plugin package. Add one entry point line to
the package's `pyproject.toml`, install the package into the same Python environment as the server, and restart the
server. You do not change server or web code.

- If this is your first time, [Get started](getting-started.md) walks through creating, installing, checking, and
  removing one condition operator.
- The common rules (names, load time, failure handling, turning off) are in [Plugin basics](plugins.md).
- The available groups are in the [entry point group table](reference.md#entry-point-groups). Each point is described
  on its area page: [Team graph and runs](graph.md), [Execution backends](backends.md), [Resources](resources.md),
  [Usage](usage.md), [Logs](logs.md), [Import and export](transfer.md), [Server host and modules](host.md),
  [Projects](projects.md), [Architecture map](architecture.md), [Memory](memory.md), [Specs (SDD)](sdd.md),
  [Wiki](wiki.md), [Localization](i18n.md).

### 3. Do you need a new feature? Write a server module

A feature with new REST paths, its own storage (DB tables), and its own settings section is a server module. A module
connects to other modules only through port names. When you turn it off, only that feature's paths disappear and the
rest keeps working. See [Server modules](modules.md).

### 4. Do you want to connect two features? Write a link module

To make two existing features (for example, a notes feature and runs) use each other, add one link module without
changing either feature. A link module sees only the public ports of the two features and turns only itself off when
one side is missing. See [Link modules](links.md).

### 5. Do you want to change the screens? See the web guide

The settings schema of a server plugin is drawn as a settings form without web code. When you need web code, such as
for a new widget or a dashboard cell, see [Web](web.md).

## Documents

| Document | Contents |
| --- | --- |
| [Get started](getting-started.md) | Your first plugin end to end: create, install, check, turn off, remove |
| [Creating packages](packages.md) | Creating packages inside and outside the source repository, names and version ranges, README and tests |
| [Plugin basics](plugins.md) | Entry point rules, loading, failures, duplicates, turning on and off, settings schemas, secrets |
| [Server modules](modules.md) | Module descriptor, ports, settings, migration branches, standalone runs, turning off |
| [Link modules](links.md) | Connecting two features, required ports and `unsatisfied`, multi-provider ports, forbidden imports |
| [Contracts and events](contracts-events.md) | Shared types, versions, open strings, plugin-owned events and issue codes |
| [Testing](testing.md) | Contract test suites, test doubles, assembly tests, portability checks |
| [Distribution](distribution.md) | Wheels and tarballs, install and uninstall, version compatibility, checks before publishing |
| [Extension point reference](reference.md) | Tables of points, groups, ports, modules, and contract versions (generated) |
| Area pages | One section per point: when to use it, minimal shape, rules, common mistakes |
| [Example index](../../examples/extensions/README.md) | Example packages you can install, and the points they show |

## Keeping docs and code in sync

Each extension point is declared by the package that defines it, in its `pyproject.toml` (`package.json` for
TypeScript). The reference tables and the "registration, interface, built-in implementations, examples, turning off"
blocks of the area pages are generated from those declarations and the code. When you add or change a point in the
source repository:

```bash
uv run poe extpoints-check   # compare the code (group constants, entry points, module ports) with the declarations
uv run poe extdocs           # regenerate the reference tables, generated blocks, and example index
uv run poe extdocs-check     # check for stale output, links, and document snippets
```

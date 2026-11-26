# Link modules

Code that makes two features use each other does not go into either feature. It goes into a **link module** (link).
For example, "a running agent reads notes" belongs neither to the notes feature nor to the runs feature. With a link
module, the two features can each be used without knowing about the other, and you can turn off or remove just the
link.

Full example: [agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
(it connects the notes module example with the runs module and gives agents a tool that reads notes).

## Shape

A link has the same shape as a [server module](modules.md) (`descriptor` + `build`) and uses the same entry point
group (`agent_console.server_modules`). There are two differences.

- The descriptor has `kind="link"`. An id of the form `link-<a>-<b>` is recommended.
- The ports of the two features it connects are **required** (`requires`). If either is missing, only this link is
  turned off as `unsatisfied`, and the server and other modules start as usual. `GET /api/v1/modules` shows the
  missing ports in `missing`.

The code that writes the descriptor and `build` is in
[How to build a link module](../../examples/extensions/agent-console-example-link/README.md#how-to-build-a-link-module)
in the example README.

## Only public ports

- A link does not import the packages of the two feature modules. Ports are matched by name strings. Declare again, in
  your own `ports.py`, a `PortKey` with the same name and the shape (protocol) of the methods you actually use.
- If a feature module exports public port declarations (`<module package>.ports`), you may import those. Everything
  else inside the module is off limits.
- You may import the public API of feature libraries (pure libraries below the server layer). For example, the tool
  provider protocol is part of the public API of the node types library.

For packages inside the source repository, these rules are enforced by import checks (`importlinter.rules.toml`,
`uv run poe imports`).

| Rule | Meaning |
| --- | --- |
| Link modules do not know each other | Links do not import each other |
| Feature modules do not know link modules | Feature modules keep working without links |
| Apps and feature libraries do not import link modules | Links are assembled only through entry points |
| Link modules see only the public ports of feature modules | Feature module code outside `<module>.ports` must not be imported |

The rules themselves are in [importlinter.rules.toml](../../importlinter.rules.toml) in the source repository. These
checks do not apply to plugins outside the repository, but if you follow the same rules, your plugin does not break
when the server packages change.

## Adding items to multi-provider ports

Many links do not create new ports. They add one item to a **multi-provider port** that a feature module has already
opened.

| Port (example) | What it adds |
| --- | --- |
| `runs.scopes` | Node services and tool providers per run |
| `definitions.checks` | One more pre-save check for definitions |
| `settings.scope_layers` | One more settings layer |
| `definitions.references` | Extracting references from definitions (shown as usage) |

The full list, and who collects each port, are the rows of the [port table](reference.md#ports) whose "Multiple"
column is `yes`. Each point is described on its area page ([Projects](projects.md), [Logs](logs.md),
[Specs (SDD)](sdd.md), and others).

The collecting side receives a list of providers, so when a link is turned off, only its item drops out of the list.

```python
>>> from agent_console_modkit import PortKey, assemble
>>> from agent_console_modkit.testing import fake_module
>>> NOTES, RUNS = PortKey("notes.reader"), PortKey("runs.reader")
>>> CHECKS = PortKey("definitions.checks", multi=True)
>>> notes = fake_module("mod-notes", provides=[NOTES])
>>> runs = fake_module("mod-runs", provides=[RUNS], optional=[CHECKS])
>>> link = fake_module("link-notes-runs", kind="link", requires=[NOTES, RUNS], provides=[CHECKS])
>>> other = fake_module("link-other-checks", kind="link", provides=[CHECKS])
>>> assemble([notes, runs, link, other]).ports(CHECKS)
['link-notes-runs/definitions.checks', 'link-other-checks/definitions.checks']
>>> without_notes = assemble([runs, link, other])
>>> [(r.id, r.state.value, r.missing) for r in without_notes.report]
[('link-notes-runs', 'unsatisfied', ('notes.reader',)), ('link-other-checks', 'active', ()), ('mod-runs', 'active', ())]
>>> without_notes.ports(CHECKS)
['link-other-checks/definitions.checks']

```

## Rules for links

- **Opt in**: a link being on must not, by itself, change how user data behaves. The example link gives the tool only
  to agents that have a notes resource attached.
- **Stay inside the space**: a project run reads only that project's space. If it cannot open it, report an error; do
  not fall back to another space.
- **Events under your own prefix, without content**: call results carry only status, counts, and correlation ids
  ([Contracts and events](contracts-events.md#plugin-owned-events)).
- **Start even when one side is missing**: if a required port is missing, only the link is `unsatisfied`. If the link's
  `build` raises, only that link is `failed`.

## Testing

Assemble with small double modules instead of the two feature modules. Each link package in the source repository
keeps its doubles in its `testing` module. The example link exposes a notes module double (`StaticNotesModule`). See
[Testing](testing.md#4-assembly-tests).

# agent-console-example-link

An example and writing guide for **a link module that connects two features**. It connects the notes module (`mod-example-notes`, the example
`agent-console-example-module`) and the runs module (`mod-runs`) so that agents in a run can read notes. It does not change the code of the server, the web app, or the two
feature modules.

| What | In this example | File |
| --- | --- | --- |
| Link descriptor | `kind="link"`, two required ports (`example_notes.reader`, `runs.reader`), provided port `runs.scopes` | `module.py` |
| Run scope (`run-scope`) | A `runs.scopes` entry: adds one provider to the node service `TOOL_PROVIDERS` for every run | `scope.py` |
| Tool provider (`agent-tool-provider`) | Gives agents that have the notes slot the tool `read_notes` + instructions, with the event `example_notes.read` per call | `provider.py` |
| Resource type | `example-notes` (slot `example_notes`): only agents it is attached to get the tool | `resource_type.py`, `data/resource_type.json` |
| Administrator options | `modules.options.link-example-notes-runs`: limit per read, tool name | `settings.py` |
| Text and defaults | Tool name, description, result line template, instructions, event type | `data/defaults.json` |
| Test stand-in | A small module that provides `example_notes.reader` without the notes module | `testing.py` |

Dependencies: the contract, the module kit, node types (`agent-console-nodes-core`, the tool provider protocol), resources, the runtime, and `pydantic`. **It does not import the two feature module
packages**: it declares again, in its own `ports.py`, only the port names and the shapes of the parts it uses. This package is not a uv
workspace member.

## How to build a link module

A link has the same shape as a server module (`descriptor` + `build`); the differences are the descriptor `kind="link"` and the **required ports**. When even one
required port is missing, only this link turns off as `unsatisfied`, and the server and the other modules start as usual.

```python
class NotesRunsLink:
    descriptor = ModuleDescriptor(
        id="link-example-notes-runs", version="0.1.0", kind="link",
        title="노트·실행 연동(예제)",
        provides=(RUN_SCOPES,),                    # runs.scopes (several providers)
        requires=(NOTES_READER, RUNS_READER),      # unsatisfied when either one is missing
        settings_schema=NotesRunsSettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings if isinstance(ctx.settings, NotesRunsSettings) else NotesRunsSettings()
        ctx.provide(RUN_SCOPES, NotesRunScope(lambda: ctx.port(NOTES_READER), slot=..., text=cfg.text(), ...))
        return ModuleParts()
```

A run scope entry is a single `scope_run(graph, services, *, project_id) -> result | None`. The `services` of the result are added to the node
services of that run. Here the link appends its own provider after the existing provider list (it does not overwrite it).

```python
def scope_run(self, graph, services, *, project_id):
    provider = NotesToolProvider(
        self._reader, slot=self.slot, text=self.text, id=..., project_id=project_id
    )
    existing = services.get(TOOL_PROVIDERS) or ()
    return RunScopeResult(services={TOOL_PROVIDERS: (*existing, provider)})
```

A tool provider is an `id` and a single `provide(ctx) -> ToolProvision`. The agent node calls it for each node.

Rules
1. **Opt-in**: when the bundle does not have its slot (the `contributes` of the resource type), return an empty `ToolProvision()`. Agents without the resource attached
   get neither tools nor instructions.
2. **Consuming slots**: put the slots you handled in `consumed_slots`. Then they are not passed to the backend, and no "slot the backend could not apply" warning appears.
   When the port to receive is missing, do not consume the slot (that warning informs the user).
3. **Only the run's space**: for a project run, read only that project's space. When it cannot be opened, return an error as the tool result and do not substitute
   another space. The run continues.
4. **Events with your own prefix, without content**: each call emits only `example_notes.read` (`status`, `count`, `tool_use_id`). Note content and
   exception messages are not included.
5. **Text is data**: tool names, descriptions, and instructions are in `data/defaults.json`; values to change are administrator options.

Assembling and using it without a server (test host + notes stand-in):

```python
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_example_link import MODULE_ID, RUN_SCOPES, module
>>> from agent_console_example_link.testing import StaticNote, StaticNotesModule, StaticNotesReader
>>> notes = StaticNotesModule(StaticNotesReader({None: [StaticNote("n1", "배포는 금요일")]}))
>>> assembly = assemble([notes, module], ModulesConfig())
>>> assembly.status(MODULE_ID).state.value, assembly.status(MODULE_ID).missing
('unsatisfied', ('runs.reader',))
>>> assembly = assemble([module], ModulesConfig())  # without the notes module too, both are reported missing
>>> sorted(assembly.status(MODULE_ID).missing)
['example_notes.reader', 'runs.reader']
>>> assembly.ports(RUN_SCOPES)
[]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

The assembly that includes the runs module is in `tests/test_assembly.py`, and how to put the provider into the engine directly is in `tests/test_engine.py`.

## Registration and settings

Two entry points in `pyproject.toml`: the link module (group `agent_console.server_modules`, name = module id) and the resource type (group
`agent_console.resource_types`, name = descriptor id).

```toml
[project.entry-points."agent_console.server_modules"]
link-example-notes-runs = "agent_console_example_link.module:module"

[project.entry-points."agent_console.resource_types"]
example-notes = "agent_console_example_link.resource_type:NotesResourceType"
```

Administrator options (the server settings file; when omitted, the package data defaults):

```yaml
modules:
  options:
    link-example-notes-runs:
      max_notes_per_call: 20   # limit on notes returned at once (empty = the notes module limit)
      tool_name: read_notes    # the tool name agents see (empty = the default name)
  # disabled: [link-example-notes-runs]   # turn off only this link
```

To give it to an agent, create a resource in the workspace and attach it to the agent (or a team or node). All settings are optional.

```yaml
# resources/team-notes.yaml
id: team-notes
type: example-notes
name: Team notes
config:
  limit: 10     # when the tool input has no count
  tag: meeting  # only notes with this tag
```

When it is attached at several layers (common, team, agent, node), each key uses the value of the closest layer.

## Install and remove

Install the notes module example as well (without it, this link is `unsatisfied`). On WSL (`/mnt/c`), add the environment variables.

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL only
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-module \
                                                  -e examples/extensions/agent-console-example-link   # install
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-link                         # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Install: `GET /api/v1/modules` lists `link-example-notes-runs` (`active`), and `GET /api/v1/resource-types` lists `example-notes`.
- The notes module or the runs module is missing or off: the server starts and only this link is `unsatisfied` (the missing ports are in `missing`). Runs of agents with a notes
  resource attached finish normally, with one "slot the backend could not apply" warning.
- Remove: the link and the resource type disappear. **What remains**: the `example-notes` resource files in the workspace (warned about as an unknown type),
  the `example_notes.read` events of past runs, and the setting `modules.options.link-example-notes-runs` (the server starts with a warning).

To use only the resource type without installing, put `agent_console_example_link.resource_type:register` in the setting `plugins.modules`.
When it is installed, do not add it (the entry point already registers it, so the same key would be registered twice and that plugin would fail).

## Test

The tests run without installing (pytest setting `pythonpath = ["src", "tests", "../agent-console-example-module/src"]`). The root
`uv run poe examples` runs mypy and pytest with this folder's settings. When only this folder is copied outside the repository, the neighboring notes module is missing,
so only the two integrated server tests that use the real notes module are skipped.

```bash
cd examples/extensions/agent-console-example-link
uv run --project ../../.. python -m pytest
```

- `tests/test_unit.py`: settings schema help, default data and renaming the tool, descriptor ports, the resource type (schema, check,
  `register`), merging layers, the scope appending after existing providers and returning None without the port.
- `tests/test_engine.py` (engine with the fake backend): an agent with the resource attached gets the tool and instructions and the slot is consumed; resource tag and count and
  the administrator limit; no resource → no tool or instructions; no port → one slot warning; a project run reads only its space; a missing space → a tool
  error and the run continues; no content in events.
- `tests/test_assembly.py` (test host + stand-ins): all on → reading; notes module off or runs module off → only this link is `unsatisfied`.
- `tests/test_server.py` (integrated server + the real notes module; the resource type comes from the entry point when installed, otherwise from `plugins.modules`):
  an agent reads a note written through REST and no plugin failed; a server without the notes module and a server without the runs
  module start, and only this link is `unsatisfied`.

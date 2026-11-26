# agent-console-example-module

An example and writing guide for **adding one new feature as a server module**. It does not change the code of the server, the web app, or other modules. Install it and
restart the server and the feature turns on; turn it off (`modules.disabled`) and only its routes return 404 while everything else keeps working.

The module `mod-example-notes` writes and reads short notes. It is small, but it shows everything a server module can have.

| What | In this example | File |
| --- | --- | --- |
| Descriptor | id, title, description, provided and optional ports, settings schema, settings compatibility declarations, lineage, web role | `module.py` |
| REST | `GET·POST /api/v1/example-notes`, `GET /api/v1/example-notes/{id}` (the route is an administrator option) | `routes.py` |
| Administrator options | `modules.options.mod-example-notes`: title, description, `x-ui` (the settings screen shows them as a read-only table) | `settings.py` |
| Command-line option | `--example-notes-max N` → `max_notes` (shown in `agent-console serve --help`) | `settings.py` |
| User settings section | `example_notes` in the workspace `settings.yaml`: applied from the next request, without a restart | `settings.py` |
| Definition kind contribution | Note templates (`example-note-template`): the definitions module registers them in the library store | `module.py` |
| Migration lineage | `example_notes`, `scopes=("app", "project")`: the same table in the app database and in project record databases | `storage.py`, `migrations/` |
| Provided port | `example_notes.reader`: other modules (links) read notes | `ports.py` |
| Optional ports | `workspace.settings`, `definitions.lookup`, `records.spaces`: without them, only that action returns 409 | `ports.py` |
| Standalone run | `python -m agent_console_example_module` (the same host code and security rules) | `standalone.py` |

Dependencies: the contract (`agent-console-contracts`), the module kit (`agent-console-modkit[host]`), storage (`agent-console-store`),
`fastapi`, `pydantic`, and `sqlalchemy`. It does not import other feature modules (it connects to them by port names only). This package is
not a uv workspace member. When it is not installed, it changes nothing.

## How to build a module

A module is two things: `descriptor` (data) and `build(ctx) -> ModuleParts` (assembly).

```python
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts, PortKey

NOTES_READER: PortKey[object] = PortKey("example_notes.reader", "노트 읽기")
RECORDS_SPACES: PortKey[object] = PortKey("records.spaces", "프로젝트 기록 DB")  # optional


class NotesModule:
    descriptor = ModuleDescriptor(
        id="mod-example-notes",
        version="0.1.0",
        kind="feature",
        title="노트(예제)",
        description="짧은 노트를 적고 읽는다",          # a sentence app users read
        provides=(NOTES_READER,),
        optional=(RECORDS_SPACES,),                     # without it, only that action returns 409
        settings_schema=NotesModuleSettings,            # validates modules.options.<id>
        settings_compat=SETTINGS_COMPAT,                # command-line options
        migrations=(BRANCH,),                           # the host applies them only when the module is on
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        options = ctx.settings or NotesModuleSettings()
        service = NotesService(options, NotesDeps(app_engine=lambda: ctx.database.engine, ...))
        ctx.provide(NOTES_READER, service)
        return ModuleParts(routers=[build_router(service, options.route)],
                           error_map={NoteNotFoundError: "not_found"})
```

Rules
1. **No global state**: create services and stores inside `build`, and receive outside dependencies (database, clock, other modules) from `ctx`.
   Assembling several apps from the same module object does not mix them up.
2. **Other modules only by port name**: do not import other module packages. Declare a `PortKey` with the same name in your own
   `ports.py`. When a required port (`requires`) is missing, the whole module is `unsatisfied`; when an optional port (`optional`) is missing,
   only that action does `raise ctx.unavailable(PORT)` (or `FeatureUnavailableError`) → 409 `feature_unavailable`.
3. **Do not change the contract**: keep your API shapes in your own package (`models.py`), use the contract's known codes for errors
   (`not_found`, `validation_failed`), and use your own prefix (`example_notes.`) for your issue codes.
4. **Do not write security code**: token, Host, and Origin checks and request size limits are done by the host.
5. **Values as settings and data**: routes, kind names, and limits are administrator options; how things are shown is a user settings section; defaults are package
   data (`data/defaults.json`). Give every administrator option field a `title`, `description`, and `x-ui` (`tier`, `when`)
   (the settings screen help lint checks them).
6. **Tables through lineages**: the revision files (`migrations/versions/`) define the table shape. When `scopes` contains `"project"`,
   the link that opens project record databases applies the same lineage to those files too (the code has no list of lineage names).

Assembling and using it without a server (test host = the module kit's `assemble`):

```python
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_example_module import NOTES_READER, NoteCreate, module
>>> assembly = assemble([module], ModulesConfig(options={"mod-example-notes": {"max_notes": 2}}))
>>> [(r.id, r.state.value) for r in assembly.report]
[('mod-example-notes', 'active')]
>>> notes = assembly.port(NOTES_READER)
>>> for text in ("하나", "둘", "셋"):
...     _ = notes.add(NoteCreate(text=text))
>>> [n.text for n in notes.list_notes()]
['셋', '둘']
>>> notes.list_notes("p1")
Traceback (most recent call last):
  ...
agent_console_modkit._errors.FeatureUnavailableError: 프로젝트 기록 연동이 꺼져 있어 프로젝트 노트를 쓸 수 없습니다

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

On a host without a database, app notes are kept in an in-memory SQLite (the same lineage is applied, with the server warning `example_notes.storage_memory`).

## Registration and settings

One entry point in `pyproject.toml`. Group = `agent_console_modkit.MODULES_GROUP` (`agent_console.server_modules`);
name = module id.

```toml
[project.entry-points."agent_console.server_modules"]
mod-example-notes = "agent_console_example_module.module:module"
```

Administrator options in the server settings file (`agent-console.yaml`). When omitted, the package data defaults apply.

```yaml
modules:
  options:
    mod-example-notes:
      route: /example-notes                  # REST route (after the API prefix)
      template_kind: example-note-template   # name of the contributed definition kind
      template_dir: example-note-templates   # note template folder inside the workspace
      user_section: example_notes            # name of the user settings section
      records_space_prefix: "project:"       # prefix of project record space names
      max_notes: 200                         # notes to keep per space (the oldest are deleted first when exceeded)
      max_text_chars: 4000                   # maximum characters per note
  # disabled: [mod-example-notes]            # turn it off: routes return 404, other modules are unchanged
```

Command line: `agent-console serve --example-notes-max 50` (takes precedence over the settings file). Turn it off with `--disable-module mod-example-notes`.

User settings (the workspace `settings.yaml`, edited by app users):

```yaml
example_notes:
  newest_first: true   # false = in the order written
  list_limit: 50       # number shown in the list at once
```

Wrong values are replaced with the defaults and reported through the warning `example_notes.settings_invalid` of `GET /api/v1/server-info`.

Note templates (definition kind contribution): `example-note-templates/<id>.yaml` in the workspace.

```yaml
kind: example-note-template
id: standup
name: Morning standup
category: meeting
text: "Done yesterday / Doing today / Blockers"
tags: [meeting]
```

`POST /api/v1/example-notes {"template": "standup"}` creates a note from the template's body and tags. When the definitions module is off,
only this request returns 409. With `?project=<project id>`, notes are written to and read from the record database of that project folder (when the project records link
is off, 409; it does not write to the app database instead).

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-module   # install
uv pip uninstall agent-console-example-module                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Install: `GET /api/v1/modules` lists `mod-example-notes` (`active`), and `agent-console serve --help` shows `--example-notes-max`.
- Turn off (while installed): the setting `modules.disabled` or `--disable-module`; the routes return 404 and the lineage is not applied.
- Remove: the module and its routes disappear. **The data remains**: the `example_notes` tables in the app database and the project record databases, the note template files
  in the workspace, and the settings section. To delete the tables too, roll back the lineage before removing (`SqliteDatabase.downgrade_branch(BRANCH)`).
  The server still starts when `modules.options.mod-example-notes` remains in the settings file (options of unknown modules give a warning).

Standalone run (without the integrated server, for development and reuse):

```bash
python -m agent_console_example_module --config standalone.yaml --port 0          # start
python -m agent_console_example_module --config standalone.yaml --port 0 --check  # check /health 200, then exit
```

`standalone.yaml` is the host settings (`workspace`, `state`, `security`, `modules`). App notes are in `<state>/example-notes.sqlite3`,
and user settings in `<workspace>/settings.yaml`. There are no definitions or projects features, so note templates and project notes return 409.

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The root `uv run poe examples` runs mypy and pytest with this folder's
settings. Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>` (`uv run poe wheels` in the repository), and then
`uv run pytest`.

```bash
cd examples/extensions/agent-console-example-module
uv run --project ../../.. python -m pytest
```

- `tests/test_service.py`: the service (writing, order, retention count, length, empty body), the user settings section (order and count, wrong values → defaults +
  a warning, the section name is an administrator option), note templates (no port → 409, body and tags filled in, missing template), project notes (no port →
  409, an empty list when there is no record database, separate from the app), applying, rolling back, and reapplying the lineage, revisions matching the table definitions, and the settings schema
  help (descriptions, `x-ui`).
- `tests/test_module.py`: assembling the module alone (REST, 404, 422, 409, 401 without a token, the lineage applied when on, the kind contribution and ports),
  no database → memory + a warning, the route option, off → 404, lineage not applied, the rest normal, wrong options failing only this module,
  the standalone `main` (local settings module, SQLite file), and `python -m … --check` (a real socket, `/health` 200).
- `tests/test_server.py`: the integrated server (all default modules) + this module: `--example-notes-max` reflected in the options view, the definitions
  module registering the contributed kind so note templates work, the user settings section, project registration → an `example_notes`
  table and notes in the project record database, off → 404 with other routes normal, and the option in `serve --help`.

Test your own module the same way: for unit tests, give the service a set of functions such as `NotesDeps`; for assembly, use
`agent_console_modkit.assemble` + `agent_console_modkit.host.create_host_app`; for integration, use
`agent_console_server.create_app(modules=[*installed_modules(), module])`.

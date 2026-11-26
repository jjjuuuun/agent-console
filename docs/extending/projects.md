# Projects

A project is one local folder and the space of configuration copies inside it. The points on this page fall into
three groups.

- Choosing folders: browse start locations and hidden names ([folder-browse-defaults](#folder-browse-defaults)), the
  operating system folder dialog ([folder-dialog-provider](#folder-dialog-provider))
- The copy space: which definition kinds go in ([portable-definition-kind](#portable-definition-kind)), the folder
  name and the `.gitignore` template ([project-space-layout](#project-space-layout)), path guarding
  ([path-field](#path-field))
- Moving definitions and running: extracting and rewriting references ([definition-references](#definition-references),
  [definition-reference-rewriter](#definition-reference-rewriter)), run scopes ([run-scope](#run-scope)), scoped
  settings layers ([settings-scope-layer](#settings-scope-layer))

Port points are provided by server modules or link modules. For their shape and assembly rules, see
[Server modules](modules.md#ports) and [Link modules](links.md#adding-items-to-multi-provider-ports).

## definition-reference-rewriter

**When to use**: when you copy definitions between spaces under a new name (for example, copying `coder` as `coder-2`
because the target space already has the same id), it fixes the other definitions in the copy set so they do not point
to the old id. If a new definition kind points to other definitions by id, the module that created the kind provides
this together with reference extraction ([definition-references](#definition-references)).

**Minimal shape**: one function, `rewrite(kind, document, renames) -> new_document`. `renames` maps
`(kind, old id) → new id`. For a kind it does not know, it returns the document unchanged. Provide it in the module's
`build` with `ctx.provide(DEFINITIONS_REWRITERS, rewrite)`.

```python
>>> from agent_console_projects import apply_renames
>>> def rewrite(kind, doc, renames):
...     if kind != "graph":
...         return doc
...     return {**doc, "uses": [renames.get(("agent", u), u) for u in doc.get("uses", [])]}
>>> docs = {("graph", "team"): {"id": "team", "uses": ["coder"]}, ("agent", "coder"): {"id": "coder"}}
>>> out = apply_renames(docs, {("agent", "coder"): "coder-2"}, rewrite_references=rewrite)
>>> sorted(out), out[("graph", "team")]["uses"]
([('agent', 'coder-2'), ('graph', 'team')], ['coder-2'])

```

**Rules**
- Do not modify the input document; return a new one. The projects module deep-copies the documents it receives, but
  other providers receive the same document.
- When there are several providers, they are applied one after another. Each provider changes only the kinds and
  fields it knows and leaves the rest as it is.
- Handle the same fields as reference extraction. If you extract but do not rewrite, a set copied under new names
  points to the old ids and is blocked by the pre-run check.

**Common mistakes**: changing the `id` field as well (the copying side already changes it), and removing references
whose names did not change.

**Turning off**: without any provider, copies under new names keep the references as they are.

<!-- extdocs:facts definition-reference-rewriter -->
- Registration: A server module provides the port `definitions.reference_rewriters` (symbol `agent_console_mod_projects.ports:DEFINITIONS_REWRITERS`, multiple: yes).
- Interface:
  - `agent_console_projects:RewriteReferences` — Reference rewriter `rewrite(kind, document, renames) -> new_document` (injected).
- Built-in implementations: —
- Examples:
  - snippet: Provide one reference rewriting function through a port
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## definition-references

**When to use**: so that copying a definition to a project, or checking it, also brings along the other definitions it
uses. Provide it when you create a new kind of definitions that point to each other, the way a team points to agents
and an agent points to resources.

**Minimal shape**: one function, `references(kind, document) -> [(kind, id), ...]`. For a kind it does not know, it
returns an empty list. The pure project rule `copy_plan` uses this function to build the reference closure (the items
to bring along) and warnings about cycles and missing references. In the server, provide it through a port.

**Rules**
- It must be a pure function. It looks only at the document, without reading the store (the copy plan calls it many
  times).
- Return references to definitions that do not exist as they are. The plan produces the missing reference warnings.
- When you register a new definition kind as a definition kind contribution, you can also give the same function to
  the contribution's `references` ([definition kind contribution](host.md#definition-kind-contribution)). The projects
  module combines both.

**Common mistakes**: returning empty values in the document (`""`, `None`) as references, and returning the same
reference several times (harmless, but the same item can show twice on the plan screen).

**Turning off**: without a provider, the copy plan copies only the chosen items and attaches the info issue
`project.references_unavailable`.

<!-- extdocs:facts definition-references -->
- Registration: A server module provides the port `definitions.references` (symbol `agent_console_mod_projects.ports:DEFINITIONS_REFERENCES`, multiple: yes).
- Interface:
  - `agent_console_mod_projects.ports:References` — ``definitions.references`` shape: the ``(kind, id)`` of the definitions one document uses.
- Built-in implementations: `link-definitions-teams`
- Examples:
  - reference: [packages/py/links/ac-link-definitions-teams](../../packages/py/links/ac-link-definitions-teams/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## folder-browse-defaults

**When to use**: to change the range of the in-app folder browser used when registering a project. The server
administrator changes the start locations (browsing never goes outside them). People who use the library directly can
also change the hidden names and the default start location rules per path flavor.

**Minimal shape**: the server reads only the administrator setting `modules.options.mod-projects.browse_roots` (a
list of absolute paths).

```yaml extdocs:validate=agent_console_mod_projects.settings:ProjectModuleSettings
browse_roots:
  - /srv/work
  - /srv/shared
```

When you use the library (`agent-console-local-folders`) directly, read a dictionary with the same shape as the
default data with `load_browse_defaults` and pass it as `defaults=` to `check_folder`, `list_dirs`, and
`default_roots`.

```python
>>> from agent_console_local_folders import MemoryFileSystem, list_dirs, load_browse_defaults
>>> defaults = load_browse_defaults({"hidden_names": ["node_modules"], "roots": {}})
>>> fs = MemoryFileSystem().add_dir("/srv/work/app").add_dir("/srv/work/node_modules")
>>> listing = list_dirs("/srv/work", fs=fs, defaults=defaults)
>>> [e.name for e in listing.entries], listing.hidden_count
(['app'], 1)

```

**Rules**
- Hidden names are case-insensitive. Names that start with a dot and items with the OS hidden attribute are hidden
  regardless of the data (the screen's "show hidden" option reveals them).
- A start location rule, per path flavor (`posix`, `windows`), is either a `path` template (`~` = home, `{item}` when
  `each` is present) or `parent` + `name_pattern`. Only folders that exist become start locations.
- When `browse_roots` is set, browsing and folder checks are limited to those folders (`folders.outside_roots` when
  outside).

**Common mistakes**: writing relative paths in `browse_roots` (only absolute paths have meaning), and writing paths in
hidden names (only a single folder name is compared).

**Turning off**: an empty `browse_roots` goes back to the default start locations such as the home folder and drives.
Server settings cannot change hidden names, and the package's default hidden name list is empty.

<!-- extdocs:facts folder-browse-defaults -->
- Registration: Uses the package data `data/browse_defaults.json`; the settings `mod-projects.browse_roots` override it.
- Interface:
  - `agent_console_local_folders:load_browse_defaults` — Browse defaults. Without `data`, the package default data (`data/browse_defaults.json`).
- Built-in implementations: —
- Examples:
  - snippet: Server administrator setting `mod-projects.browse_roots`
- Turning it off or removing it: Remove the settings `mod-projects.browse_roots` to go back to the package data defaults.
<!-- /extdocs:facts -->

## folder-dialog-provider

**When to use**: to change or add the folder dialog on the server computer that the folder selection button opens. In
most cases, adding one command as data is enough. Write a code provider only for dialogs that cannot be opened from
the command line (dialogs that need a library call).

**Adding with data**: write entries in the administrator setting
`modules.options.mod-projects.folder_dialog.providers`. The same id replaces a built-in entry, and `enabled: false`
removes it. New ids are tried before the built-in entries. The entry format (`platforms`, `requires`, `env_requires`,
`argv`, `env`, `cancel_exit_codes`) is in the [local folders package README](../../packages/py/features/ac-local-folders/README.md).

```yaml extdocs:validate=agent_console_mod_projects.settings:ProjectModuleSettings
folder_dialog:
  mode: auto
  include_default_providers: true
  providers:
    - id: my-picker
      platforms: [linux]
      requires: my-picker
      argv: [my-picker, {when: initial, args: ["--start", "{initial}"]}]
      cancel_exit_codes: [1]
    - {id: kdialog, enabled: false}
```

**Code providers**: an object with `id`, `available(environ) -> bool`, and
`pick(*, initial, title, timeout, cancel) -> str | None`. The entry point value is that object, or a class that
creates the object when called without arguments.

```python
>>> from agent_console_mod_projects import FolderDialogProvider
>>> class FixedPicker:
...     id = "fixed"
...     def available(self, environ):
...         return "DISPLAY" in environ
...     def pick(self, *, initial, title, timeout, cancel):
...         return None if cancel.is_set() else "/srv/work/app"
>>> isinstance(FixedPicker(), FolderDialogProvider)
True

```

```toml
[project.entry-points."agent_console.folder_dialogs"]
fixed = "my_package.picker:FixedPicker"
```

**Rules**
- All installed code providers are tried before the data commands. The first provider whose `available` is true is
  used.
- Do not insert user values (`initial`, `title`) into script strings. Pass them as separate arguments or environment
  variables. Data commands run without a shell.
- The projects module checks the chosen path again. The provider only returns the path: `None` for cancel, an
  exception for failure.
- The dialog opens only when the server is bound to a loopback address. Only one opens at a time.

**Common mistakes**: opening a window or running a command in `available` (the check must be light), and not watching
`cancel`, so the dialog stays open after the request is gone.

**Turning off**: with `folder_dialog.mode: off`, only the in-app browser is used. A code provider drops out when you
uninstall its package. When no dialog is available, the screen hides the button and shows only the browser.

<!-- extdocs:facts folder-dialog-provider -->
- Registration: Register in the entry point group `agent_console.folder_dialogs` (constant `agent_console_mod_projects:FOLDER_DIALOGS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_mod_projects:FolderDialogProvider` — Folder picker dialog provider (entry point ``agent_console.folder_dialogs``).
- Settings: `mod-projects.folder_dialog.providers`, `mod-projects.folder_dialog.include_default_providers`
- Built-in implementations: —
- Examples:
  - reference: [packages/py/features/ac-local-folders](../../packages/py/features/ac-local-folders/README.md) — Command table data `data/folder_dialogs.json`
  - snippet: Code provider
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## path-field

**When to use**: when the settings schema of a node type, backend, or resource kind has a property that takes a local
path, add the `x-path` annotation to that property. In a project run, the path guard reports when this value points
outside the project folder. The path guard does not look at field names, only at this annotation.

**Minimal shape**: put `x_path()` (a folder) or `x_path("file")` (a file) in `json_schema_extra` of the Pydantic
field. On a list field, each item is a path.

```python
>>> from pydantic import BaseModel, Field
>>> from agent_console_contracts import x_path
>>> from agent_console_projects import outside_paths
>>> class ToolOptions(BaseModel):
...     cwd: str = Field(default=".", json_schema_extra=x_path())
...     extra_files: list[str] = Field(default_factory=list, json_schema_extra=x_path("file"))
>>> schema = ToolOptions.model_json_schema()
>>> schema["properties"]["cwd"]["x-path"], schema["properties"]["extra_files"]["x-path"]
('directory', 'file')
>>> value = {"cwd": "../other", "extra_files": ["notes.md"]}
>>> [p.resolved for p in outside_paths(value, schema, "/srv/work/app", flavor="posix")]
['/srv/work/other']

```

**Rules**
- The only values are `directory` and `file`. For any other value, `x_path` raises `ValueError`.
- Relative paths are resolved against the project folder. To use it with other extension keys, merge them as in
  `{**x_ui(...), **x_path()}`.

**Common mistakes**: leaving the annotation off a field that takes a path (its value passes without a check), and
annotating URLs or identifiers that are not paths.

**Turning off**: when you remove the annotation, the field is no longer path-checked.

<!-- extdocs:facts path-field -->
- Registration: Add the schema annotation key `x-path`.
- Interface:
  - `agent_console_contracts:x_path` — Pydantic `Field(json_schema_extra=...)`에 넣을 `{"x-path": kind}`를 만든다.
- Built-in implementations: —
- Examples:
  - snippet: Add the `x-path` annotation to a schema property
- Turning it off or removing it: Remove the annotation to go back to the default behavior.
<!-- /extdocs:facts -->

## portable-definition-kind

**When to use**: when you register a new definition kind, decide whether it can go into the copy space of a project
folder (`portable`) and whether it can live in the app library (`library`). For example, documents that are separate
per project are `library=False`, and something like the app registry is `portable=False`.

**Minimal shape**: two fields of `DefinitionKind`. To add the kind to the server, see
[definition kind contribution](host.md#definition-kind-contribution).

```python
>>> from agent_console_store import DefinitionKind
>>> notes = DefinitionKind(name="note", directory="notes", portable=True, library=False)
>>> notes.is_portable, notes.library
(True, False)
>>> DefinitionKind(name="app-settings", singleton_file="app.yaml").is_portable
False

```

**Rules**
- Singleton kinds (`singleton_file`) cannot be moved, whatever the `portable` value.
- A `library=False` kind looks like an unknown kind to the library store (a request finds nothing). Keep it only in
  project and standalone spaces.
- If you put a kind that cannot be moved into a copy plan, only that item drops out, with a warning.

**Common mistakes**: making a kind that points to other definitions `portable` without providing reference extraction
(the references break in the space it is copied to).

**Turning off**: when you omit the fields, `portable=True` and `library=True`.

<!-- extdocs:facts portable-definition-kind -->
- Registration: Put a value in the descriptor field `DefinitionKind.portable`.
- Interface:
  - `agent_console_store:DefinitionKind` — Storage rules for one definition kind.
- Built-in implementations: —
- Examples:
  - snippet: DefinitionKind(portable=..., library=...)
- Turning it off or removing it: Leave the field empty to use the default.
<!-- /extdocs:facts -->

## project-space-layout

**When to use**: to change the name of the configuration folder the app creates inside a project folder, or the
default lines of the `.gitignore` created at registration. This is for sharing the same folder with an app that uses
a configuration folder of a different name, or for an ignore list that follows in-house rules.

**Minimal shape**: in the server, just the administrator setting `modules.options.mod-projects.config_dir`.

```yaml extdocs:validate=agent_console_mod_projects.settings:ProjectModuleSettings
config_dir: .team-console
records_file: records.sqlite3
```

When you use the library (`agent-console-project-space`) directly, change them with
`open_space(folder, config_dir=...)` and `init_space(..., gitignore_template=...)`. The default template is package
data.

```python
>>> from agent_console_project_space import default_gitignore_template
>>> [line for line in default_gitignore_template().splitlines() if line.startswith("/")][:2]
['/.state/', '/memory.sqlite3']

```

**Rules**
- The lines the app manages in the template are the lines that start with `/`. They point only directly under the
  configuration folder so they do not collide with definition names.
- The template has the name placeholders `{state_dir}`, `{memory_file}`, `{records_file}`, and `{sessions_dir}`.
  Registration, the missing line check, and the append action fill them with that space's layout values (the settings
  `records_file` and `sessions_dir`), so when you change a name, the git ignore lines follow. Templates you pass
  yourself can use the same placeholders (`render_gitignore_template`).
- At registration, `project.yaml` and `.gitignore` are created only when they do not exist. Existing files are not
  changed, and lines missing compared with the template are reported as the info `project.gitignore_outdated`. They
  are appended at the end only when the user chooses to append them.
- The configuration folder name must be a relative name that does not leave the folder (`..`, absolute paths, and
  backslashes are rejected).

**Common mistakes**: changing `config_dir` when projects are already registered. The old configuration folder is no
longer read, so the definitions and records of those projects disappear from view (they are not deleted).

**Turning off**: remove the setting to go back to the default name.

<!-- extdocs:facts project-space-layout -->
- Registration: Uses the package data `data/gitignore.template`; the settings `mod-projects.config_dir` override it.
- Interface:
  - `agent_console_project_space:default_gitignore_template` — The default `.gitignore` template text shipped in the package (UTF-8, ends with a newline).
- Built-in implementations: —
- Examples:
  - snippet: Server administrator setting `mod-projects.config_dir`
- Turning it off or removing it: Remove the settings `mod-projects.config_dir` to go back to the package data defaults.
<!-- /extdocs:facts -->

## run-scope

**When to use**: to add node services, warnings, and a definition source to just that run, each time a run starts.
Examples: for a project run, using the definitions and records of that project's space; when memory or the wiki is
on, adding agent tool providers. Link modules that connect two features usually provide it.

**Minimal shape**: an object with `scope_run(graph, services, *, project_id) -> RunScope | None`. To also decide the
definition source, add the optional method `run_definitions(project_id, graph_id)`. For a full example, see the
[link example](../../examples/extensions/agent-console-example-link/README.md).

```python
from agent_console_mod_runs.ports import RunScope
from agent_console_nodes_core import TOOL_PROVIDERS


class NotesScope:
    def scope_run(self, graph, services, *, project_id):
        if not uses_notes(graph):          # opt in: leave runs it does not apply to unchanged
            return None
        existing = services.get(TOOL_PROVIDERS) or ()
        return RunScope(services={TOOL_PROVIDERS: (*existing, NotesTools())})
```

**Rules**
- It is called at every run start (a normal run, a resume, a chat turn), before checks and preparation. It is not
  called for child runs, which inherit the parent's services.
- When several providers give the same service key, the later provider wins. For list services (tool providers and
  so on), add to the list you received and return it.
- `warnings` do not block the run and are recorded as `log.warning`. To block the run, return `errors` (the run is not
  created).
- If it raises, only that provider is skipped and the run continues without its scope.

**Common mistakes**: adding services to every run (it creates behavior the user did not turn on), and opening another
project space instead (if the space cannot be opened, report an error).

**Turning off**: when you turn off the link module that provides it, only that scope drops out.

<!-- extdocs:facts run-scope -->
- Registration: A server module provides the port `runs.scopes` (symbol `agent_console_mod_runs.ports:RUN_SCOPES`, multiple: yes).
- Interface:
  - `agent_console_mod_runs.ports:RunScoper` — ``runs.scopes`` entry: run scope.
  - `agent_console_mod_runs.ports:RunScopeLike` — Shape of the ``RunScoper.scope_run`` result (``RunScope`` satisfies it).
  - `agent_console_mod_runs.ports:RunDefinitionsScoper` — **Optional** method of a ``runs.scopes`` entry: where a Run looks up definitions.
  - `agent_console_mod_runs.ports:RunChildScoper` — **Optional** method of a ``runs.scopes`` entry: checks child Runs (nested teams).
  - `agent_console_mod_runs.ports:RunProjectScoper` — **Optional** method of a ``runs.scopes`` entry: whether it handles the project scope.
- Built-in implementations: `link-memory-runs`, `link-projects-runs`, `link-wiki-runs`
- Examples:
  - package: [examples/extensions/agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
  - reference: [packages/py/links/ac-link-projects-runs](../../packages/py/links/ac-link-projects-runs/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## settings-scope-layer

**When to use**: to provide, for each scope id (for example, a project id), a settings layer to insert into the
effective settings. When the effective settings are requested with `?project=<id>`, this layer goes directly below
the common settings. The built-in implementation is the link that applies the settings written in a project folder's
manifest to runs and screens.

**Minimal shape**: an object with `scope_layers(scope_id) -> result`. The result has two attributes, `layers` (the
list of layers) and `warnings` (a list of issues). For an unknown scope id, return empty layers. The reference
implementation is the [projects and runs link](../../packages/py/links/ac-link-projects-runs/README.md).

**Rules**
- The consumer of this port does not know what scopes mean. The provider interprets the id.
- If a layer cannot be read, return a warning and empty layers instead of raising. The effective settings are still
  computed from the common settings.
- Layers from several providers are stacked in provider order.

**Common mistakes**: putting secret values into a layer as they are (the effective settings are visible on screen;
use `secret://` references for secrets).

**Turning off**: without a provider, `?project=` is ignored and only the common settings are used.

<!-- extdocs:facts settings-scope-layer -->
- Registration: A server module provides the port `settings.scope_layers` (symbol `agent_console_link_definitions_teams.ports:SCOPE_LAYERS`, multiple: yes).
- Interface:
  - `agent_console_link_definitions_teams.ports:ScopeLayersSource` — ``settings.scope_layers`` shape: scope id → settings layer (scope meaning unknown here).
- Built-in implementations: `link-projects-runs`
- Examples:
  - reference: [packages/py/links/ac-link-projects-runs](../../packages/py/links/ac-link-projects-runs/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

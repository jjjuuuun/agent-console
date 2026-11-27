# Plugin basics

Every "one more of the same kind" comes in the same way. A package announces its implementation with an entry point,
and the server reads it at startup and registers it in the registry of each extension point. Built-in implementations
are registered the same way, so a plugin is treated exactly like a built-in implementation. This page collects the
rules that apply to every point. What differs per point (interfaces, descriptor fields) is on the area pages.

## Entry points

```toml
[project.entry-points."agent_console.edge_types"]
"acme.relay" = "acme_console_edges:RelayEdge"
```

- **Group** = extension point. The group name equals a public constant of the package that defines it (for example,
  `agent_console_runtime.EDGE_TYPES_GROUP`). The full list and the built-in implementations are in the
  [entry point group table](reference.md#entry-point-groups).
- **Name** = registration id. Data (the `type` and `kind` of a team, the `op` of a condition, a source id in settings)
  finds the implementation by this name. If the point has a descriptor, make the descriptor `id` the same.
- **Value** = `module:attribute`. The attribute is one of these:
  - A class: the server creates an instance without arguments. This is the most common shape.
  - An object that already exists (a module-level instance).
  - A factory without arguments: some points take "a function without arguments that returns the function that builds
    the real implementation" (for example, the wiki search index takes a function that returns
    `(folder, options) -> index`). The area page of the point describes that shape.
- Do not read files, the network, or environment variables in the constructor. Take outside values from settings
  (`config`, options) or from the context the point passes in. That way tests can swap in fakes, and loading stays
  fast.

## Names and duplicates

- When a group has two entries with the same name, only one is registered. Among entries with the same name, the one
  that comes first in value (module path) order is used, and the later one is reported as `failed` (a duplicate, with
  the source that registered first in `error`). Install order does not matter.
- Built-in implementations also come in through entry points, so the same rule applies. If you use the same name as a
  built-in implementation, either the built-in implementation or your plugin drops out as `failed`, depending on value
  order. To replace a built-in implementation, do not reuse its name: register a new name and choose that name in the
  data (`plugins.disabled` turns things off by name, so with the same name both are turned off).
- That is why names carry your own prefix (`acme.relay`). Names without a prefix are for built-in implementations.
- Different groups can use the same name without affecting each other (registration is per group; turning on and off,
  described below, applies to all groups).
- Explicit module plugins (`plugins.modules`) are called after all entry points are read. If one registers a name that
  already exists, that plugin is `failed` (a duplicate) and the earlier entry stays. Overwrite with
  `register(name, implementation, replace=True)` only when you mean to replace it. If the overwritten name is then
  dropped by `plugins.disabled`, the original entry comes back.
- Points that keep different versions under the same name (such as `type_version` of node types) are explained on that
  point's page. Entries with different versions stay together, and a lookup without a version gets the highest
  version.

## Load time and failures

- Entry points are read **once, when the server starts**. Restart the server after installing, removing, or changing
  the version of a package.
- A load failure does not stop the server. For an import error, a missing attribute, a failed point check (a required
  method or descriptor is missing), or a duplicate, only that entry drops out and the result is reported.
- The results appear per entry in `plugins` of `GET /api/v1/server-info`.

| `status` | Meaning |
| --- | --- |
| `loaded` | Registered |
| `failed` | Could not be read. The reason (exception name and message) is in `error` |
| `skipped` | Not read because it is in `plugins.disabled` or not in `plugins.enabled` |
| `disabled` | Registered by an explicit module plugin, but removed because it is in `plugins.disabled` or not in `plugins.enabled` |

`skipped` and `disabled` are not errors, so `error` is empty. Which setting caused it is recorded in `reason` (for
example, `설정 plugins.disabled에 있음`) and in the server log.

```bash
curl -s http://127.0.0.1:8765/api/v1/server-info      # plugins: [{name, group, loaded, status, reason, error}]
```

## Turning plugins on and off

In the server settings file (or environment variables):

```yaml
plugins:
  disabled: [acme.relay] # names to turn off (all groups). Everything else is read as usual
  enabled: null          # null = everything installed. A list reads only those names (all groups)
  modules: []            # plugin modules that are not installed, as "package.module:attribute" (below)
```

- **To turn off just one, put its name in `plugins.disabled`.** Other plugins and the built-in implementations are
  read as usual. The name is the entry point name (registration id), the same as `name` in `plugins` of
  `server-info`.
- `plugins.enabled` is **an allow list that applies to all groups together**. Built-in implementations also come in
  through entry points, so when you write the list you must include the names of the built-in implementations too.
  Use it when you want to pick only what you use.
- When you set both, `plugins.disabled` is removed from `plugins.enabled` (the deny list wins).
- Neither list looks at groups. If another group has the same name, it is turned off too.
- If `plugins.disabled` contains a name that is not installed, the server still starts and adds a
  `plugins.unknown_disabled` warning to `warnings` of `server-info` (to catch typos). If the name is an installed distribution name
  (`my-console-ops`), the warning (`plugins.disabled_distribution`) shows the entry point names of that distribution. If it is a server module id
  (`mod-…`), the warning (`plugins.disabled_module_id`) says to turn it off with `modules.disabled` and also shows the entry point names of the same
  distribution.
- The same rules apply to entries registered by `plugins.modules` plugins. The name is the registered key, and an entry
  that is turned off appears with `group` `plugins.modules` and `status` `disabled` (entry point plugins show
  `skipped`).
- Environment variables: `AGENT_CONSOLE_PLUGINS_DISABLED` and `AGENT_CONSOLE_PLUGINS_ENABLED` (comma-separated),
  `AGENT_CONSOLE_PLUGIN_MODULES`.
- To try a plugin without installing it, put `"package.module:attribute"` in `plugins.modules`. The attribute is an
  object with a `register(registries)` method, or a function of the same shape, and it registers directly in the named
  registries. Registration goes through the same checks as entry points. The module must be on the server's import
  path.
- Server modules (feature units) are not plugins. Turn them on and off with the module settings `modules.enabled` and
  `modules.disabled` ([Server modules](modules.md#turning-on-and-off)).

## Data left after removal

When you remove or turn off a plugin, the user data that uses its name (nodes and edges of a team, conditions,
resources, source entries in settings) is **not deleted**. Instead:

- The pre-save check and the list checks report issues. The code and severity are fixed per point and written on the
  area page. For example, the node type `unknown_node_type` and the edge type `unknown_edge_type` are errors (that team
  is blocked by the pre-run check), and the condition operator `condition.unknown_operator` is a warning (the run goes
  ahead and only that condition item is false).
- An unknown name affects only that part. Other teams and other plugins keep working.
- When you install the plugin again, everything works again without changing the data.

Follow the same convention when you write a plugin. If your plugin takes ids of other extensions as data, report
unknown ids with a warning code under your own prefix instead of raising, and skip only that part.

## Settings schema

Most points put a `config_schema` (JSON Schema) on the descriptor. The web draws the settings form from this schema,
so a plugin does not write web code. Add the following to each field.

| Key | What |
| --- | --- |
| `title` | A short label |
| `description` | One sentence on what it does and why you would change it. Do not use internal names |
| `x-ui.tier` | `basic` (shown at the top) or `advanced` (collapsed) |
| `x-ui.when` | One sentence on when to change it (required for `basic` fields) |
| `x-ui.example` | An example value to fill in when the user selects an empty field |
| `x-ui.unit` | The unit (seconds, items, MB) |

For a Pydantic model, put `x_ui()` in `json_schema_extra`. You can check the result yourself with
`lint_schema_help`. The top-level `title` and `description` of the schema appear as the form header, and Pydantic
fills them with the class name and the docstring. Give the title with `model_config = ConfigDict(title="...")` and
keep the docstring as one sentence the user reads (move code documentation such as `Attributes:` into each
`Field(title=..., description=...)`).

```python
>>> from pydantic import BaseModel, Field
>>> from agent_console_contracts import x_ui
>>> from agent_console_contracts.schema_help import lint_schema_help
>>> class RelayConfig(BaseModel):
...     prefix: str = Field(
...         default="",
...         title="머리말",
...         description="다음 노드에 넘길 때 앞에 붙일 글입니다.",
...         json_schema_extra=x_ui(
...             tier="basic", example="[검토 요청] ", when="넘기는 글을 구분하고 싶을 때 바꾸세요."
...         ),
...     )
>>> lint_schema_help(RelayConfig.model_json_schema())
[]
>>> sorted(i.rule for i in lint_schema_help({"type": "object", "properties": {"n": {"type": "integer"}}}))
['missing-description', 'missing-example', 'missing-tier', 'missing-title']

```

If you use an `x-ui` widget name that the web does not know, structured values switch to JSON editing with a note.
If you really need a new widget, see [Web](web.md).

## Secrets

- Do not write secrets (keys, tokens) as values in settings. Users write a `secret://name` reference, and the server
  finds the value in environment variables (or a secret provider plugin) and passes it on. A reference is resolved only
  when the whole string is `secret://name`.
- Mark secret fields in the schema with `SecretStr` (or `"x-secret": true`). They are masked on screens, in settings
  views, and in responses.
- Do not put a secret you received into logs, events, error messages, or exception strings. The engine masks values it
  resolved in records, but it cannot mask values a plugin got another way or changed (encoded, partly truncated).
- If you need a new secret source (a file, a keychain, and so on), use the secret provider point
  ([Execution backends](backends.md)).

## Choosing an extension point

| What you want to do | Where to look |
| --- | --- |
| The full point table (registration kind, number of built-in implementations, example kinds) | [Extension point reference](reference.md#extension-points) |
| Install an example package to try it | [Example index](../../examples/extensions/README.md) |
| Build your first one | [Get started](getting-started.md) |

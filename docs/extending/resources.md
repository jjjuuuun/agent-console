# Resources

Resources are the materials you attach to agents (instructions, skills, MCP servers, tool permissions, files, hooks,
and so on). A resource kind defines which slot of the run bundle (the instructions slot, the MCP server slot, and so
on) the material goes into and with what value. Slot names are strings, not a fixed list in code, and the execution
backend declares which slots it accepts.

There are two ways to create a new kind.

| Way | When | Install |
| --- | --- | --- |
| Declarative YAML (no code) | When it is enough to put the content or settings values into a template and place it in a slot | One file in the workspace folder |
| Plugin (code) | When computing or checking values needs code (reading files, several slots, conditional contributions) | A package + an entry point |

## resource-type

**When to use**: when you want to attach a material to agents that the built-in kinds cannot hold. Examples are
prompt snippets, shared team notes, and in-house tool settings.

### Declarative kinds

Put one YAML file in the workspace's `resource-types/` folder (the server setting
`modules.options.mod-resources.declarative_dir`). The server reads this folder at startup, so restart the server
after adding or removing a file.

```yaml extdocs:validate=agent_console_resources:DeclarativeTypeSpec
id: acme.prompt-snippet
title: 프롬프트 조각
description: 마크다운 본문 하나를 지침에 제목과 함께 넣습니다.
config_schema:
  type: object
  properties:
    tone: {type: string, enum: [formal, casual], title: 말투}
content: {media_types: [text/markdown], editor: markdown}
contributes:
  - slot: instructions
    template: "## {title}\n{content}"
```

- `contributes[]` has one entry per slot. Give either `template` (a string template) or `value` (a structured value
  whose strings are templates too), not both. With `raw: true`, the value is merged as it is without wrapping (when
  object slots are merged with `combine: merge`).
- Template variables: `id`, `name`, `description`, `title` (the name by default), `content` (the body), plus the
  top-level keys of `config` (on a name clash, config wins).
- With `content`, it is a document kind, and the screen shows a body editor.
- A format error (including unknown keys) or an invalid `config_schema` is reported as a load failure of that file
  only (`plugins` of `GET /api/v1/server-info`). If a plugin kind with the same id already exists, the declarative file
  is the one that fails.
- For an installable example, see the [declarative resource kind example](../../examples/resource-types/README.md).

### Plugin kinds

**Minimal shape**: `descriptor` (`ResourceTypeDescriptor`), `validate(resource) -> list[Issue]`, and
`contribute(resource, content, ctx) -> list[Contribution]`. For a kind that only needs `config_schema` checks,
subclass `SchemaResourceType` and write only `contribute`.

- `contribute` returns slot names and values (`Contribution(slot, value)`). You can give a `fallback` contribution to
  use when the execution backend does not accept the slot. If the fallback slot is not accepted either, the bundle
  preview and validation report `resource.slot_unsupported`.
- Fill in the descriptor fields `contributes` (the slots it uses), `combine` (how to merge when several items go into
  the same slot), and `slot_key` (the settings field that tells items apart within the same slot) accurately. The
  screens and the preview explain the kind with these values.
- `contribute` is called while a run is being prepared. Do not call the network or do slow work. Do not put settings
  values in error text (the server masks values in issues, but it cannot mask sentences you built yourself).
- If the work does not end with one resource kind but connects another feature (notes, memory, wiki) to runs, a link
  module holds the kind and a tool provider together. The [link example](../../examples/extensions/agent-console-example-link/README.md)
  has that shape.

### Common mistakes

- Naming a slot with a name the built-in backends do not accept and not looking at the preview warnings. The accepted
  slots are in the backend capabilities (`resource_slots`) of `GET /api/v1/backends`.
- Leaving the prefix off the `id` of a declarative file so that it collides with a built-in kind (`instruction`,
  `skill`, and so on).

### Data left after removal

Resource files created with that kind are not deleted. Validation reports `resource.unknown_type` as a **warning**
(it does not block saving, because you may install the kind again later), and the resource does not contribute to the
run bundle. Agents with that resource attached still run with their other resources.

<!-- extdocs:facts resource-type -->
- Registration: Register in the entry point group `agent_console.resource_types` (constant `agent_console_resources:RESOURCE_TYPES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_resources:ResourceType` — Resource type. Register via entry point `agent_console.resource_types` or declarative data.
  - `agent_console_resources:SchemaResourceType` — Base for resource types that check config against `descriptor.config_schema`.
  - `agent_console_resources:DeclarativeTypeSpec` — Format of a declarative kind file.
- Built-in implementations: `file (agent-console-resources-core)`, `hook (agent-console-resources-core)`, `instruction (agent-console-resources-core)`, `mcp-server (agent-console-resources-core)`, `memory (agent-console-link-memory-runs)`, `rule (agent-console-resources-core)`, `skill (agent-console-resources-core)`, `tool-permission (agent-console-resources-core)`, `wiki (agent-console-link-wiki-runs)`
- Examples:
  - package: [examples/extensions/agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
  - reference: [examples/resource-types](../../examples/resource-types/README.md) — Declarative type with no code: `prompt-snippet.yaml` (the workspace `resource-types` folder)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

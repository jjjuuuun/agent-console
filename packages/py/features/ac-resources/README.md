# agent-console-resources

Resource kind registration and **run bundle (ResourceBundle) assembly**. No kind names or slot names are in this package.

- **Kind registration**: the entry point `agent_console.resource_types`, an explicit module list, or **declarative data**
  (`<workspace>/resource-types/*.yaml`, no code). Registration key = the `type` of the resource definition.
- **Attachment merging**: lists of `ResourceAttachment` across layers (common → team → agent → node …, caller data) are
  merged with the `keyed_attachments` strategy registered in the `ac-settings` strategy table (`add`, `replace`, `remove`, provenance per element).
- **Bundle assembly**: for each remaining attachment, the kind's `validate` and `contribute` (pure functions) are called, and each slot is combined with the kind's
  `combine` strategy (default `append`) into `ResourceBundle{slots, sources}`.
- It does no file writes, secret resolution, or networking. Secrets go into the bundle as `secret://name` references.
- Problems are returned as `Issue` instead of exceptions (missing resources or kinds, settings errors, slots not accepted, and so on).

## Installation

```bash
uv sync --all-packages                        # inside the workspace
uv pip install ./packages/py/features/ac-resources     # standalone
```

## Minimal usage

```python
>>> from agent_console_contracts import Resource, ResourceAttachment
>>> from agent_console_resources import (
...     AttachmentLayer,
...     InMemoryResources,
...     compose_bundle,
...     declarative_type_from_data,
...     load_resource_types,
...     new_resource_types,
... )

>>> types = new_resource_types()
>>> _ = load_resource_types(types)  # installed plugins (for example ac-resources-core); returns a list of reports
>>> fragment = declarative_type_from_data(  # a declarative kind (usually load_declarative_types(folder, types))
...     {
...         "id": "prompt-fragment",
...         "title": "프롬프트 조각",
...         "config_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
...         "slot_key": "title",
...         "contributes": [{"slot": "instructions", "template": "## {title}\n{content}"}],
...     }
... )
>>> _ = types.register(fragment.descriptor.id, fragment)

>>> resources = InMemoryResources(  # usually the store implements ResourceLookup
...     [
...         Resource(
...             id="tip",
...             type="prompt-fragment",
...             name="팁",
...             config={"title": "팁"},
...             content={"file": "content.md"},
...         )
...     ],
...     contents={"tip": "짧게 답한다."},
... )
>>> result = compose_bundle(
...     [
...         AttachmentLayer("team", [ResourceAttachment(ref="tip")], label="팀 구성"),
...         AttachmentLayer("node", [ResourceAttachment(ref="nope")], label="이 팀의 노드"),
...     ],
...     types=types,
...     resources=resources,
...     accepted_slots=["instructions", "files"],  # backend capabilities.resource_slots
... )
>>> result.bundle.slots
{'instructions': ['## 팁\n짧게 답한다.']}
>>> [(s.ref, s.layer) for s in result.bundle.sources["instructions"]]
[('tip', 'team')]
>>> [i.code for i in result.issues]  # warnings and errors (the attachment is skipped and work continues)
['resource.not_found']

```

### With settings layer merging (computing effective settings)

The schema annotation of the contract `AgentSettings.resources` is `x-merge: keyed_attachments`. When you compute effective settings
with the same strategy table, attachments are merged by the same rules, and you can build the bundle directly from the result.

```python
from agent_console_resources import (
    attachment_slot_key,
    build_bundle,
    placed_from_resolved,
    resource_strategies,
)
from agent_console_settings import resolve_layers

table = resource_strategies(slot_key_of=attachment_slot_key(types, resources))
resolved = resolve_layers(layers, schema=agent_settings_schema, strategies=table)
bundle = build_bundle(
    placed_from_resolved(resolved), types=types, resources=resources, strategies=table
)
```

To add to an existing strategy table, use `register_resource_strategies(table, slot_key_of=...)`.

## Attachment modes

| Mode | Behavior |
| --- | --- |
| `add` (default) | Appends. If the same resource with the same override comes again, the bundle uses it only once (`resource.duplicate`, info). |
| `replace` | Replaces in place an upper-layer attachment with the same resource id **or** the same slot key (the kind's `slot_key` config value, for example the `title` of an instruction). If there is none, it adds and reports `resource.replace_unmatched` (info). |
| `remove` | Removes an upper-layer attachment with the same resource id. If there is none, `resource.remove_unmatched` (info). |

`config_override` is shallowly overlaid on the resource config (`effective_resource`).

## Writing resource kinds

### 1) Plugin (code)

```python
from agent_console_contracts import ResourceTypeDescriptor
from agent_console_resources import Contribution, SchemaResourceType


class GreetingType(SchemaResourceType):
    descriptor = ResourceTypeDescriptor(
        id="greeting",
        title="인사",
        contributes=["instructions"],
        config_schema={"type": "object", "properties": {"who": {"type": "string"}}},
    )

    def contribute(self, resource, content, ctx):
        return [Contribution("instructions", [f"{resource.config.get('who', '')}에게 인사한다."])]
```

```toml
[project.entry-points."agent_console.resource_types"]
greeting = "my_plugin:GreetingType"
```

`validate` is checked by `SchemaResourceType` against `config_schema` (additional checks go in `extra_issues`).
With `combine` of `Contribution(slot, value, combine=None, fallback=None)`, only this contribution can use a different strategy (for example `prepend`).

- **Fallback slot** (`fallback`): the contribution to use instead when the execution backend does not accept `slot` (not in `accepted_slots`).
  Example: for backends that cannot take path-conditional instructions (`rules`), plain instructions (`instructions`). Switching reports info `resource.slot_fallback`.
- **Multi-file bodies**: kinds whose descriptor has `content.multi_file=true` receive `{path: bytes}` (`ContentFiles`) as the `content` of `contribute`.
  The lookup object must have the optional capability `FileContentLookup.read_files(resource)`
  (`InMemoryResources`, `MaskedResources`, ac-nodes-core `FunctionResources(find, read, read_files)`). Otherwise
  `None` with a `resource.content_unreadable` warning.
- **Notes on slots not accepted**: when `slot_notes={slot: note}` (backend `capabilities.slot_notes`) is passed to `build_bundle` or `compose_bundle`,
  it is attached to `details.reason` and the message of the `resource.slot_unsupported` warning.

### 2) Declarative data (no code)

```yaml
# <workspace>/resource-types/prompt-fragment.yaml
id: prompt-fragment
title: 프롬프트 조각
config_schema: {type: object, properties: {title: {type: string}}}
content: {media_types: [text/markdown], editor: markdown}
slot_key: title
contributes:
  - slot: instructions
    template: "## {title}
{content}"          # one result string is one slot item
  - slot: mcp_servers                          # a structured value (each string substituted) → one item
    value: {name: "{title}", type: stdio, command: echo}
  - slot: env_map                              # raw: as is, unwrapped (object slot + merge)
    value: {A: "{title}"}
    raw: true
    combine: merge
```

Substitution is safe substitution (only `{name}`, no attribute or index access, unknown names left as is). Variables are
`id`, `name`, `description`, `title` (the default name), `content` + the top-level config keys.

## Secret field marker `x-secret`

In the config schema, put `x-secret: true` (constant `SECRET_SCHEMA_KEY`) at locations that hold secret values. The screen uses this structural
hint to draw a secret input field (masked, choose a `secret://` reference); it never guesses from description text.
Plugin kinds and declarative kinds work the same. `SchemaResourceType.validate` **rejects plain text (values that are not references) at these locations
as a general rule** (`find_schema_plain_secrets` → `resource.plain_secret` error, with a message that has no value). Declarative
kinds do not need a separate `pattern`. If a kind already reports the same location through `extra_issues`, it is reported only once.

```yaml
# <workspace>/resource-types/api-token.yaml
id: api-token
title: API 토큰
config_schema:
  type: object
  properties:
    token: {type: string, x-secret: true}   # resource.plain_secret if plain text
contributes:
  - slot: env_map
    value: {API_TOKEN: "{token}"}
    raw: true
    combine: merge
```

## Kind validation (`validate`, `extra_issues`) contract

Whoever writes a resource kind (plugin or declarative) must follow this. Before saving (REST `POST/PUT /resources`, version revert),
the server calls these checks through `validate_resource` and does not save if there are error issues.

- **Do not put input values in messages.** Write only what is wrong (the rule), never the value.
- **Set `path` precisely.** The JSON Pointer of the problem value relative to config (for example `/env/API_KEY`; `~` and `/` become `~0` and `~1`).
  The server rewrites it in the response relative to the document (`/config/env/API_KEY`, or `/resources/0/config_override/env/API_KEY` for attachment overrides),
  and the screen uses it to attach the error to the field. Attachment checks (`validate_attachment`) also use this path to tell whether the override caused it.
- `scrub_issue_values` is only a safety net: it removes **only the value that `path` points to** from the message. If there is no path, it points elsewhere,
  or the value is short (fewer than 3 characters), values left in the message cannot be removed.
- Do not raise (raising becomes error `resource.type_failed` and blocks saving). Pure functions (no files, networking, or secret resolution).

## Public API

| Name | Description |
| --- | --- |
| `ResourceType`(Protocol) | `descriptor`, `validate(resource) -> list[Issue]`, `contribute(resource, content, ctx) -> list[Contribution]` |
| `Contribution(slot, value, combine=None)`, `ContributeContext(attachment, layer)` | Contribution and context |
| `ResourceLookup`(Protocol), `InMemoryResources` | `get_resource(ref)`, `read_content(resource)` |
| `FileContentLookup` (Protocol, optional capability), `Content`, `ContentFiles` | `read_files(resource) -> {path: bytes} \| None` (multi-file body kinds) |
| `SchemaResourceType` | Base for config_schema checks (`extra_issues` hook) |
| `RESOURCE_TYPES_GROUP`, `new_resource_types()`, `load_resource_types(registry, *, enabled, modules, entry_points)`, `as_resource_type`, `list_descriptors` | Registration |
| `load_declarative_types(dir, registry, *, read, files)`, `declarative_type_from_data(data)`, `DeclarativeResourceType`, `DeclarativeTypeSpec`, `ContributionSpec`, `DeclarativeTypeError` | Declarative kinds |
| `ATTACHMENT_STRATEGY` (`keyed_attachments`), `PREPEND_STRATEGY`, `keyed_attachments_strategy(slot_key_of)`, `attachment_slot_key(types, resources)`, `prepend`, `register_resource_strategies`, `resource_strategies` | Merge strategies |
| `compose_bundle(layers, *, types, resources, accepted_slots, strategies, slot_notes) -> ComposedBundle`, `SLOT_UNSUPPORTED`, `SLOT_FALLBACK`, `resolve_attachments`, `build_bundle`, `placed_from_resolved`, `unsupported_slots`, `AttachmentLayer`, `PlacedAttachment` | Bundles |
| `effective_resource`, `content_text`, `is_secret_ref`, `find_plain_secrets`, `find_schema_plain_secrets`, `PLAIN_SECRET`, `SECRET_REF_PREFIX`, `SECRET_REF_PATTERN`, `SECRET_SCHEMA_KEY` (`x-secret`), `validate_config`, `check_config_schema`, `render_template`, `fill_value` | Helpers |
| `validate_attachment(attachment, *, types, resources, path="", override_path=None, ref_path=None, secret_rules=None) -> list[Issue]` | Runs the kind check on the resource config with the attachment `config_override` shallowly overlaid. Only issues the override caused (issues under overridden keys always), path = `<override_path>/...`. A missing resource gives a warning (at the ref location) plus error `resource.override_secret_suspected` for each value caught by the secret suspicion rules (`SecretRules` of `ac-secret-rules`, default = the default rules); a missing kind gives a warning (at the ref location) |
| `mask_plain_secrets(value, schema)`, `mask_resource(resource, types)`, `mask_attachment(attachment, *, types, resources)`, `MaskedResources(lookup, types)`, `SECRET_MASK` | A safety net for display: values at `x-secret` locations that are not `secret://` become `***` (follows `properties`, `additionalProperties`, `items`, `allOf/anyOf/oneOf`; does not follow `$ref`) |
| `validate_resource(resource, types) -> list[Issue]`, `scrub_issue_values(issues, config)` | Pre-save check: calls the kind's `validate` (unknown kind = warning `resource.unknown_type`, exception = error `resource.type_failed`) and replaces the config values that issue `path`s point to with `***` in messages. The server refuses to save on error issues |

## Issue codes

`resource.not_found`, `resource.unknown_type` (warning, attachment skipped), `resource.invalid_config`,
`resource.invalid_type_schema` (error, skipped), `resource.type_failed` (kind implementation exception, error),
`resource.content_missing`·`resource.content_unreadable`, `resource.duplicate`,
`resource.replace_unmatched`·`resource.remove_unmatched`(info), `resource.slot_unsupported`(warning, `details.reason` =
backend note), `resource.slot_fallback` (info, `details.slot`, `fallback`),
`resource.merge.*` (strategy problems). `details` contains `resource`, `layer`, `slot`, and so on.

**Issue messages never contain input values** (to prevent secret leaks). Instead of jsonschema's
`err.message` (which contains the input value), `validate_config` builds messages only from the kind of check and the schema's expectations (type, list of allowed values, whether a pattern exists,
required key names, and so on), and reports the location as `Issue.path` (JSON Pointer). Exceptions from kind implementations also
leave only the exception type name in messages.

## Dependencies

| What | Why | Alternatives |
| --- | --- | --- |
| `jsonschema` | config_schema checks (already used in the workspace) | Hand-written checks (incomplete) |
| `ruamel.yaml` | Reads declarative kind YAML (the same library as definition storage) | PyYAML |
| `pydantic` | Format checks of declarative kinds, contract models | Hand-written checks |
| `ac-secret-rules` (internal) | Secret suspicion for attachment overrides without a resource (the same rules as the server and import, with injected user rules) | A module inside the contracts package (the earlier design, which could not take user rules) |
| `ac-text-template` (internal) | Safe substitution for declarative kinds (`render_template`, `fill_value`, re-exported by this package under the same names) | A copy inside this package (the same rules as the SDD input templates would live in two places) |

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-resources`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-resources
```

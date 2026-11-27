# Declarative resource kind example

An example that adds a resource kind (extension point `resource-type`) with **one YAML file** and no code.
There is no package to install: put the file in the workspace folder and the kind appears; delete it and the kind goes away.

| File | Kind id | What it does |
| --- | --- | --- |
| `prompt-snippet.yaml` | `prompt-snippet` | Puts one Markdown body into the instructions slot (`instructions`) under a `## <name>` heading. Setting `tone` (enum) |

## Minimal data

```yaml
id: prompt-snippet
title: 프롬프트 조각
config_schema: {type: object, properties: {tone: {type: string, enum: [formal, casual]}}}
content: {media_types: [text/markdown], editor: markdown}   # document kind (body editor)
contributes:
  - slot: instructions
    template: "## {title}\n{content}"
```

- `contributes[].slot`: the run bundle slot name (a string, not a fixed list). If the backend doesn't accept the slot, the
  bundle preview and validation report `resource.slot_unsupported`.
- Template variables: `id`, `name`, `description`, `title` (default = the name), `content` (the body), plus the top-level
  config keys.
- Full format: the `_declarative` module docs of the `agent_console_resources` package (`DeclarativeTypeSpec`, `value`,
  `raw`, `combine`, and so on).
- The example data is user data, so its title and description are in Korean (the E2E scenario looks for that title).
  Write your own kinds in any language.

## Register and remove

```bash
cp examples/resource-types/prompt-snippet.yaml <workspace>/resource-types/   # register
rm <workspace>/resource-types/prompt-snippet.yaml                            # remove
```

Declarative kinds are read when the server starts, so **restart the server**.
- Register: `GET /api/v1/resource-types` lists `prompt-snippet` (`declarative: true`), and the kind list under
  "New resource" on the resources screen shows the kind's title.
- Remove: it disappears from the list. Resources made with this kind are not deleted; validation reports them with a
  `resource.unknown_type` warning.
- If the same id collides with a plugin kind, the declarative file is reported as a load failure (`LoadReport` `failed`)
  and is not registered.

## Testing

`tests/test_resource_type_examples.py` reads every `*.yaml` in this folder with the same loader the server uses
(`load_declarative_types`) and checks what each kind contributes.
The root `uv run poe check` collects it. The "resource kind" scenario of E2E `08-extension` copies this file into the
workspace.

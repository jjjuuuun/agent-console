# agent-console-example-transfer

An example and writing guide that exports definitions to **a single JSON file** and imports them again from the same file (a pair of the extension points
"export formats" and "import sources"). No engine, server, or web code changes. Once installed, `example-json` appears in the export format list and
the import source list, and it disappears when removed.

Format `example-json`
- **Export**: puts the selected definitions (+ the definitions used with them, such as the agents and resources of a team) into one file (`agent-console-bundle.json`).
  Definitions are stored as they are, and bodies are stored as `text` when they are text and as `base64` when they are binary. Multi-file bodies (catalog `files`) go into
  `files`, and single-file bodies (catalog `content`, for kinds whose document body field points to one file) go into `content`.
  It works for every definition kind.
- **Import**: reads the file with the same name in the project folder and shows its items as candidates. The original file is only read.
- **The format name, field names, and file name are option data** (defaults in `data/defaults.json`). Change them with administrator settings.
- **Secret values never go into the file**: secret references (`secret://name`) are stored as references, and values suspected to be plain text are masked by the export
  service's final check (warning `export.secret_redacted`, location only). On import, suspected plain-text values are masked as well and get
  `import.secret_suspected` (location only).
- Dependencies: the contract (`agent-console-contracts`), the export library (`agent-console-exports`), the import library
  (`agent-console-imports`), `agent-console-secret-rules`, and `pydantic`. It does not import any server module.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## How to build a format and a source

An export format follows `agent_console_exports.Exporter` (`descriptor`, a pure `plan(items, catalog, options) -> ExportOutput`), and
an import source follows `agent_console_imports.ImportSource` (`descriptor`, a read-only `scan() -> ScanResult`).
What you register is a **factory**: export = `(administrator options) -> format`, import = `(ImportSourceContext) -> list of sources`.

A full round trip with only the two libraries, without a server (in-memory catalog → file → in-memory store):

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import (
...     ExportSelection, ExportWriteRequest, ImportRequest, ImportSelection,
... )
>>> from agent_console_exports import ExportRoot, ExportService, FolderWriter
>>> from agent_console_exports.testing import MemoryCatalog
>>> from agent_console_imports import ImportService, ImportSourceContext
>>> from agent_console_imports.testing import MemoryDefinitionWriter
>>> from agent_console_example_transfer import (
...     FORMAT_ID, json_bundle_exporter, json_bundle_sources,
... )

>>> tmp = tempfile.TemporaryDirectory()
>>> out = Path(tmp.name)  # an export root the administrator allowed
>>> catalog = MemoryCatalog().add("agent", {"id": "writer", "name": "작성자", "system_prompt": "짧게 쓴다."})
>>> exports = ExportService(
...     {FORMAT_ID: json_bundle_exporter({})}, catalog, writer=FolderWriter([ExportRoot("out", out)])
... )
>>> written = exports.write(ExportWriteRequest(
...     exporter=FORMAT_ID, items=[ExportSelection(kind="agent", id="writer")], root="out", subdir="proj",
... ))
>>> [(f.path, f.action) for f in written.files]
[('agent-console-bundle.json', 'create')]

>>> (source,) = json_bundle_sources(ImportSourceContext(project_dir=out / "proj"))
>>> store = MemoryDefinitionWriter()  # in a real setup, the definition store
>>> imports = ImportService([source], store)
>>> [(c.kind, c.suggested_id, c.name) for c in imports.preview(FORMAT_ID).candidates]
[('agent', 'writer', '작성자')]
>>> result = imports.apply(ImportRequest(source=FORMAT_ID, items=[ImportSelection(candidate_id="agent:writer")]))
>>> [(i.target_id, i.action) for i in result.items]
[('writer', 'created')]
>>> store.documents[("agent", "writer")]["system_prompt"]
'짧게 쓴다.'
>>> tmp.cleanup()

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Rules
1. **`plan` is pure**: it only reads the catalog and returns the file contents it builds. Writing (archive files, allowed folders) is done by
   `ExportService`, so rejecting path escapes, links, and protected locations, and handling conflicts, are not reimplemented for every format.
2. **Formats do not need to handle secrets themselves**: the service checks the output of every format at the end and masks suspected plain-text values.
   Formats do not resolve secret references into values.
3. **Sources only read the originals**: files are opened without following links (`O_NOFOLLOW`), and paths that resolve outside the source folder are not read
   (`import.skipped_link`). A missing file gives an empty result.
4. **Wrong files and items become warnings**: instead of raising, leave warnings (`example_transfer.*`, location only) and offer only the valid items as candidates.
5. **Format id = entry point name = descriptor id**: when they differ, the export loader warns and skips it.
6. **Read bodies through the two paths the catalog provides**: multi-file bodies with `catalog.files(kind, id)`, single-file bodies with
   `catalog.content(kind, id)`. The kind decides which one applies, so the format does not need to know the kind. On import, the same two values are passed as
   `ImportItem.files` and `ImportItem.content`.

## Registration

Two entry point tables in `pyproject.toml`. Name = format id. The value is a factory function.

```toml
[project.entry-points."agent_console.exporters"]
"example-json" = "agent_console_example_transfer:json_bundle_exporter"

[project.entry-points."agent_console.import_sources"]
"example-json" = "agent_console_example_transfer:json_bundle_sources"
```

At server startup, the host plugin loaders of the export and import server modules read these groups. Import sources are created only for requests with
a project folder (`ImportSourceContext.project_dir`). Other places, such as the home folder, are not read.

To use it without installing, list the registration function in the server setting `plugins.modules` (both factories go into the same registries):

```yaml
plugins:
  modules:
    - agent_console_example_transfer:register
```

When it is installed, do not add it. The entry point already registers `example-json`, so the same key would be registered twice and that plugin would
remain `failed`.

## Settings example

The format settings apply the administrator options over the defaults (`data/defaults.json`). **The export and import options must match** for a round trip.

```yaml
modules:
  options:
    mod-exports:
      options:
        example-json:
          file_name: team-bundle.json
          format_name: my-team-bundle
          fields: {items: things}     # field names are overridden one by one
          drop_fields: [project]      # top-level fields left out on export
    mod-imports:
      options:
        example-json:
          file_name: team-bundle.json
          format_name: my-team-bundle
          fields: {items: things}
```

| Option | Default | Meaning |
| --- | --- | --- |
| `file_name` | `agent-console-bundle.json` | The file name to export = the file to look for in the project folder on import (a relative path; `..` is not allowed) |
| `format_name`, `format_version` | `agent-console-example-bundle`, `1` | The format marker in the file (when different, nothing is imported, `example_transfer.unknown_format`) |
| `fields` | `format`, `version`, `definitions`, `kind`, `id`, `document`, `files`, `content`, `text`, `base64` | Field names in the file (rejected when they collide at the same level) |
| `name_field`, `type_field` | `name`, `type` | Definition fields used as the name and resource type in the import preview |
| `drop_fields` | none | Top-level fields left out of definitions on export |
| `max_file_bytes` | 10MiB | Maximum size read on import |
| Request option `include_dependencies` | `true` | Include the definitions used together (per export request; the screen form is `config_schema`) |

When the administrator options are wrong (unknown keys, absolute paths, colliding field names), the loader leaves a warning and only this format or source is left out.
The locations are `modules.options.mod-exports.options.<format id>` for the export module and `modules.options.mod-imports.options.<source factory name>` for the import module.

## Install and remove

Run these from the repository root. On WSL (`/mnt/c`), add the environment variables.

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL only
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-transfer   # install
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-transfer                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Install: `example-json` appears in the export format list and the import source list.
- Remove: it disappears from the lists. Files already exported and definitions already imported remain (imported definitions are ordinary definitions, unrelated to this package).
  Leftover administrator options are simply unused; they are not errors.
- Keep it installed but not loaded: remove `example-json` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest
with this folder's settings (`uv run poe examples`). Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>`
(`uv run poe wheels` in the repository), and then `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-transfer
uv run --project ../../.. python -m pytest
```

- `tests/test_round_trip.py`: agents and resources (text and binary bodies) in a real definition store (file workspace) → export to an allowed folder →
  **import into an empty workspace → the same definitions and the same bodies**; importing again gives new names (the original file unchanged); secret references
  stay as they are, and plain-text values are in neither the file nor the imported definitions. Kinds with a single-file body round-trip with their bodies too.
- `tests/test_agent_console_example_transfer.py`: the entry point declaration, loading with the library loaders, wrong options leaving out only that format,
  field and format name options, text and binary bodies (multi-file and single-file), warnings for wrong files and items, warnings for missing dependencies, rejection of links and paths outside the folder,
  and the size limit.
- `tests/test_server.py`: the integrated server (registered through `plugins.modules` when not installed, and only through the entry point when installed). When only one agent of
  registered project A is selected and exported through REST into the folder of project B, the resources that agent uses (text and binary bodies) are also
  found in the space of A and included; importing in B gives the same definitions and the same bodies, secret references as they are, and the original file unchanged.

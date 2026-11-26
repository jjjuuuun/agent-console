# Import and export

Export definitions (agents, teams, resources, and so on) to outside formats, and import definition candidates from
outside folders. The built-in implementations use the Claude Code project settings folder format (export
`claude-dir`, import `claude`), and other formats are implementations registered in the same groups. The two points
are independent of each other. You can build only an exporter or only an import source. To round-trip one format, put
both in one package and use the same options ([example](../../examples/extensions/agent-console-example-transfer/README.md)).

Rules for both:

- **Raw data is read-only.** Import sources only read outside folders. The same goes for the user's real tool settings
  folders.
- **The service does the writing.** An export format only returns file contents and does not write them. The service
  writes only to an allowed folder the user chose and checks the paths (paths that leave the folder or go to protected
  locations are rejected).
- **Secrets do not move.** Secret references (`secret://name`) stay references. Values that look like plain-text
  secrets are masked by the export service's final check (`export.secret_redacted`, location only), and imports also
  mask them and attach `import.secret_suspected` (location only). Formats do not need to mask anything themselves, but
  if a format changes a value (encodes it, truncates part of it), the check cannot recognize it.
- Format and source options are administrator settings: `modules.options.mod-exports.options.<format id>` for export
  and `modules.options.mod-imports.options.<source factory name>` for import. If the options are wrong, only that
  format or source drops out, with a warning.

## exporter

**When to use**: when you want to export definitions to a format other tools read (another agent CLI's settings
folder, a bundle file for sharing with a team, documents).

**Minimal shape**: the entry point points to a **factory** `(administrator options) -> Exporter`. An `Exporter` has
`descriptor` (`ExporterDescriptor`: `id`, `title`, and optionally `config_schema` (request options) and `kinds` (the
definition kinds it can export)) and `plan(items, catalog, options) -> ExportOutput`. `ExportOutput` is a list of
files (relative path + content) and warnings.

**Rules**

- `plan` is **pure**. It only reads definitions through `catalog` and does not touch files or the network. The same
  input gives the same output, so the preview and the real write give the same result.
- Read bodies through the two paths of `catalog`: multi-file bodies with `files(kind, id)` (path → content), and
  single-file bodies (kinds whose body field points to one file) with `content(kind, id)`. The kind decides which one
  applies, so a format reads both and includes whatever exists.
- Emit only relative paths. If you emit `..` or absolute paths, the service rejects the whole request.
- Whether to include related definitions (the agents and resources a team references) comes from the request
  options.
- Do not drop what the format cannot hold (settings the format has no field for); report it as a warning. If the
  export must stop, emit an error warning and the service rejects the request.

**Common mistakes**: hard-coding format names, file names, or field names. If you take them from option data
(package defaults + administrator options), other teams can use the same package with their own names.

**Data left after removal**: the format disappears from the format list, and requests that choose it return 404
`not_found`. Files already exported stay. Leftover administrator options are simply unused, not an error.

<!-- extdocs:facts exporter -->
- Registration: Register in the entry point group `agent_console.exporters` (constant `agent_console_exports:EXPORTERS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_exports:Exporter` — Export format. `plan` is **pure**: it reads the catalog and never writes files.
  - `agent_console_exports:ExporterFactory` — Server administrator options (`modules.options.mod-exports.options.<format>`) → format.
  - `agent_console_exports:ExportOutput` — Output a format produced (file contents + warnings). `ExportService` does the writing.
- Built-in implementations: `claude-dir (agent-console-exports)`
- Examples:
  - package: [examples/extensions/agent-console-example-transfer](../../examples/extensions/agent-console-example-transfer/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## import-source

**When to use**: when you want to import settings made by other tools (agents, instructions, skills, MCP servers) as
definitions of this console. Examples are another agent CLI's settings folder and a bundle file a team shared.

**Minimal shape**: the entry point points to a **factory** `(ImportSourceContext) -> list of sources`. The context
holds the user's home, the project folder, the administrator options, and the secret suspicion rules. One source
(`ImportSource`) has `descriptor` (`ImportSourceDescriptor`: `id`, `title`, and optionally `path` and `available`) and
`scan() -> ScanResult`. Each item of the result (`ImportItem`) is a candidate for the screen plus the definition
document (+ body) to save.

**Rules**

- `scan` only reads the raw data. It does not save the result. The service saves only the items the user chose as
  definitions.
- When the folder does not exist or the format marker differs, report it with `available = false` or an empty result
  instead of raising. Other sources still show.
- Decide where to read from the context (home, project folder) and the options. Do not hard-code paths.
- A factory can return several sources (the user folder and the project folder as separate sources).
- Imported definitions are ordinary definitions of this console. They are not tied to the source package.

**Common mistakes**: letting one unreadable file fail the whole `scan`. Leave out only that item with a warning and
show the rest.

**Data left after removal**: the source disappears from the source list. Definitions already imported stay (they are
ordinary definitions unrelated to the source). The raw files were never touched, so they stay as they are.

<!-- extdocs:facts import-source -->
- Registration: Register in the entry point group `agent_console.import_sources` (constant `agent_console_imports:IMPORT_SOURCES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_imports:ImportSource` — Import source (for example the user's `~/.claude`). **Only reads the originals.**
  - `agent_console_imports:ImportSourceFactory` — Build sources from environment values (target of entry point `agent_console.import_sources`).
  - `agent_console_imports:ImportItem` — One importable item: a candidate for the screen + the document to write (+ content).
- Built-in implementations: `claude (agent-console-imports)`
- Examples:
  - package: [examples/extensions/agent-console-example-transfer](../../examples/extensions/agent-console-example-transfer/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

# i18n

Checks that server text reaching the screen has a translation in some package message catalog (`poe i18n-check`) and adds the missing entries as empty values (`poe i18n-extract`). It is a repository tool and is not shipped. It runs in the workspace venv (`agent-console-i18n`, `agent-console-server` with its dev dependency `httpx`, `ruamel.yaml`).

Targets, exclusions, server seeds and rule severities live in `i18n.yaml`. To use the tool in another repository, change that file (`--root`, `--config`).

## Commands

| poe task | Direct | What it does | In `poe check` |
| --- | --- | --- | --- |
| `i18n-check` | `python scripts/i18n/i18n_tool.py check [--package NAME ...] [--strict] [--list] [--by-package] [--no-server] [--quiet]` | Runs S1-S3 below and prints totals per language and per group (`groups` in `i18n.yaml`). `--package` takes a folder or distribution name glob and keeps only findings that package owns. `--strict` treats every finding as an error (use it to confirm a package is done). `--no-server` skips the server crawl of S1; the static sources of S1 (`static`) are still read | yes (`--quiet`) |
| `i18n-extract` | `python scripts/i18n/i18n_tool.py extract --lang CODE [--package NAME ...] [--dry-run] [--no-server]` | Adds every `missing_text` / `missing_code` finding for `CODE` as an empty value to the owning package's `src/<import>/locales/<CODE>.json`. Existing keys and values are left alone. If the package has no `agent_console.message_catalogs` entry point, one is added to its `pyproject.toml` (run `uv sync --all-packages` afterwards so the server sees it) | no |
| `i18n-test` | `pytest -q -c scripts/i18n/pytest.ini scripts/i18n` | The tool's own mypy (strict) and tests (two fake packages, fake server) | yes |

Exit codes: 0 pass (warnings only), 1 an error-severity rule fired, 2 configuration or input error.

Typical translation loop for one package:

```sh
uv run poe i18n-extract --lang en --package ac-mod-runs
uv run poe i18n-extract --lang ko --package ac-mod-runs
# fill the empty values in src/<import>/locales/{en,ko}.json
uv run poe i18n-check --package ac-mod-runs --strict --list
```

## Checks

- **S1 server text.** Assembles the server with every installed module (empty workspace in a temporary folder, `CLAUDE_CONFIG_DIR` pointed at an empty folder, the folders in `server.dirs` created first, then the data in `server.seeds` created with ASCII names and the fake backend), reads every OpenAPI GET route and collects strings that contain source-language characters (`source_pattern`). Path variables come from `server.params` (fixed `values`, or `from` a GET route with a `select` path such as `/profiles/*/id`); routes without values are listed as skipped. A route that declares a query variable listed in `server.query_params` is read once more per value (`?name=value`), for text that only appears in a project space. The `message` of an issue-shaped object (`issue.code` and `issue.message` are strings) is not collected here: it is translated by code (S2). Each string must have a non-empty value in the `text` section of some catalog for every language other than `source_language`.
  S1 also reads **static sources** that the web translates with the server catalogs but that no GET response shows (`static`, read without a server, so also with `--no-server`): the contract JSON Schema document (`static.schemas`: the models the web draws, named in `models` or found in web sources by the `discover` pattern, plus every definition they reach through `$ref`) and values in package data files (`static.data`: `files` and `select` paths). A data source with `pointer_slots: true` reads templates whose placeholders are JSON pointers (`{/data/hookName}`, `{/output|count}`) in the form the source sends in `text_templates` (`{hookName}`, `{output_count}`: the last pointer segment, `_count`/`_keys` for a mode; a template whose placeholders would share a name is kept as written and reported). It is used for the log classifier's default event title and summary templates, which no crawl response shows because the crawl server has no session logs. Python sources (`static.python`) collect the strings in given keyword arguments of given calls and in given dictionary keys (for example the event titles that log sources and classifiers build in code, `LogEventDraft(title=...)`); string constants on both sides of a conditional or `or` count, and an f-string is collected with `{…}` for its values so it becomes a `dynamic_text` finding. Their findings name the origin `schema:<model>`, `data:<file>` or `python:<file>:<line>`. Schema and data sources are walked with the same key rules: `texts.skip_keys` values are data and are not collected (schema `default`, `const`, `enum`, `examples`), except the keys listed under a parent in `texts.keep_keys_in` (the string `example` inside `x-ui`, which the web shows as input hint text); keys directly inside a `texts.name_maps` key (`properties`, `$defs` and so on) are property names, so a property called `default` is still walked.
- **S2 codes.** Codes are taken from package sources by AST: string constants in classes whose name matches `codes.class_pattern` (`ErrorCodes`, `KnownIssueCodes` and the per-package `*Codes` classes), `code=` arguments (literal, `Class.ATTR` or a module constant) and `{"code": ..., "message": ...}` dictionaries; plus codes seen in S1 responses. Every code must have a non-empty value in the `codes` section of some catalog for every language in `languages`.
- **S3 placeholders.** Within a package, a code template must use the same placeholders in every language, and a placeholder must be a key of that code's `details`. Known `details` keys come from `details={...}` dictionary literals next to `code=` in the source and from issues seen in responses (intersection over all sites; sites with unknown keys are ignored).

The owner of a missing string is the package whose source or data file contains it literally (docstrings are matched after `inspect.cleandoc`, the way Pydantic builds descriptions, and by their first line, which some tables use as a summary). When several packages contain it, `texts.prefer_owners` decides, then name order. The owner of a code is the package that defines it, otherwise the first package that uses it.

## Rules

| Rule | Meaning |
| --- | --- |
| `missing_text` | S1 string with no translation; the owner is known (`extract` adds it) |
| `untranslated_text` | S1 string whose catalog value is still empty |
| `dynamic_text` | S1 string built from values (matches an f-string or a `{name}` template in the owner): give it a code with `details`, make it a fixed string, or send the source template + values in the response `text_templates` (config `texts.templates_key`: an object with that table is read as its templates, nested ones included, and the fields it covers are not collected; `extract` adds the templates as `text` keys) |
| `unowned_text` | S1 string not found in any target source (built at runtime, or from outside the targets) |
| `missing_code` / `untranslated_code` | S2 code with no message / an empty message in a language |
| `unowned_code` | Code seen in a response but not found in any target source |
| `stale_code` | A catalog has a code that no target source produces |
| `placeholder_mismatch` / `unknown_placeholder` | S3 |
| `catalog_unregistered` | `locales/` exists but no `agent_console.message_catalogs` entry point points to the import package |
| `catalog_invalid` | A catalog file cannot be read (see `agent_console_i18n.read_catalog`) |

Severities are set per rule in `i18n.yaml` `severity`. While the catalogs are still being filled, the missing/untranslated/dynamic/unowned rules are warnings; switch them to `error` when the bundled languages are complete.

## Configuration (`i18n.yaml`)

| Key | Meaning |
| --- | --- |
| `targets` | Package folder globs (relative to the repository root). The folder name is the package name and the catalog entry point name |
| `groups` | Summary rows: name and package folder globs (first match wins) |
| `source_language`, `source_pattern` | Language of server source text and a regular expression that finds its characters |
| `languages` | Bundled languages that must be complete. `codes` is checked for all, `text` for all but `source_language` |
| `sources` | Globs (relative to the package folder) for Python and data files, and exclusions. `locales/` is always skipped |
| `codes` | Code shape, code class name pattern and codes to ignore |
| `texts` | `exclude` strings to ignore, `skip_keys` response keys not to descend into (data values), `keep_keys_in` keys collected anyway directly under a parent key (`{x-ui: [example]}`), `name_maps` keys whose children are names rather than data keys (`properties`, `patternProperties`, `$defs`, ...), `prefer_owners` owner preference, `templates_key` source template table |
| `static` | S1 sources read without a server. `schemas`: list of `{document, defs, models, discover: {files, exclude, pattern}}` (a JSON Schema file, its definitions key, model names, and a regular expression with one group that finds model names in web sources). `data`: list of `{files, select, pointer_slots}` (package data file globs and `/a/*/b` paths; no `select` = the whole file; `pointer_slots` turns `{/pointer}` placeholders into named ones). `python`: list of `{files, calls, keywords, dict_keys}` (Python file globs, call names — a name or an attribute name —, keyword argument names, dictionary keys). A missing document, a `files` glob that matches nothing or a Python file that doesn't parse is a configuration error (exit code 2) |
| `issue` | Key names of issue-shaped objects in responses |
| `severity` | `error` or `warning` per rule |
| `server` | `openapi` path, `env` process environment (`{tmp}` = temporary folder), `options` module options, `dirs` folders to create before the seeds, `seeds` requests that create data (`{method, path, body, if_match}`: `{tmp}` in body strings is replaced, a string body is sent as `text/plain`, and `if_match: {from, select}` reads a GET route and sends the first selected string as `If-Match`), `params` path variable values, `query_params` query variable values (same shape as `params`), `max_param_values` value cap and `skip_paths` routes to skip (routes that may call outside services must be listed here) |

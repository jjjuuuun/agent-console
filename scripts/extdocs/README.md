# extdocs

Checks extension point declarations against the code (`poe extpoints-check`), generates the factual parts of the extension guide (`poe extdocs`), and checks that the generated documents are not stale (`poe extdocs-check`). It is a repository tool and is not shipped. It runs in the workspace venv (pydantic, ruamel.yaml).

Paths and targets come from arguments and data files. To use the tool in another repository, change only `extdocs.yaml` (`--root`, `--config`, `--tool-dir`).

## Commands

| poe task | Direct | What it does | In `poe check` |
| --- | --- | --- | --- |
| `extpoints-check` | `python scripts/extdocs/extdocs.py points [--allow-missing [CAT ...]]` | Checks code against declarations (see "What `points` checks" below). Works without the documents | yes |
| `extdocs` | `python scripts/extdocs/extdocs.py generate [--scaffold]` | Generates `docs/extending/reference.md`, the `extdocs:facts` blocks inside the documents folder, and `examples/extensions/README.md`. `--scaffold` creates an empty stub (`extdocs:todo`) when the section a declaration's `guide` points to does not exist | — |
| `extdocs-check` | `python scripts/extdocs/extdocs.py docs [--allow-missing [CAT ...]]` | Regeneration diff is empty, the area page files in `areas.yaml` exist, guide sections have hand-written text and generated blocks, no `extdocs:todo` is left, relative links and anchors resolve, public lint, `>>>` doctests, and `extdocs:validate` snippet validation. Without the documents folder it prints "no documents folder — skipped" and exits 0 | yes |
| — | `python scripts/extdocs/extdocs.py docs --report [GLOB ...]` | Public lint only, as warnings (default `report_globs`: package and app READMEs). Always exits 0 | — |
| — | `python scripts/extdocs/extdocs.py schema [--check]` | Rewrites `declaration.schema.json` from the model (`points` catches drift) | — |
| `extdocs-test` | `pytest -q -c scripts/extdocs/pytest.ini scripts/extdocs` | The tool's own mypy (strict) and tests (temporary repositories) | yes |

Common options: `--root` (default: the current folder), `--config`, `--tool-dir`, `--quiet` (warnings only as counts per rule). Exit codes: 0 pass, 1 violations, 2 configuration or input error.

## Declaration format

The model is `extdocs_model.py` (Pydantic), and the shared JSON Schema `declaration.schema.json` is generated from it (the TS checks use this file too).

Python package `pyproject.toml`:

```toml
[tool.agent-console]
# Ports and groups that are not extension points (left out of the checks, a reason is required)
internal-ports = [{ port = "wiki.service", reason = "Private between the wiki module and its link modules" }]
internal-groups = [{ group = "agent_console.config_schemas", reason = "..." }]

[tool.agent-console.extension-points.wiki-search-index]
title = "Wiki search index"
area = "wiki"                     # an id from areas.yaml
design_id = "X48"                 # optional, not published in the documents
summary = "Replaces wiki search with another index implementation"
registration = { kind = "entry-point", group = "agent_console_wiki:SEARCH_INDEX_GROUP" }
interface = ["agent_console_wiki:WikiSearchIndex"]
settings = ["wiki.search_backend"]
builtin = "entry-points"          # optional: entry-points (default for entry-point kinds) · providers (default for port kinds) · none · a list of member distributions
example = { kind = "package", path = "examples/extensions/agent-console-example-wiki-search" }
guide = "wiki.md#wiki-search-index"   # relative to the documents folder; the slug when the section is omitted
```

- Slug (the table key): lowercase letters, digits and hyphens. Unique across the repository.
- Sentence fields (`title`, `summary`, `example.note`, and `reason` of `internal-ports`/`internal-groups`) are written in English. The generated documents (`reference.md`, the generated blocks of area pages, the example index) are English-only and copy them as is.
- `registration.kind` is an open string. Known values: `entry-point` (`group`), `port` (`port`, `multi`), `data` (`path`, `settings`, `disable`), `injection`, `annotation`, `descriptor` and `registry` (`name`), and `props` (`export`). Unknown values appear in the table as written and use the `_default` sentence of `templates/registration.yaml`. Adding one sentence template gives them their own sentence.
- `group` and `port` are normally symbols (`module:name`). A string that is not a symbol is taken as the group or port name itself.
- `example` is a single table or a list. Kinds: `package` (an installable example folder `path`), `reference` (a reference implementation inside the repository `path`), `contract-tests` (`symbols`: contract test suites and test double symbols), and `snippet` (a `>>>` or `extdocs:validate` snippet inside the guide section).
- `interface` and `settings` are a single string or a list.
- `builtin` as a list names the workspace distributions that implement the point (for an optional capability with no registration group or port, such as `capability` kinds). The generated "Built-in implementations" shows them as `folder (distribution)` in the listed order.

TS package and app `package.json` (the same model, under the key `extensionPoints`):

```json
{
  "agentConsole": {
    "kind": "lib",
    "extensionPoints": {
      "dashboard-widget": {
        "title": "Dashboard widget", "area": "web", "summary": "...",
        "registration": { "kind": "props", "export": "@agent-console/log-view#DashboardWidgets" },
        "interface": ["@agent-console/log-view#DashboardWidget"],
        "example": { "kind": "package", "path": "examples/web/agent-console-example-web" },
        "guide": "web.md#dashboard-widget"
      }
    }
  }
}
```

An example package lists the points it demonstrates: Python `[tool.agent-console.example] points = ["wiki-search-index"]`, TS `"agentConsole": {"example": {"points": [...]}}`. These must match the `example` (kind `package`) of the point declarations.

## What `points` checks

1. Groups: group constants in the `src` of workspace members (name `*_GROUP`, value `agent_console.*`; the patterns are `code` in `extdocs.yaml`) plus the entry point groups of member pyprojects = declared `registration.group` plus `internal-groups`
2. Ports: provides, requires and optional of the `descriptor` (not built) of member server module entry points = declared `registration.port` plus `internal-ports`. Time limit `descriptor_time_limit_seconds` (10 seconds)
3. Declared Python symbols import. TS symbols (`@pkg#name`) are checked by `pnpm extdocs-check`
4. Example paths exist, example `points` and declared `example` match in pairs, and every point has at least one example
5. The README of an example that demonstrates a declared point has the required sections (`readme_sections.yaml`; a heading that contains an alias counts)
6. No duplicate slugs, `area` exists in `areas.yaml`, the distributions a `builtin` list names are workspace members (`builtin-unknown`), and the declaration format (schema) is valid
7. `declaration.schema.json` matches the model

The targets are only the distributions among the root `[tool.uv.workspace] members` that are linked with `workspace = true` in `[tool.uv.sources]`. Installed examples and outside plugins are not mixed in (determinism).

## Gradual adoption (`--allow-missing`)

Only "not filled in yet" findings are split into categories and lowered to warnings. Format errors, symbol import failures, pair mismatches, missing README sections, stale generated output, links, public lint and snippet validation are always errors.

| Category | What becomes a warning |
| --- | --- |
| `declarations` | Groups and ports without a declaration (`group-undeclared`, `port-undeclared`), and points an example refers to without a declaration (`example-point-undeclared`) |
| `examples` | Points without an example (`example-missing`), and snippet examples whose section has no validated snippet (`snippet-missing`) |
| `guides` | Missing guide files, sections or generated blocks, missing hand-written text, leftover `extdocs:todo`, missing area page files from `areas.yaml` (`area-page-missing`), and links to area pages that are not written yet |

`--allow-missing` alone means all three categories. Declarations, examples and guides are all filled in, so `poe check` does not pass this option. It remains for manual runs while a new area is filled in gradually.

## Document snippets

- Code fences that contain `>>>` are run as doctests with one namespace per file (ELLIPSIS, NORMALIZE_WHITESPACE).
- Data snippets name their model in the fence info string: ` ```yaml extdocs:validate=agent_console_contracts.wiki:WikiRulesDefinition `. The yaml, json or toml is read and validated with that Pydantic model; for models that keep unknown keys, leftover keys (`model_extra`) also count as a failure.

## Public lint

The rules are in `public_lint.yaml` (regular expressions, line by line). The targets are `public_lint_globs` (errors) and `docs --report` (`report_globs`, warnings only). Package and app READMEs (`packages/**/README.md`, `apps/*/README.md`, `apps/web/src/**/README.md`), package and app changelogs (`packages/**/CHANGELOG.md`, `apps/*/CHANGELOG.md`, `examples/**/CHANGELOG.md`), the tool READMEs (`scripts/**/README.md`) and the root public documents (`README.md`, `README.ko.md`, `USAGE.md`, `USAGE.ko.md`, `docs/DEVELOPMENT.md`, `docs/DEVELOPMENT.ko.md`, `CONTRIBUTING.md`, `CHANGELOG.md`; missing files are skipped) are in `public_lint_globs` (new design ids and task numbers are errors). The test guide `apps/web/e2e/README.md` is not a target.

| Rule | Catches | Does not catch |
| --- | --- | --- |
| `internal-doc-link` | `specs/` and `docs/design/` inside a link target, the same following a `./` or `../` relative path, and `specs/<...>.md` or `docs/design/` at the start of a path | API paths with a path segment in front (`GET /sdd/specs/{id}`), and product folders that are not `.md` files (`specs/demo`) <!-- extdocs:allow internal-doc-link --> |
| `internal-config` | See "Product files and development settings" below | Same |
| `design-section` | `§` <!-- extdocs:allow design-section --> | — |
| `task-number` | Task numbers (`5.2R.3`, `8R.4a`) <!-- extdocs:allow task-number --> | — |
| `design-id` | Extension point, decision and requirement ids (`X22`, `(X25)`, `R8.6`, `R0·R10.4`, `K33-19`). Only text outside code fences and inline code is checked (`prose_only`) | Example data inside code (`` `R1` ``, `requirement_ids=["R1"]`), and parts of names (`test_R1_x`, `k8s`, `R2D2`, `0X1F`) |
| `local-path`, `email` | Local paths, email addresses | — |
| `korean-prose` | Korean text outside code fences and inline code in English documents (public lint targets that are not `*.ko.md`). An error, like the other rules | Inside code fences and inline code (Korean source messages in doctest output), Korean copies `*.ko.md`, and the language switch line at the top (`**English** \| [한국어](README.ko.md)`: a line with two or more items separated by `\|`, where each item is only a bold name or a single `.md` link) |

**Product files and development settings.** The app reads and writes Claude Code files (`~/.claude/projects`, `~/.claude/settings.json`, a project's `.claude/agents`, an exported `CLAUDE.md`). In such sentences the file names are **data (product formats)**. Sentences that point to the development `CLAUDE.md` and `.claude/agents` used to build this repository, on the other hand, must not remain in public documents. The two are told apart like this. <!-- extdocs:allow internal-config -->

- Treated as development settings (caught): link targets (`[rules](../../CLAUDE.md)`), sentences that say the file belongs to this repository, such as "the repository (root) `CLAUDE.md`", and bare names in text without quotes or backticks ("the rules are in CLAUDE.md", a code comment `# CLAUDE.md "fixed and environment notes"`). <!-- extdocs:allow internal-config -->
- Treated as product formats (pass): file names wrapped in backticks or quotes (`` `CLAUDE.md` ``, `'.claude/agents/pl.md'`), and names with a path segment in front (`~/.claude/…`, `${CLAUDE_CONFIG_DIR}/…`, `./.claude/hooks`, `*/.claude/rules`, `/srv/me/.claude/…`).
- So when a public document talks about product files, wrap the file names in backticks (even inside code block comments).

**Allowing a single line.** To exempt one line where a rule does not fit, add `<!-- extdocs:allow <rule id> -->` to that line. Join several ids with spaces or commas (`<!-- extdocs:allow internal-config, task-number -->`). The marker turns off only that rule on that line. If the rule itself can be fixed, fix the rule instead of adding markers.

**New rules.** Add `id`, `message` and `pattern` to `public_lint.yaml`. The error code is `public-<id>`. Optional fields:

| Field | Meaning |
| --- | --- |
| `prose_only: true` | Checks only text outside code fences and inline code |
| `files` | Checks only files that match these globs (relative to the repository, a single string or a list). Without it, all target files |
| `exclude_files` | Skips files that match these globs (for example `**/*.ko.md`) |
| `skip_line` | Lines that match this regular expression skip only this rule (for example the language switch line) |
| `severity` | `error` (default) or `warning` (always a warning, for turning on a new rule gradually). Other values are a data format error (exit code 2) |

## Data files

| File | Contents |
| --- | --- |
| `extdocs.yaml` | Paths and target globs (globs do not descend into `glob_skip_dirs` folders or hidden folders), code patterns, contract table symbols and time limits |
| `areas.yaml` | Areas (id, title, file); a new area is one line |
| `readme_sections.yaml` | Required sections of example READMEs and their aliases (English headings). `language_aliases` are old headings accepted only in examples of that language (currently the Korean headings of TS examples, to be removed once the TS READMEs are in English) |
| `public_lint.yaml` | Public lint rules (regular expressions, `prose_only`, `files`, `exclude_files`, `skip_line`, `severity`) |
| `templates/registration.yaml` | "Registration" and "turning off or removing" sentences per registration kind. When a value is a list, the first sentence whose placeholders are all filled is used (the last one unconditionally), so sentences like "Keys that turn it off: ." are not produced from empty values |
| `templates/text.yaml` | Titles, introductions, table headers and the `extdocs:todo` stub of generated files. The generated documents are English-only, so these are written in English. When a title changes, also fix links to its anchor (for example `reference.md#entry-point-groups`); `anchor-broken` in `extdocs-check` catches them |

## Boundary with the TS side (`pnpm extdocs-check`)

The Python side also reads the TS `package.json` declarations, checks their format, slugs, areas and example pairs, and generates the documents (deterministically, without Node). The TS tool covers the following.

- Where to read: `ts_package_globs` in `extdocs.yaml`, the table name `ts_table` (`agentConsole`) and the key `extensionPoints`
- Format: `declaration.schema.json` (top level = slug to declaration)
- Symbols: whether the `@pkg#name` of `interface` and `registration.export` is exported from that package's `src/index.ts` (TypeScript compiler API)
- Output: human-readable lines `오류 [code] where: message` plus optional `--json`. The Python generator does not depend on this JSON

## Tests

```sh
uv run poe extdocs-test
```

The tests build temporary repositories (a root pyproject plus member packages, examples and documents) and check failure and success for each rule. They also check the time it takes to check the descriptors of the repository's real server modules.

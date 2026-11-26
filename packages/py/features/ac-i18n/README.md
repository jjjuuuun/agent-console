# agent-console-i18n

Message catalogs for Agent Console: a per-language JSON format, loading from packages (entry points) and
folders, merging in source order, lookup by original text or by code, and consistency checks. It does not know
about the server, HTTP, or the contract models. It uses only the Python standard library.

A catalog file is `<language>.json` with three sections:

| Section | Key | Value |
| --- | --- | --- |
| `text` | an original server string (the string itself is the key) | its translation |
| `codes` | an error or issue code | a template; `{name}` is filled from the issue `details` |
| `ns` | a web namespace | a nested object whose leaves are strings |

An empty string means "not translated yet": lookups and merges treat it as missing.

Public API (summary):

| What | Functions |
| --- | --- |
| Model | `Catalog`, `CatalogIssue`, `read_catalog(data, *, language, source, origin, path)`, `normalize_language`, `is_language_tag` |
| Loading | `MESSAGE_CATALOGS_GROUP` (`agent_console.message_catalogs`), `package_catalogs(*, entry_points=None, disabled=())`, `folder_catalogs(folders, *, base_dir=None)`, `load_catalog_folder`, `load_catalog_file`, `CatalogLoad` |
| Merge and lookup | `CatalogSet` (`from_load`, `add`, `languages`, `sources`, `catalog`, `translator(language, *, fallback)`), `Translator` (`text`, `code`, `template`, `namespace`), `merge_catalogs`, `match_language`, `placeholders`, `render` |
| Checks | `compare_catalogs(base, other)`, `is_complete`, `check_codes`, `check_texts`, `check_details`, `schema_texts(schema, *, keys)`, `SchemaTextKeys`, `flatten_ns` |
| Test helpers | `agent_console_i18n.testing`: `write_catalog`, `make_catalog_package`, `make_distribution` (a fake installed distribution), `catalog_entry_point` |

Rules:

- Merge order is the order you add catalogs; the later one wins. The usual order is package catalogs (entry
  point name order) and then user folders (list order). `ns` merges leaf by leaf.
- Lookup goes through the chosen language, then the fallback language, then the original text. Language
  matching drops trailing subtags one by one (`en-US` matches `en`).
- Loading never raises for bad data. Unreadable files, invalid entries, and modules that cannot be imported
  are skipped and reported as `CatalogIssue` values with `i18n.*` codes. Issue messages are English (they are
  meant for the terminal).
- Checks only report. The caller decides what is an error (for example, bundled languages must be complete,
  while a language a user adds may be partial).

## Install

```bash
pip install agent-console-i18n
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-i18n
```

## Minimal usage

```python
>>> from agent_console_i18n import Catalog, CatalogSet, compare_catalogs, read_catalog
>>> ko, _ = read_catalog(
...     {"codes": {"run.failed": "{run_id} 실행이 실패했습니다"}}, language="ko", source="demo"
... )
>>> en, _ = read_catalog(
...     {"text": {"저장": "Save"}, "codes": {"run.failed": "Run {run_id} failed"}},
...     language="en", source="demo",
... )
>>> catalogs = CatalogSet([ko, en, Catalog("en", text={"저장": "Store"}, source="user")])
>>> en_us = catalogs.translator("en-US")
>>> en_us.text("저장"), en_us.code("run.failed", {"run_id": "r1"})
('Store', 'Run r1 failed')
>>> catalogs.translator("ko", fallback="en").text("저장")
'Store'
>>> catalogs.sources("en")
('demo', 'user')
>>> compare_catalogs(ko, en, sections=["codes"])
[]

```

Load what installed packages ship (entry point group `agent_console.message_catalogs`, value = a module that
has a `locales/` folder) and then user folders:

```python
>>> from agent_console_i18n import folder_catalogs, package_catalogs
>>> from agent_console_i18n.testing import catalog_entry_point
>>> load = package_catalogs(entry_points=[catalog_entry_point("missing", "no_such_module_xyz")])
>>> [(issue.code, issue.source) for issue in load.issues]
[('i18n.source_unavailable', 'missing')]
>>> CatalogSet.from_load(load, folder_catalogs([])).languages()
()

```

A package registers its catalogs in `pyproject.toml` and includes `locales/*.json` as package data:

```toml
[project.entry-points."agent_console.message_catalogs"]
my-plugin = "my_plugin"
```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```

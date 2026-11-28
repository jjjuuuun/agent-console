# agent-console-mod-i18n

Message catalog feature module (`mod-i18n`). It collects per-language message catalogs from installed packages and
from user folders, merges them, and serves them to the web. The server does not translate its own responses: the web
uses these catalogs to show server text (original-text keys) and error and issue codes (code keys) in the chosen
language. Catalog format, merging, and lookup come from `agent-console-i18n`.

| What | Details |
| --- | --- |
| REST | `GET /i18n` (`I18nInfo`: languages in code order with `sources`, `complete`, `missing`, plus `default_language`, `fallback_language` and `source_language`), `GET /i18n/{lang}` (`MessageCatalog`; `en-US` matches `en`; `ETag` + `Cache-Control: no-cache`, `If-None-Match` → 304) |
| Errors | `i18n.unknown_language` (404; no catalog matches the language, `details.language`, `details.available`) |
| Provided ports | `server.warnings` (catalog files, entries, and packages skipped while loading; `i18n.*` issue codes, severity warning, no catalog values) |
| Required ports | none (the module runs alone) |
| Administrator options | `modules.options.mod-i18n.{default_language, fallback_language, source_language, catalog_dirs, disabled_catalogs}` |
| Plugins | Entry point `agent_console.message_catalogs` (name = catalog id, value = a module with a `locales/` folder). The host plugin loader (`i18n` of `agent_console.host_plugin_loaders`) registers them in the `message_catalogs` extension of the host bundle without importing them |
| Own catalog | `locales/en.json` (entry point `ac-mod-i18n`): English for this module's title, description, and settings schema |
| Web role | `i18n` |

Settings (all optional):

| Key | Default | Meaning |
| --- | --- | --- |
| `default_language` | `en` | Language when neither the screen setting nor the browser language decides it |
| `fallback_language` | `en` | Language for text the chosen language lacks; `complete` and `missing` count against it |
| `source_language` | `ko` | Language the server source text is written in (`I18nInfo.source_language`). The web stops source-text lookups at this language, so a screen in this language shows the source text even when other catalogs are loaded. `null` or empty = unknown (the web looks through the whole fallback chain). In this language (and its subtags such as `ko-KR`) `LanguageInfo.missing` does not count the `text` section, whose keys are the source text itself; codes and `ns` are still counted. Change it only for packages whose source text is in another language |
| `catalog_dirs` | `[]` | Folders with `<language>.json` files. Relative paths are relative to the settings file folder. They come after package catalogs, in list order (later wins) |
| `disabled_catalogs` | `[]` | Package catalog ids to leave out |

- Merge order: package catalogs (entry point name order) → `catalog_dirs` (list order). Later sources win; empty values
  mean "not translated yet" and do not erase earlier values.
- Turning one catalog off: put its id in `modules.options.mod-i18n.disabled_catalogs` or in the host setting
  `plugins.disabled` (the plugin loader skips it, and the server info plugin list shows why). Its text then shows in
  the fallback language or as the original server text.
- User folders are read again when their `*.json` files change (name, size, modification time), so an edited catalog
  shows on the next request. Package catalogs are read once when the module starts.
- Broken files or entries are skipped and reported in `server.warnings` (and once in the terminal log, in English); the
  rest is still served. A catalog module that cannot be imported is `i18n.source_unavailable`.
- With no catalogs at all, `GET /i18n` returns 200 with an empty list. When the module is off, the routes return 404,
  the web uses only its own catalogs, and server text stays as the original.

## Dependencies: what, why, alternatives

- In-house: `agent-console-i18n` (catalog format, loading, merging, checks), `agent-console-contracts` (`I18nInfo`,
  `MessageCatalog`, error codes), `agent-console-modkit` (module, host helpers), `agent-console-registry` (host
  bundle registry and load reports).
- External: FastAPI and pydantic (common to server modules). No new external dependencies.

## Install

```bash
pip install agent-console-mod-i18n
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-i18n
```

## Minimal usage

The service works without a server. Give it package catalogs (here built inline) and user folders:

```python
>>> import json, tempfile
>>> from pathlib import Path
>>> from agent_console_i18n import Catalog, CatalogLoad
>>> from agent_console_mod_i18n import I18nService, UnknownLanguageError

>>> packages = CatalogLoad(catalogs=(
...     Catalog("en", text={"저장": "Save", "열기": "Open"}, source="my-plugin"),
... ))
>>> mine = Path(tempfile.mkdtemp())
>>> _ = (mine / "en.json").write_text(json.dumps({"text": {"저장": "Store"}}), encoding="utf-8")
>>> _ = (mine / "de.json").write_text(json.dumps({"text": {"저장": "Speichern"}}), encoding="utf-8")
>>> service = I18nService(packages=packages, folders=[mine])

>>> [(row.code, row.complete, row.missing) for row in service.info().languages]
[('de', False, 1), ('en', True, 0)]
>>> body = service.catalog("en-US")
>>> body.catalog.language, body.catalog.text
('en', {'저장': 'Store', '열기': 'Open'})
>>> try:
...     service.catalog("fr")
... except UnknownLanguageError as exc:
...     exc.available
('de', 'en')

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

In a server, the module reads package catalogs itself (`package_catalogs`) and resolves `catalog_dirs` against the
settings file folder.

## Standalone run

```bash
python -m agent_console_mod_i18n --config standalone.json --port 0
```

Without a host registry bundle the module reads the installed `agent_console.message_catalogs` entry points directly
(only `disabled_catalogs` applies, since there is no `plugins.disabled`).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

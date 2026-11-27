# Changelog

## 0.1.0

- First release: `GET /i18n` (`I18nInfo`) and `GET /i18n/{lang}` (`MessageCatalog` with `ETag`, 304 on
  `If-None-Match`, 404 `i18n.unknown_language`).
- Settings `modules.options.mod-i18n`: `default_language`, `fallback_language` (both `en`), `source_language`
  (`ko`, the language of the server source text, sent as `I18nInfo.source_language`; null or empty = unknown), `catalog_dirs`,
  `disabled_catalogs`.
- Host plugin loader `i18n`: registers `agent_console.message_catalogs` entry points so `plugins.enabled` and
  `plugins.disabled` apply to catalog ids.
- `server.warnings` for catalog loading problems (`i18n.*` codes). User folders are read again when their files change.
- Own English catalog for the module title, description, and settings schema.

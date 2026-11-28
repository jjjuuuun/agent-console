# Changelog

## 0.1.0

- New package. Per-language JSON message catalogs (`text`, `codes`, `ns`), loading from the entry point group
  `agent_console.message_catalogs` and from folders, merging in source order, lookup with a fallback chain,
  checks (keys and placeholders across languages, missing codes and texts, placeholders against `details`),
  and screen text extraction from JSON Schema. Standard library only.

# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-definitions-resources`, so the web app can show the link module description and settings in English (data
  only, no API change).
- Space-based check `DefinitionChecker.space_issues(space, kind, document)` (optional capability
  `SpaceDefinitionCheck`). Attachment `ref` values are resolved only against resources in that space's store, without
  falling back to the library (`resources.lookup`). It takes the optional port `definitions.spaces`
  (`DEFINITIONS_SPACES`); without it, space-based checks raise `SpacesUnavailable`. Optional argument
  `DefinitionChecker(space_resources=)`. `LookupResources` also treats `LookupError` and `OSError` as "not found".

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Moved the pre-save definition checks of `apps/server` (`DefinitionChecker`: resource type checks and attachment
  override checks) to `definitions.checks`.

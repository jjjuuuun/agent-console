# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-architecture`, so the web app can show the module description, projection
  limit settings and the `architecture.settings_invalid` warning in English (data only, no API change).
- Takes the optional multi-provider port `architecture.profile_checks`
  (`ProfileCheck.check(profile, profile_id) -> list[Issue]`) and adds its results to the `issues` count of the list,
  the `problems` of the detail and the result of `POST /architecture/profiles/check` (read when called; checks that
  raise are skipped). `ArchitectureCatalogService(..., checks=)`. Without providers, behavior is unchanged.

## 0.1.0

- The user settings port `workspace.settings` is looked up when called instead of at build time (settings are read
  regardless of assembly order).
- First release (from the scripts/pkgkit template `module`).
- REST routes for the profile list, detail, checks and standalone projection, the port `architecture.catalog`, the
  host plugin loader for architecture map profiles, the server administrator options `max_request_events` and
  `max_scope_events`, standalone runs (`python -m`), and the web role `architecture`.

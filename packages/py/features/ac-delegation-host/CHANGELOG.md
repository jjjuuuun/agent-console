# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-delegation-host`, so the web app can show the delegation strategy name,
  settings schema and `delegation.*` codes in English (data only, no API change).
- Descriptor `shares_session=False` (the delegate uses its own session). `{code}` and `{message}` in `failure_text`
  only use values that went through the engine's masking (`ctx.secrets.redact`) (`HostDelegation.failure_text`).

## 0.1.0

- First release (from the scripts/pkgkit template `feature`): the delegation strategy `host` (`HostDelegation`,
  `host_descriptor`, `HostDelegationConfig`, `HostDelegationCodes`) and the entry point
  `agent_console.delegation_strategies:host`.

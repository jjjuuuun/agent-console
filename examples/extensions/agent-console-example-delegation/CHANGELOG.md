# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `agent-console-example-delegation`, so the web app can show the round-robin
  `example.round_robin.*` codes in English (data only, no API change).

## 0.1.0

- First release: an example delegation strategy `example.round_robin` (`composable = false`).

# Changelog

## Unreleased (0.2.0)

- Model discovery example (extension point `backend-model-discovery`). The administrator setting `models_file` (a
  JSON model list; relative paths are relative to the app workspace) declares `capabilities.model_discovery`, and
  `discover_models()` returns that list (reason `models_file_missing` when the file is absent, `invalid_response` when
  it is not a JSON list). New constant `MODELS_FILE_MISSING`. Requires `agent-console-runtime>=0.2,<0.3` and
  `agent-console-contracts>=0.16.1,<0.17`.
- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `agent-console-example-backend`, so the web app can show the
  `example.session_missing` error in English (data only, no API change).

## 0.1.0

- First release: the execution backend `example.scripted` (an example of an execution backend and session record
  archiving). A deterministic scripted backend that answers from rule data without a model, a server administrator
  settings hook (`from_options`) and optional session record archiving (`session_archive`).

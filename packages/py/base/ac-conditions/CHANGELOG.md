# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-conditions`, so the web app can show the built-in operator names and condition
  issues (by code) in English (data only, no API change).
- Built-in operator `any_item` (the eleventh): true when at least one list item matches every
  `{path inside the item: [allowed values…]}` entry (the value schema is an object and keys are JSON Pointers). The
  descriptor is a data file and includes the `compile_expected` fast path. The default architecture map uses it to
  count skills attached to the Instructions field together with rules.
- Optional capability `RedactorConsumer.use_redactor(redact)` and type `Redactor` (an extension that builds the
  evaluation evidence receives the app's masking function).
- Optional capability `OperatorConsumer.use_operators(provider)` and `OperatorProvider` (an extension that uses
  operators receives the app's operator registry).

## 0.1.0

- First release: the `ConditionOperator` protocol and the optional `ValueChecker` capability, a registry loader (entry
  point `agent_console.condition_operators`, `LoadReport`), `evaluate_conditions` (the evidence is the contract
  `ConditionOutcome`, and `actual` is masked, then truncated), `condition_issues` (unknown operator is a warning,
  value schema and operator check failures are errors, an empty condition is a warning), and ten built-in operators
  (descriptors are data files).

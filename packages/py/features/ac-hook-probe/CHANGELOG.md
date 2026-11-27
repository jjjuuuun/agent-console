# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-hook-probe`, so the web app can show the hook probe log source and classifier in English (data only, no API
  change).
- The `agent-console-hook-probe` help and usage errors are in English. The recorded data and the wrapped command
  output are unchanged.

## 0.1.0

- First release: the executable `agent-console-hook-probe` and `python -m agent_console_hook_probe` (passes stdin
  through, keeps stdout, stderr and the exit code byte-identical, forwards signals to the child process group with a
  forced stop after a grace period, isolates recording failures), the record format `hook-probe/1` (derived decision,
  masking of suspected secrets, command hash), shell argument rule data (`DEFAULT_SHELLS`), the wrapping helpers
  `wrap_command` and `wrap_command_line`, the log source `hook-probe-jsonl` and the classifier `hook-probe`.

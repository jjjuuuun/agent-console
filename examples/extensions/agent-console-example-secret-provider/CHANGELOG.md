# Changelog

## Unreleased

- Internal log messages are now in English.
- The server administrator settings schema has a human-readable title and description (the *Extension options*
  heading in Settings used to show the class name and code docstring).
- Raised the development dependency range to `agent-console-server>=1.0,<2` (server display version 1.0.0). No code
  changes.

## 0.1.0

- First release: an example secret provider `example-file` that reads secret values from `KEY=VALUE` lines in a local
  file you choose. The file path comes from an environment variable and the line rule is option data.

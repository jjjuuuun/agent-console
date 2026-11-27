# Changelog

## 0.1.0

- First release: `PtySession` (spawn, read, write, keys, wait, forced stop after a grace period), `TerminalText` and
  `strip_ansi` (removes control sequences, handles `\r` overwrites, line-based screen, OSC 8 links), `ExpectRules` and
  `ExpectWatcher` (rules to signals, with an injected compile function), adapters for POSIX `ptyprocess` and Windows
  `pywinpty` (optional `windows` extra), `PtyUnavailableError`, and the test doubles `FakePty` and `FakePtySpawner`.

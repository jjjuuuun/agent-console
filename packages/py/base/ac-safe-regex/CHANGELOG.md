# Changelog

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
- Performance: named group values and positions of a match result (`SafeMatch`) are built from a single `regs` read
  (no `span` or `groupdict` call per group). In `regex`, groups with the same name share one number, so values and
  positions are unchanged.

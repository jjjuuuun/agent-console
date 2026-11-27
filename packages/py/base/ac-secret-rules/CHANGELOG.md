# Changelog

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
- Masking is idempotent (spots that are already masked are not masked again).
- Fixed masking boundary limits. When value characters follow the closing bracket of an assignment value pattern, they
  are treated as part of the value. Text that already contains the mask string is also scanned as a copy with that
  spot filled with value characters, so fragments attached to a masked spot are masked as one piece. No public API
  changes.
- Prefix tokens with characters in front (`xxxsk-…`, `keyAKIA…`) are masked too. The default value patterns gained a
  prefix token rule without a word boundary (only when the body has digits or uppercase letters and a run of 16 or
  more characters without separators). The existing word boundary rules are unchanged. No public API changes.
- Added weak key names (`weak_key_names`, default `key`) and weak value shapes (`weak_value_patterns`) as data. In
  structural detection (`find_suspected`), when every matched key name is weak (`input_key`, `sort_key`), the value is
  suspected only when it looks like a secret (this fixes a defect where `input_key` in an edge config was flagged as a
  plain-text secret and saving to a project space failed with 422). `api_key`, `secret_key` and `sk-…` values are
  still caught. Names added with `with_extra(key_names=)` are removed from the weak names. The public API gained two
  constructor arguments and two default data constants.

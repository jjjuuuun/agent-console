# Changelog

## 0.1.0

- First release (from the scripts/pkgkit template `base`).
- `query_hasher(mode, salt=)`, `QueryHasher`, `QueryHashModes` and `QUERY_HASH_MODES`: the search query hasher moved
  out of `ac-memory`, so `ac-memory` and `ac-wiki` share it. Search queries are encoded with `surrogatepass`.
- `query_hasher_from_env(mode, salt_env=, environ=)`: settings (mode plus the name of the salt environment variable)
  to a hasher.

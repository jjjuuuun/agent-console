# agent-console-query-hash

Builds the query hash stored in search events. Queries are often short, so an unsalted sha256 can be reversed with a dictionary attack;
the default is therefore a salted HMAC-SHA256. It uses only the standard library. The caller chooses the mode and the salt and passes them in
(for example, server administrator settings plus an environment variable). This package never stores or prints the salt.

- `query_hasher(mode="hmac", *, salt=None, random_bytes=secrets.token_bytes)`: query → hex hash (or None).
  - `hmac`: HMAC-SHA256(salt, query). If the salt is missing or empty, 32 random bytes are drawn when the hasher is created (the same value only within that hasher).
  - `sha256`: unsalted sha256 (when you need the same value across installations).
  - `off`: always None (no hash is attached).
- `query_hasher_from_env(mode, *, salt_env, environ)`: builds a hasher from settings (mode plus the name of the salt environment variable). If the variable is missing or
  empty, a random salt is used. `environ` is injected (usually `os.environ`).
- `QueryHasher`: `Callable[[str], str | None]`. Tool sets accept only this shape.
- `QueryHashModes`, `QUERY_HASH_MODES`: mode names (for settings validation and screen choices).

## Installation

```bash
pip install agent-console-query-hash
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-query-hash
```

## Minimal usage

```python
>>> import hashlib
>>> from agent_console_query_hash import QUERY_HASH_MODES, query_hasher
>>> QUERY_HASH_MODES
('hmac', 'sha256', 'off')
>>> keyed = query_hasher("hmac", salt=b"from-env")
>>> keyed("plan") == keyed("plan") != query_hasher("hmac", salt=b"other")("plan")
True
>>> query_hasher("sha256")("plan") == hashlib.sha256(b"plan").hexdigest()
True
>>> query_hasher("off")("plan") is None
True
>>> from agent_console_query_hash import query_hasher_from_env
>>> from_env = query_hasher_from_env("hmac", salt_env="MY_SALT", environ={"MY_SALT": "from-env"})
>>> from_env("plan") == keyed("plan")
True

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

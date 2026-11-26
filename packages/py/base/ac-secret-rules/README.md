# agent-console-secret-rules

Finds values **suspected** to be plain-text secrets (`find_suspected`) and masks suspected parts of a text (`redact_suspected`).
It is a heuristic for when the schema is unknown. If the schema has `x-secret`, that check takes precedence.
Masking is idempotent: places that already hold the mask string (`mask`) are not masked again, so applying it twice gives the same result. Plain text attached to a mask string is still masked.
It also blocks inputs that insert a mask string to leave the tail of a secret behind: if the text contains a mask string, a copy with that spot filled with value characters
is scanned too, and a fragment attached to a masked spot is masked together with it (`password=[REDACTED]hunter2` →
`password=[REDACTED]`). A closing bracket of an assigned value (`)`, `}`, `]`) counts as part of the value when value characters follow it
(`password=abc]hunter2` → `password=[REDACTED]`, `{password=abc}` → `{password=[REDACTED]}`). Text that does not hit a secret rule
(such as `AAAA[REDACTED]BBBB`, with no name or prefix) is left as is.
Its only internal dependency is `ac-safe-regex` (user regex validation and time-limited runs), so you can take it to another project as is.

Where Agent Console uses it: `ac-imports` (turns secrets in arguments and URLs into references on import), `ac-resources` (checks attachment overrides
that have no resource), and the server (the plain-text warning `secret.plain_found`, masking suspected values before saving run history and interactions).

## Rules are data

| Data | Default | Meaning |
| --- | --- | --- |
| `key_names` | `DEFAULT_KEY_NAMES` | Secret name words. A name is split into words (separators, camelCase), and it is suspected when joining consecutive words gives a match (`api_key`, `apiKey`, `x-api-key`, `APIKEY`). `author` and `max_tokens` do not match because the words differ |
| `name_exceptions` | `DEFAULT_NAME_EXCEPTIONS` | Names that are not secrets when they come **after** a secret word (`--key-file`, `auth_mode`, `token_url`) |
| `value_patterns` | `DEFAULT_VALUE_PATTERNS` | Secret shapes inside text (known prefixed tokens: with a word boundary before, a body of 6 or more characters; with letters attached before (`xxxsk-…`), only key-shaped bodies that contain digits or capitals and a 16-character run without separators; JWT, PEM private keys, `Bearer x`, `--token x`, `API_KEY=x`, `?token=x`, `"password": "x"`, `user:pw@`). The named group `secret` is the part to mask; the group `name` must be a secret name to match |
| `weak_key_names` | `DEFAULT_WEAK_KEY_NAMES` (`key`) | Key names with a broad meaning. If every key name matched in a name is one of these (`input_key`, `sort_key`), structural judgement suspects it only when the value has a secret shape. If it also matches another key name, like `api_key` (`apikey`), the name alone is enough. `weak_key_names=()` turns this off. Names added with `with_extra(key_names=)` are removed from the weak names |
| `weak_value_patterns` | `DEFAULT_WEAK_VALUE_PATTERNS` | Secret shapes for values under weak names (16 or more letters and digits without separators that include a digit, UUIDs). Values that match `value_patterns` (`sk-…`) also count as secret shapes |
| `is_reference` | `secret://…` | References (names, not values) are left out of suspicion and masking |

User rules can only be **added** with `with_extra(key_names=, value_patterns=)`. There is no public way to reduce the default rules
(reducing them would leak secrets). Value patterns are checked with `ac-safe-regex`, so dangerous patterns (`(a+)+`) raise
`InvalidSecretRuleError` (for pre-save validation, `check_extra_rules` returns them as a list of problems).

## Judgement

- String leaves: suspected when non-empty, not a reference, and either under the nearest secret key name (`key_name`) or containing a secret shape
  (`value_pattern`).
- Number leaves (excluding booleans and null): suspected when under a secret key name (`{"API_KEY": 12345}`).
- Under a weak key name (`{"input_key": "question"}`), a value is suspected only when it has a secret shape (`{"input_key": "sk-…"}`,
  32 hex characters). Name judgement (`name_suspected`), text masking, and flags in argument lists (`--key x`) still suspect weak names
  by name alone (the safe side).
- Child objects and lists **inherit** the nearest secret key name, except when the last word of their own name is an exception word
  (`{"auth": {"mode": "oauth"}}`).
- In an argument list, the item after a secret flag (`--token`) is treated as a secret value.
- The result `Finding{path, reason}` **contains no value**. The path is a JSON Pointer (including a `path=` prefix).
- If a pattern check exceeds its time limit, it falls to the safe side: judgement suspects it as `timeout`, and masking masks the whole text.
- Long text is scanned in overlapping chunks of `max_scan_chars` (default 1 million characters).

## Installation

```bash
uv sync --all-packages                          # inside the workspace
uv pip install ./packages/py/base/ac-safe-regex ./packages/py/base/ac-secret-rules   # standalone
```

## Minimal usage

```python
>>> from agent_console_secret_rules import SecretRules, check_extra_rules

>>> rules = SecretRules().with_extra(key_names=["session-id"], value_patterns=[r"corp_[0-9]{6}"])

>>> for f in rules.find_suspected(
...     {"env": {"API_KEY": "abc"}, "args": ["--token", "x"], "note": "corp_123456"}, path="/config"
... ):
...     print(f.path, f.reason)  # location and reason only (no value)
/config/env/API_KEY key_name
/config/args/1 key_name
/config/note value_pattern

>>> rules.redact_suspected("curl -H 'Authorization: Bearer abc123456' --token zzz")
"curl -H 'Authorization: Bearer [REDACTED]' --token [REDACTED]"

>>> [(p.field, p.index) for p in check_extra_rules([], ["(a+)+"])]  # validate user rules
[('extra_value_patterns', 0)]

```

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-secret-rules`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/base/ac-secret-rules/tests
```

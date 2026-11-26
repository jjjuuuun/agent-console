# agent-console-safe-zip

A small library that reads a user-uploaded zip **in memory, within limits, without extracting it to disk**.
Memory Markdown import (`ac-memory`) and wiki page import (`ac-wiki`) use the same safety rules from here (the same
checks are not kept in two places). It uses only the standard library `zipfile`.

- Whole-archive rejection (`ZipLimitError`, `limit` = the name of the exceeded limit): compressed size, entry count, declared size of one entry, and total declared
  size. Bytes actually decompressed are also capped (in case the header lies about sizes).
- Format error (not a zip): `ZipFormatError`.
- Per-entry marking only (`ZipMember.kind`): `unsafe` (`..`, `.`, empty segments, absolute paths, drive letters, backslashes, control characters,
  symbolic links; not read), `encrypted`, `broken` (corrupt compressed data), `dir`, `file` (has bytes). What to accept
  (extensions, location rules) is up to the caller.
- Writing with `write_zip`: path order, fixed timestamp, deflate, mode 0644, so the same input gives the same bytes.

## Installation

```bash
pip install agent-console-safe-zip
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-safe-zip
```

## Minimal usage

```python
>>> from agent_console_safe_zip import ZipLimitError, ZipLimits, read_zip, write_zip

>>> data = write_zip([("notes/a.md", b"# A\n"), ("b.md", b"B")])
>>> [(m.name, m.kind, m.data) for m in read_zip(data)]
[('b.md', 'file', b'B'), ('notes/a.md', 'file', b'# A\n')]

>>> try:
...     read_zip(data, ZipLimits(max_file_bytes=2))
... except ZipLimitError as exc:
...     print(exc.limit)
max_file_bytes

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

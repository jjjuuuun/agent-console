# agent-console-numbered-id

A small base package that holds one rule: "if the name is taken, append `-2`, `-3`, …". It uses only the standard library.
Project registration ids, definition ids made from names, renames during import, new node ids in graph suggestions, and backup file names
all share this rule.

- An empty desired name is returned as is. Otherwise the first free number starting at `-2` is appended.
- The caller decides what "taken" means (case-insensitive, store lookup, file exists) by passing the function `is_taken`.
- With `max_length`, the front part is cut so the numbered name fits the length. With `limit`, the search stops before that number and,
  if nothing is free, raises `NoFreeId` (a `LookupError`).

## Installation

```bash
pip install agent-console-numbered-id
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-numbered-id
```

## Minimal usage

```python
>>> from agent_console_numbered_id import numbered_id
>>> taken = {"notes", "notes-2"}
>>> numbered_id("notes", taken.__contains__), numbered_id("todo", taken.__contains__)
('notes-3', 'todo')
>>> folded = {t.casefold() for t in ["App"]}
>>> numbered_id("app", lambda name: name.casefold() in folded, max_length=128)
'app-2'

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Dependencies: what / why / alternatives

No external dependencies (standard library only).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

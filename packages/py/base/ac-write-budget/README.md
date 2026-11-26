# agent-console-write-budget

A write-count limit that one run shares across several tool sets (for example, the memory and wiki agent tools). It uses only the standard library
and is thread-safe. The caller decides the limit value, reason code, and messages; this package only counts.

- `WriteBudget(limit)`: `take()` returns true (and uses one write) while writes remain, false otherwise. With `limit=None` it is always true.
- `WriteBudgetLike`: a protocol that only needs `take() -> bool`. Tool sets accept only this shape.

## Installation

```bash
pip install agent-console-write-budget
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-write-budget
```

## Minimal usage

```python
>>> from agent_console_write_budget import WriteBudget, WriteBudgetLike
>>> budget = WriteBudget(2)
>>> [budget.take() for _ in range(3)], budget.used
([True, True, False], 2)
>>> isinstance(budget, WriteBudgetLike), WriteBudget(None).take()
(True, True)

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

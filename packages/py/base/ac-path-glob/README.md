# agent-console-path-glob

A small base package that turns path globs (with `**` support) into regular expressions and checks whether a path matches. It uses only the standard library.
It exists so that features that take "path shaped" settings, such as the include and exclude patterns of a log source or the target paths of a wiki page rule,
share the same rules.

- `*` and `?` do not cross `/`. `**/` matches zero or more folders, and a trailing `/**` matches the folder itself and everything below it.
- Patterns and paths are compared without rewriting them. Normalize Windows paths with `normalize_path` first.
- Matching is case-sensitive by default. Pass `case_insensitive=True` to ignore case.
- Format checks (rejecting empty patterns, absolute paths, and so on) are caller rules, so they are not included.

## Installation

```bash
pip install agent-console-path-glob
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-path-glob
```

## Minimal usage

```python
>>> from agent_console_path_glob import glob_match, normalize_path
>>> glob_match("docs/**", "docs"), glob_match("docs/**", "docs/a/b.md")
(True, True)
>>> glob_match("*.md", "a/b.md"), glob_match("**/*.md", "a/b.md")
(False, True)
>>> glob_match("Notes/*", "notes/today", case_insensitive=True)
True
>>> glob_match("docs/**", normalize_path("docs\\a\\b.md\\"))
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

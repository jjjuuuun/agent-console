# agent-console-text-template

A small library that **safely substitutes** template strings that users write as data (the `template` of a declarative resource kind, the input template of an SDD run profile, and so on).
It has no internal or external dependencies (standard library only).

Rules:

- Only `{name}` and `{name:format}` are substituted. Attribute (`{o.x}`) and index (`{l[0]}`) access is not performed.
- Format specifiers are limited to numeric precision (`.1f`, `.0%`, `.2`). Any other format (`>99999` and so on) is left as written.
- Unknown names are left as written. Substituted values are not substituted again.
- The result is cut at `max_chars` (default `DEFAULT_MAX_RENDER_CHARS` = 1,000,000 characters) and `…` is appended.
- It never raises (a value that does not fit the format becomes `str(value)`).

## Installation

```bash
uv sync --all-packages                                  # inside the workspace
uv pip install ./packages/py/base/ac-text-template      # standalone, from another project
```

## Minimal usage

```python
>>> from agent_console_text_template import fill_value, render_template, template_variables
>>> render_template("{task}: {score:.1f} {missing} {o.secret}", {"task": "T1", "score": 0.87})
'T1: 0.9 {missing} {o.secret}'
>>> fill_value({"prompt": ["{task}", 3]}, {"task": "T1"})
{'prompt': ['T1', 3]}
>>> sorted(template_variables("{task} {spec} {task}") - {"task"})
['spec']

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Public API

| Name | Purpose |
| --- | --- |
| `render_template(template, values, *, max_chars=DEFAULT_MAX_RENDER_CHARS) -> str` | Substitutes one string |
| `fill_value(value, values, *, max_chars=...) -> Any` | A copy with every string inside mappings and lists substituted (keys unchanged, tuples become lists) |
| `template_variables(template) -> set[str]` | Names that a template (a string, or a mapping or list) references, including names in places where the format is not allowed |
| `DEFAULT_MAX_RENDER_CHARS` | Default cap on the result length |

## Dependencies: what / why / alternatives

- None (standard `re`). The alternative, Jinja2, has far more features than needed and carries a sandboxing burden.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```

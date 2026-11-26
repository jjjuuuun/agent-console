# agent-console-example-condition

An example that adds a new **condition operator** with a single plugin package.
No engine, server, or web code changes. Once installed, it appears in the operator list (`GET /api/v1/condition-operators`) and in the operator
choices of the editor's condition widget, and conditional edges (`when`) and other extensions that read conditions use it as they are. It disappears when removed.

Condition operator `example.word_count_at_least` (word count at least)
- True when the value the path points to is text and the number of words split by whitespace (including line breaks) is at least the expected value.
- Value schema (`value_schema`) `{"type": "integer", "minimum": 0}`: the pre-save check validates the value with this schema
  (a wrong value such as `"3"` is a `condition.invalid_value` error). `applies_to: ["string"]` (a hint for the screen).
- False when the value is not text or the path has no value (it does not raise). It is deterministic, without external calls.
- Its only dependency is the contract (`agent-console-contracts`). It does not import the evaluator or the engine.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

```python
from typing import Any

from agent_console_contracts import ConditionOperatorDescriptor


class WordCountAtLeast:
    descriptor = ConditionOperatorDescriptor(
        id="example.word_count_at_least",
        title="단어 수 이상",
        value_schema={"type": "integer", "minimum": 0},
        applies_to=["string"],
    )

    def evaluate(self, actual: Any, expected: Any) -> bool:
        return (
            isinstance(actual, str)
            and isinstance(expected, int)
            and len(actual.split()) >= expected
        )
```

The real implementation is `src/agent_console_example_condition/word_count.py` (it also rejects booleans and negative expected values).

```python
>>> from agent_console_example_condition import WordCountAtLeast
>>> op = WordCountAtLeast()
>>> op.descriptor.id, op.evaluate("하나 둘 셋", 3), op.evaluate("하나 둘", 3), op.evaluate(None, 0)
('example.word_count_at_least', True, False, False)

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Registration

One entry point in `pyproject.toml`. Group = `agent_console_conditions.CONDITION_OPERATORS_GROUP`
(`agent_console.condition_operators`); name = the descriptor `id` = the `op` of a condition item.

```toml
[project.entry-points."agent_console.condition_operators"]
"example.word_count_at_least" = "agent_console_example_condition:WordCountAtLeast"
```

To use only the evaluator without an entry point, register it in a registry directly (the tests do this):
`registry = new_operator_registry(); registry.register("example.word_count_at_least", WordCountAtLeast())`.

Using it in a team: choose it as the `op` of a condition item in the config of a conditional edge (`when`).

```yaml
edges:
  - id: long-enough
    source: {node: writer, port: out}
    target: {node: reviewer, port: in}
    kind: when
    config:
      conditions:
        all:
          - {path: /output, op: example.word_count_at_least, value: 50}
```

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-condition   # install
uv pip uninstall agent-console-example-condition                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Install: `GET /api/v1/condition-operators` lists `example.word_count_at_least`.
- Remove: it disappears from the list. Conditions that use this operator are not deleted; the pre-save check reports `condition.unknown_operator`
  (warning), and at run time that item is false (evidence `reason = unknown_operator`, with a warning event), so the conditional edge is blocked.
- Turn off while installed: remove `example.word_count_at_least` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest
with this folder's settings (`uv run poe examples`). Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>`
(`uv run poe wheels` in the repository), and then `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-condition
uv run --project ../../.. python -m pytest
```

Tests: the truth table, using it with the evaluator (`ac-conditions`) and the default operators, the pre-save check (value schema), an engine run through a conditional edge (`when`,
`ac-nodes-core`), and warning and false after removal.
E2E: `apps/web/e2e/08-extension.spec.ts` (`ext` flavor) installs this package into a temporary folder and checks the list and a run.

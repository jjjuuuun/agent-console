# agent-console-conditions

A small library that applies declarative conditions (JSON Pointer + operator) to a target (JSON), produces **a result and its evidence**, and creates pre-save validation
issues. Condition operators come in through an extension point (entry point `agent_console.condition_operators`),
and the 11 default operators (`eq`, `ne`, `in`, `contains`, `matches`, `exists`, `gt`, `gte`, `lt`, `lte`, `any_item`) are registered
the same way. You use it on its own, without the server or the execution engine.

- The condition data shape is the contract `ConditionSpec{all?, any?, negate?}` and `ConditionItem{path, op, value?}`; the evidence is
  `ConditionOutcome` (the shape the screen draws as is); the operator descriptor is
  `ConditionOperatorDescriptor` (all in `agent-console-contracts`).
- `all` means every item is true, `any` means at least one is true, and when both are present both must hold. If both are missing or empty the result is true (a pre-save warning).
  `negate` flips the final result. Every item is evaluated so the evidence is complete.
- A type mismatch is false (for example, a string in a numeric comparison). If the path has no value, the operator receives `MISSING` and
  returns false (`reason = "missing"`); an unknown operator is false (`unknown_operator`); an operator exception is false (`error`).
- `eq` and `ne` compare with JSON semantics (numbers by value so `1 == 1.0`, booleans differ from numbers). If the types differ, `eq` is
  false and `ne` is true (they are not equal). If the path has no value, both are false.
- The actual value in the evidence (`actual`) is masked with the injected `redact` **first** and then cut at `max_actual_chars` (default 200).
- `matches` uses only `agent-console-safe-regex` (input length and time limits, rejection of dangerous patterns). Pre-save validation uses the same
  rules to block dangerous patterns as `condition.invalid_value`.
- The titles, descriptions, and value schemas of the default operators are the data file `src/agent_console_conditions/data/builtin_operators.json`
  (the code only implements the comparisons).

- An extension that uses operators (for example, a condition edge type) can offer the optional capability `OperatorConsumer.use_operators(provider)`, and the app
  passes in its own operator registry (`lambda: operator_map(registry)`). Operators turned off in settings and operators added by explicit
  plugins are then reflected the same way in evaluation, pre-save validation, and the operator list (`GET /condition-operators`).
- An extension that produces evidence can offer the optional capability `RedactorConsumer.use_redactor(redact)`, and the app passes in a secret-masking function
  (`Redactor`, for example the engine's `SecretResolver.redact`). The extension passes it on to `evaluate_conditions(redact=)`
  so actual values in the evidence are masked **before they are cut**.

## Dependencies: what / why / alternatives

- **jsonschema, referencing**: validate condition values against the operator `value_schema` before saving (with an empty registry that does not fetch external
  `$ref`). `ac-graph` already uses these libraries, so this is not a new dependency. Alternative: code a value check in each operator,
  which would keep the descriptor (data) and the check rules in two places.
- Internal: `agent-console-contracts` (models), `agent-console-registry` (registry, `LoadReport`),
  `agent-console-safe-regex`(`matches`).

## Installation

```bash
pip install agent-console-conditions
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-conditions
```

## Minimal usage

```python
>>> from agent_console_conditions import condition_issues, default_operators, evaluate_conditions
>>> from agent_console_contracts import ConditionSpec

>>> operators, reports = default_operators()  # from installed entry points (including the 11 defaults)
>>> spec = ConditionSpec.model_validate(
...     {"all": [{"path": "/output", "op": "contains", "value": "PASS"},
...              {"path": "/iteration", "op": "lt", "value": 3}]}
... )
>>> outcome = evaluate_conditions(spec, {"output": "all tests PASS", "iteration": 1}, operators)
>>> outcome.result, outcome.combinator, [(i.op, i.result) for i in outcome.items]
(True, 'all', [('contains', True), ('lt', True)])

>>> bad = ConditionSpec.model_validate(
...     {"any": [{"path": "/output", "op": "fuzzy"}, {"path": "/n", "op": "gt", "value": "3"}]}
... )
>>> [(i.severity, i.code, i.path) for i in condition_issues(bad, operators, base_path="/conditions")]
[('warning', 'condition.unknown_operator', '/conditions/any/0/op'), ('error', 'condition.invalid_value', '/conditions/any/1/value')]

```

When you do not need evidence and judge many targets with the same condition, use the precompiled fast path. It resolves paths, looks up operators,
and binds expected values once, and returns only true or false (`all` stops at the first false, `any` at the first true). The result equals
`evaluate_conditions(...).result` called with the same operators (differential test).

```python
>>> from agent_console_conditions import compile_conditions, conditions_hold
>>> holds = compile_conditions(spec, operators)
>>> holds({"output": "all tests PASS", "iteration": 1}), holds({"output": "FAIL", "iteration": 1})
(True, False)
>>> conditions_hold(spec, {"output": "PASS", "iteration": 5}, operators)  # for a one-off check
False

```

An operator can produce a judge function with the expected value bound (`actual → bool`,
which also accepts `MISSING`) through the optional capability `CompilableOperator.compile_expected(expected)`. All 11 defaults have it. If the capability is missing, returns None, or raises while building,
the fast path judges only that item with `evaluate(actual, expected)` (the result must be the same).

`necessary_items(spec, operators)` returns, as `(key, item judge)`, the items that must be true for the condition set to be true and that depend on "one top-level key" (items of `all`,
or the single item when `any` has only one) (none when `negate` is set). An item's result depends only on that key's value,
so a caller that judges many targets with the same condition can remember results per key value and filter out conditions that cannot match
in advance (`ac-architecture` `ProfileMatcher`).

```python
>>> from agent_console_conditions import necessary_items
>>> [key for key, _ in necessary_items(spec, operators)]
['output', 'iteration']

```

A new operator is an object with a `descriptor` (`ConditionOperatorDescriptor`) and `evaluate(actual, expected) -> bool`.
Give the entry point the same name as the descriptor id.

```toml
[project.entry-points."agent_console.condition_operators"]
words_at_least = "my_pkg.ops:WordsAtLeast"
```

You can also register one directly without an entry point.

```python
>>> from agent_console_conditions import new_operator_registry, operator_map
>>> from agent_console_conditions.builtin import CONTAINS
>>> registry = new_operator_registry()
>>> _ = registry.register("contains", CONTAINS)
>>> sorted(operator_map(registry))
['contains']

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

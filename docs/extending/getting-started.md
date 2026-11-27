# Get started: your first plugin

This walkthrough builds one condition operator as a plugin package, installs it, checks it on the server, turns it
off, and removes it. A condition operator is a comparison rule that a conditional edge (`when`) of a team uses to
decide whether to move on to the next node. Its only dependency is the contract package, so it is the smallest kind
of plugin.

The operator you build here, `mine.max_chars` (at most N characters), is true when the length of the text being
checked is at most the value.

## 1. Install the server

If you already run a server, skip this step and read the commands below with the server's Python environment in mind.

You need a wheelhouse for distribution. Build it from the source repository.

```bash
uv run poe wheels          # → dist/wheelhouse
```

Create a virtual environment in an empty folder and install the server. `<wheelhouse>` is the path of the folder
above.

```bash
mkdir my-console && cd my-console
uv venv --python 3.12
uv pip install --find-links <wheelhouse> agent-console-cli
uv run --no-project agent-console serve --workspace ./ws     # 127.0.0.1:8765, stop with Ctrl-C
```

When the server is up, `GET http://127.0.0.1:8765/api/v1/health` returns 200. After you check it, stop the server.

If you rebuild the wheelhouse (wheels with the same name and version) and install again, uv may install the old wheel
from its cache. In that case, add `--reinstall` to `uv pip install`, or install with a new cache folder
(`UV_CACHE_DIR=<empty folder>`). See [Distribution](distribution.md#install).

## 2. Check the contract version

A plugin uses the same contract package (`agent-console-contracts`) as the server. Look at the installed version and
write the dependency with the same minor range (while the version is 0.x, a minor change can break compatibility).

```bash
uv pip show agent-console-contracts      # Version: 0.16.x → range >=0.16,<0.17
```

```python
>>> from importlib.metadata import version
>>> version("agent-console-contracts")
'0.16...'

```

## 3. Create the package

```text
my-console-ops/
├── pyproject.toml
└── src/my_console_ops/__init__.py
```

`pyproject.toml`:

```toml
[project]
name = "my-console-ops"
version = "0.1.0"
description = "조건 연산자 하나: 글자 수 이하"
requires-python = ">=3.12"
dependencies = [
    "agent-console-contracts>=0.16,<0.17",
]

[project.entry-points."agent_console.condition_operators"]
"mine.max_chars" = "my_console_ops:MaxChars"

[build-system]
requires = ["uv_build>=0.8.17,<0.9"]
build-backend = "uv_build"
```

- The entry point group `agent_console.condition_operators` is the "condition operator" extension point. The groups
  are listed in the [entry point group table](reference.md#entry-point-groups).
- The entry point name (`mine.max_chars`) is the operator id, and it must equal the descriptor `id`. Add your own
  prefix (`mine.`) so that it does not collide with other plugins.
- Do not use `agent-console-` in the package name or `agent_console_` in the module name. Those names belong to the
  server distribution.

`src/my_console_ops/__init__.py`:

```python
"""Condition operator `mine.max_chars`: true when the text is at most the expected number of characters."""

from typing import Any

from agent_console_contracts import ConditionOperatorDescriptor


class MaxChars:
    descriptor = ConditionOperatorDescriptor(
        id="mine.max_chars",
        title="글자 수 이하",
        description="텍스트 길이가 값 이하인지 봅니다.",
        value_schema={"type": "integer", "minimum": 0},
        applies_to=["string"],
    )

    def evaluate(self, actual: Any, expected: Any) -> bool:
        # false instead of an exception when it is not text or there is no value
        return isinstance(actual, str) and isinstance(expected, int) and len(actual) <= expected
```

- `descriptor` is the data the screens use to draw the operator. `value_schema` is the JSON Schema that checks the
  value of a condition item before saving, so the pre-save check reports a wrong value such as `"3"` as an error.
- `evaluate` only decides. It has no external calls or side effects, and it returns false for input it does not
  understand.
- When the entry point points to a class, the server creates an instance without arguments.

## 4. Install and restart

Install into the same environment as the server. Entry points are read when the server starts, so restart the server
after installing.

```bash
uv pip install ./my-console-ops
uv run --no-project agent-console serve --workspace ./ws
```

## 5. Check

```bash
curl -s http://127.0.0.1:8765/api/v1/condition-operators      # "mine.max_chars" is in the list
curl -s http://127.0.0.1:8765/api/v1/server-info               # plugins has {"name": "mine.max_chars", "status": "loaded"}
```

On the web, connect two nodes with a conditional edge in the team editor and add a condition: the operator choices
show the operator by its descriptor `title`. The value field is an integer input, as `value_schema` says. The same
condition written in a file looks like this.

```yaml
edges:
  - id: short-enough
    source: {node: writer, port: out}
    target: {node: reviewer, port: in}
    kind: when
    config:
      conditions:
        all:
          - {path: /output, op: mine.max_chars, value: 200}
```

If loading fails (an import error, a missing descriptor), the server still starts, and that entry in `server-info`
shows `failed` with the reason. The detailed rules are in [Plugin basics](plugins.md#load-time-and-failures).

## 6. Test

Test with the condition evaluator, without a server. The evaluator package (`agent-console-conditions`) is included
when you install the server.

```python
# my-console-ops/tests/test_max_chars.py
from agent_console_conditions import condition_issues, default_operators, evaluate_conditions
from agent_console_contracts import ConditionSpec


def test_installed_operator_is_found_and_evaluated() -> None:
    operators, _ = default_operators()          # read from the installed entry points
    spec = ConditionSpec.model_validate(
        {"all": [{"path": "/output", "op": "mine.max_chars", "value": 5}]}
    )
    assert condition_issues(spec, operators) == []
    assert evaluate_conditions(spec, {"output": "짧다"}, operators).result is True
    assert evaluate_conditions(spec, {"output": "조금 더 긴 글"}, operators).result is False
```

```bash
uv pip install pytest
uv run --no-project pytest my-console-ops/tests
```

For more ways to test, see [Testing](testing.md).

## 7. Turn it off

To keep the plugin installed but not use it, put its name in the server setting `plugins.disabled` and restart the
server. Other plugins and the built-in implementations are read as usual.

The name is the **entry point name** (`mine.max_chars`), not the distribution name (`my-console-ops`). It is the
`name` shown in `plugins` of `GET /api/v1/server-info`. If you write a name that is not installed, the server still
starts and records a warning, in the startup log and in `warnings` of `server-info` (code `plugins.unknown_disabled`), that the name
is not an installed plugin name and is ignored. If you wrote the distribution name by mistake, the warning (code `plugins.disabled_distribution`) also lists
the names you should write, the entry point names of that distribution (here `mine.max_chars`).

`agent-console.yaml`:

```yaml
plugins:
  disabled: [mine.max_chars]
```

The server reads `agent-console.yaml` in the folder it starts from. For a file with another name or in another folder,
pass it with `--config PATH`.

```bash
uv run --no-project agent-console serve --workspace ./ws --config ./agent-console.yaml
curl -s http://127.0.0.1:8765/api/v1/condition-operators      # "mine.max_chars" is not there
curl -s http://127.0.0.1:8765/api/v1/server-info               # plugins has {"name": "mine.max_chars", "status": "skipped", "reason": "설정 plugins.disabled에 있음"}
```

To list only what you use, use the allow list `plugins.enabled` (you must include the names of the built-in
implementations too). When you set both, the deny list is removed from the allow list. For details, see
[Plugin basics](plugins.md#turning-plugins-on-and-off).

## 8. Remove

```bash
uv pip uninstall my-console-ops
```

After you restart the server, the operator disappears from the list. Conditions that used this operator are not
deleted.

- The pre-save check and the check results in the team list get the warning `condition.unknown_operator`.
- At run time, that condition item is judged false and a warning event is recorded. That conditional edge is blocked.
- When you install the plugin again, it works as before.

Checking the same condition in an environment where the plugin is not installed looks like this.

```python
>>> from agent_console_conditions import condition_issues, default_operators
>>> from agent_console_contracts import ConditionSpec
>>> operators, _ = default_operators()
>>> spec = ConditionSpec.model_validate(
...     {"all": [{"path": "/output", "op": "mine.max_chars", "value": 200}]}
... )
>>> [(i.severity, i.code) for i in condition_issues(spec, operators)]
[('warning', 'condition.unknown_operator')]

```

## Next

- A more complete example of the same point (value checks, an engine run test): [agent-console-example-condition](../../examples/extensions/agent-console-example-condition/README.md)
- Other points: [Extension guide map](README.md#what-do-you-want-to-change)
- Distribution: [Distribution](distribution.md)

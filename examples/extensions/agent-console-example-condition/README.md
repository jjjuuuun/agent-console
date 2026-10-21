# agent-console-example-condition

새 **조건 연산자**(확장 지점 X22)를 플러그인 패키지 하나로 추가하는 예제(R0·R10.4, design §5R.14).
엔진·서버·웹 코드를 고치지 않고, 설치하면 연산자 목록(`GET /api/v1/condition-operators`)과 편집기 조건 위젯의
연산자 선택지에 나타나고, 조건 연결(`when`)·조건을 읽는 다른 확장이 그대로 쓴다. 제거하면 사라진다.

조건 연산자 `example.word_count_at_least`(단어 수 이상)
- 경로가 가리키는 값이 텍스트이고, 공백(줄바꿈 포함)으로 나눈 단어 수가 기대 값 이상이면 참.
- 값 스키마(`value_schema`) `{"type": "integer", "minimum": 0}` — 저장 전 검사가 이 스키마로 값을 확인한다
  (`"3"`처럼 틀린 값은 `condition.invalid_value` error). `applies_to: ["string"]`(화면 안내).
- 텍스트가 아니거나 경로에 값이 없으면 거짓(예외를 던지지 않는다). 외부 호출 없이 결정적으로 동작한다.
- 의존은 계약(`agent-console-contracts`) 하나뿐이다. 평가기·엔진을 import하지 않는다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

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

실제 구현은 `src/agent_console_example_condition/word_count.py`(참거짓·음수 기대 값 거부).

```python
>>> from agent_console_example_condition import WordCountAtLeast
>>> op = WordCountAtLeast()
>>> op.descriptor.id, op.evaluate("하나 둘 셋", 3), op.evaluate("하나 둘", 3), op.evaluate(None, 0)
('example.word_count_at_least', True, False, False)

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 등록

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console_conditions.CONDITION_OPERATORS_GROUP`
(`agent_console.condition_operators`), 이름 = 디스크립터 `id` = 조건 항목의 `op`.

```toml
[project.entry-points."agent_console.condition_operators"]
"example.word_count_at_least" = "agent_console_example_condition:WordCountAtLeast"
```

entry point 없이 평가기만 쓸 때는 레지스트리에 직접 등록한다(테스트가 그렇게 한다):
`registry = new_operator_registry(); registry.register("example.word_count_at_least", WordCountAtLeast())`.

팀 구성에서 쓰기: 조건 연결(`when`) config의 조건 항목 `op`로 고른다.

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

## 설치·제거

저장소 루트에서 실행한다. WSL(`/mnt/c`)에서는 환경변수를 붙인다(CLAUDE.md "고정·환경 메모").

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-condition   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-condition                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/condition-operators`에 `example.word_count_at_least`가 나온다.
- 제거: 목록에서 사라진다. 이 연산자를 쓰는 조건은 지워지지 않고, 저장 전 검사가 `condition.unknown_operator`
  (warning)로 알리며, 실행 때 그 항목은 거짓(근거 `reason = unknown_operator`, 경고 이벤트)이다 — 조건 연결은 막힌다.
- 설치한 채로 끄기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example.word_count_at_least`를 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로
mypy·pytest를 돌린다(`uv run poe examples`). 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`
(저장소에서 `uv run poe wheels`) 뒤 `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-condition
uv run --project ../../.. python -m pytest
```

테스트: 판정 표, 평가기(`ac-conditions`)와 기본 연산자 함께 쓰기, 저장 전 검사(값 스키마), 조건 연결(`when`,
`ac-nodes-core`)로 엔진 실행, 제거하면 warning·거짓.
E2E: `apps/web/e2e/08-extension.spec.ts`(`ext` flavor)가 이 패키지를 임시 폴더에 설치해 목록·실행을 확인한다.

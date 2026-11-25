# 시작하기: 첫 플러그인

조건 연산자 하나를 플러그인 패키지로 만들어 설치하고, 서버에서 확인하고, 끄고, 지우는 데까지 한 바퀴 돈다.
조건 연산자는 팀 구성의 조건 연결(`when`)이 "다음 노드로 넘어갈지"를 판단할 때 쓰는 비교 규칙이다. 의존이 계약
패키지 하나뿐이라 가장 작은 플러그인이다.

여기서 만드는 연산자 `mine.max_chars`(글자 수 이하)는 판단 대상 텍스트의 길이가 값 이하이면 참이다.

## 1. 서버 설치

이미 서버를 돌리고 있으면 이 단계는 건너뛰고, 아래 명령의 Python 환경을 서버가 도는 환경으로 바꿔 읽는다.

배포용 휠 모음이 필요하다. 소스 저장소에서 만든다.

```bash
uv run poe wheels          # → dist/wheelhouse
```

빈 폴더에 가상 환경을 만들고 서버를 설치한다. `<wheelhouse>`는 위 폴더의 경로다.

```bash
mkdir my-console && cd my-console
uv venv --python 3.12
uv pip install --find-links <wheelhouse> agent-console-cli
uv run --no-project agent-console serve --workspace ./ws     # 127.0.0.1:8765, Ctrl-C로 끝
```

서버가 뜨면 `GET http://127.0.0.1:8765/api/v1/health`가 200을 돌려준다. 확인했으면 서버를 끈다.

휠 모음을 다시 만든 뒤(이름·버전이 같은 휠) 설치하면 uv 캐시의 옛 휠이 깔릴 수 있다. 그때는 `uv pip install`에
`--reinstall`을 붙이거나 새 캐시 폴더(`UV_CACHE_DIR=<빈 폴더>`)로 설치한다. → [배포](distribution.md#설치)

## 2. 계약 버전 확인

플러그인은 서버와 같은 계약 패키지(`agent-console-contracts`)를 쓴다. 설치된 버전을 보고 같은 minor 범위로 의존을
적는다(0.x 동안은 minor가 바뀌면 호환이 깨질 수 있다).

```bash
uv pip show agent-console-contracts      # Version: 0.15.x → 범위 >=0.15,<0.16
```

```python
>>> from importlib.metadata import version
>>> version("agent-console-contracts")
'0.15...'

```

## 3. 패키지 만들기

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
    "agent-console-contracts>=0.15,<0.16",
]

[project.entry-points."agent_console.condition_operators"]
"mine.max_chars" = "my_console_ops:MaxChars"

[build-system]
requires = ["uv_build>=0.8.17,<0.9"]
build-backend = "uv_build"
```

- entry point 그룹 `agent_console.condition_operators`가 "조건 연산자"라는 확장 지점이다. 그룹 목록은
  [entry point 그룹 표](reference.md#entry-point-그룹)에 있다.
- entry point 이름(`mine.max_chars`)은 연산자 id이고, 디스크립터의 `id`와 같아야 한다. 다른 플러그인과 겹치지 않게
  자기 접두사(`mine.`)를 붙인다.
- 패키지 이름에 `agent-console-`, 모듈 이름에 `agent_console_`를 쓰지 않는다. 그 이름은 서버 배포가 쓴다.

`src/my_console_ops/__init__.py`:

```python
"""조건 연산자 `mine.max_chars`: 텍스트가 기대 값 글자 수 이하이면 참."""

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
        # 텍스트가 아니거나 값이 없으면 예외 대신 거짓
        return isinstance(actual, str) and isinstance(expected, int) and len(actual) <= expected
```

- `descriptor`는 화면이 연산자를 그리는 데이터다. `value_schema`는 조건 항목의 값을 저장하기 전에 검사하는 JSON
  Schema라서 `"3"`처럼 틀린 값은 저장 전 검사가 오류로 알린다.
- `evaluate`는 판정만 한다. 외부 호출·부작용을 두지 않고, 모르는 입력이면 거짓을 돌려준다.
- entry point가 클래스를 가리키면 서버가 인자 없이 인스턴스를 만든다.

## 4. 설치하고 다시 시작

서버와 같은 환경에 설치한다. entry point는 서버가 시작할 때 읽으므로 설치 뒤 서버를 다시 시작한다.

```bash
uv pip install ./my-console-ops
uv run --no-project agent-console serve --workspace ./ws
```

## 5. 확인

```bash
curl -s http://127.0.0.1:8765/api/v1/condition-operators      # 목록에 "mine.max_chars"
curl -s http://127.0.0.1:8765/api/v1/server-info               # plugins에 {"name": "mine.max_chars", "status": "loaded"}
```

웹에서는 팀 구성 편집기에서 두 노드를 조건 연결로 잇고 조건을 더하면 연산자 선택지에 "글자 수 이하"가 보인다.
값 칸은 `value_schema`대로 정수 입력이다. 같은 조건을 파일로 쓰면 이렇다.

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

로드에 실패하면(import 오류, 디스크립터 없음) 서버는 그대로 시작하고 `server-info`의 그 항목이 `failed`와 이유를
보인다. 자세한 규칙은 [플러그인 공통](plugins.md#로드-시점과-실패).

## 6. 테스트

서버 없이 조건 평가기로 시험한다. 평가기 패키지(`agent-console-conditions`)는 서버를 설치하면 함께 들어 있다.

```python
# my-console-ops/tests/test_max_chars.py
from agent_console_conditions import condition_issues, default_operators, evaluate_conditions
from agent_console_contracts import ConditionSpec


def test_installed_operator_is_found_and_evaluated() -> None:
    operators, _ = default_operators()          # 설치된 entry point에서 읽는다
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

더 많은 시험 방법은 [테스트](testing.md).

## 7. 끄기

설치한 채로 쓰지 않으려면 서버 설정 `plugins.disabled`에 그 이름을 적고 서버를 다시 시작한다. 나머지 플러그인과
기본 구현은 그대로 읽힌다.

이름은 배포 이름(`my-console-ops`)이 아니라 **entry point 이름**(`mine.max_chars`)이다. `GET /api/v1/server-info`의
`plugins`에 나오는 `name`이 그 이름이다. 설치되지 않은 이름을 적으면 서버는 그대로 시작하고, 시작 로그와
`server-info`의 `warnings`(`plugins.config`)에 "설치된 플러그인 이름이 아닙니다(무시함)"를 남긴다.

`agent-console.yaml`:

```yaml
plugins:
  disabled: [mine.max_chars]
```

서버는 띄운 폴더의 `agent-console.yaml`을 읽는다. 다른 이름이나 다른 폴더의 파일이면 `--config PATH`로 넘긴다.

```bash
uv run --no-project agent-console serve --workspace ./ws --config ./agent-console.yaml
curl -s http://127.0.0.1:8765/api/v1/condition-operators      # "mine.max_chars"가 없다
curl -s http://127.0.0.1:8765/api/v1/server-info               # plugins에 {"name": "mine.max_chars", "status": "skipped", "reason": "설정 plugins.disabled에 있음"}
```

쓸 것만 골라 적고 싶으면 허용 목록 `plugins.enabled`를 쓴다(기본 구현 이름도 함께 적어야 한다). 둘 다 적으면
허용 목록 안에서 제외 목록을 뺀다. 자세한 내용은 [플러그인 공통](plugins.md#켜고-끄기).

## 8. 제거

```bash
uv pip uninstall my-console-ops
```

서버를 다시 시작하면 연산자가 목록에서 사라진다. 이 연산자를 쓰던 조건은 지워지지 않는다.

- 저장 전 검사와 팀 구성 목록의 검사 결과에 경고 `condition.unknown_operator`가 붙는다.
- 실행 때 그 조건 항목은 거짓으로 판정되고 경고 이벤트가 남는다. 그 조건 연결은 막힌다.
- 다시 설치하면 그대로 동작한다.

설치하지 않은 환경에서 같은 조건을 검사하면 이렇게 보인다.

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

## 다음

- 같은 지점의 더 완전한 예제(값 검사, 엔진 실행 테스트): [agent-console-example-condition](../../examples/extensions/agent-console-example-condition/README.md)
- 다른 지점: [확장 가이드 지도](README.md#무엇을-바꾸고-싶은가)
- 배포: [배포](distribution.md)

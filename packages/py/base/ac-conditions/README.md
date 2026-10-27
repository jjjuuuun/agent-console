# agent-console-conditions

선언형 조건(JSON Pointer + 연산자)을 판단 대상(JSON)에 적용해 **결과와 근거**를 내고, 저장 전 검사 이슈를
만드는 작은 라이브러리. 조건 연산자는 확장 지점(X22, entry point `agent_console.condition_operators`)으로
들어오며, 기본 연산자 10개(`eq`·`ne`·`in`·`contains`·`matches`·`exists`·`gt`·`gte`·`lt`·`lte`)도 같은 길로
등록된다. 서버·실행 엔진 없이 단독으로 쓴다.

- 조건 데이터 모양은 계약 `ConditionSpec{all?, any?, negate?}`·`ConditionItem{path, op, value?}`, 근거는
  `ConditionOutcome`(화면 명세 screen-delegation §12 S1 모양), 연산자 디스크립터는
  `ConditionOperatorDescriptor`다(모두 `agent-console-contracts`).
- `all`은 모두 참, `any`는 하나라도 참, 둘 다 있으면 둘 다 만족. 둘 다 없거나 비면 참(저장 전 검사 warning).
  `negate`면 최종 결과를 뒤집는다. 근거를 위해 모든 항목을 평가한다.
- 형식이 맞지 않으면 거짓이다(예: 숫자 비교에 문자열). 경로에 값이 없으면 연산자는 `MISSING`을 받고
  거짓(`reason = "missing"`), 모르는 연산자는 거짓(`unknown_operator`), 연산자 예외는 거짓(`error`).
- `eq`·`ne`는 JSON 의미로 비교한다(숫자는 값으로 `1 == 1.0`, 참거짓은 숫자와 다름). 형식이 다르면 `eq`는
  거짓, `ne`는 참이다(같지 않으므로). 단 경로에 값이 없으면 둘 다 거짓.
- 근거의 실제 값(`actual`)은 주입한 `redact`로 가린 **뒤** `max_actual_chars`(기본 200)에서 자른다.
- `matches`는 `agent-console-safe-regex`만 쓴다(입력 길이·시간 상한, 위험 패턴 거부). 저장 전 검사도 같은
  규칙으로 위험한 패턴을 `condition.invalid_value`로 막는다.
- 기본 연산자의 제목·설명·값 스키마는 데이터 파일 `src/agent_console_conditions/data/builtin_operators.json`
  이다(코드는 비교 동작만).

- 연산자를 쓰는 확장(예: 조건 연결 종류)은 선택 능력 `OperatorConsumer.use_operators(provider)`를 두면 앱이
  자기 연산자 레지스트리(`lambda: operator_map(registry)`)를 넘겨준다. 그러면 설정으로 끈 연산자나 명시
  플러그인이 더한 연산자가 평가·저장 전 검사·연산자 목록(`GET /condition-operators`)에 똑같이 반영된다.
- 판정 근거를 만드는 확장은 선택 능력 `RedactorConsumer.use_redactor(redact)`를 두면 앱이 비밀 가림 함수
  (`Redactor`, 예: 엔진 `SecretResolver.redact`)를 넘겨준다. 확장은 그것을 `evaluate_conditions(redact=)`로
  넘겨 근거의 실제 값을 **자르기 전에** 가린다.

## 의존성: 무엇을 / 왜 / 대안

- **jsonschema·referencing**: 연산자 `value_schema`로 조건 값을 저장 전에 검사한다(외부 `$ref`는 가져오지
  않는 빈 registry). 이미 `ac-graph`가 쓰는 라이브러리라 새 의존이 아니다. 대안: 값 형식 검사를 연산자마다
  코드로 — 디스크립터(데이터)와 검사 규칙이 두 벌이 된다.
- 사내: `agent-console-contracts`(모델), `agent-console-registry`(레지스트리·`LoadReport`),
  `agent-console-safe-regex`(`matches`).

## 설치

```bash
pip install agent-console-conditions
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-conditions
```

## 최소 사용

```python
>>> from agent_console_conditions import condition_issues, default_operators, evaluate_conditions
>>> from agent_console_contracts import ConditionSpec

>>> operators, reports = default_operators()  # 설치된 entry point에서(기본 10개 포함)
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

새 연산자는 `descriptor`(`ConditionOperatorDescriptor`)와 `evaluate(actual, expected) -> bool`을 가진 객체다.
entry point 이름은 디스크립터 id와 같게 둔다.

```toml
[project.entry-points."agent_console.condition_operators"]
words_at_least = "my_pkg.ops:WordsAtLeast"
```

entry point 없이 직접 등록할 수도 있다.

```python
>>> from agent_console_conditions import new_operator_registry, operator_map
>>> from agent_console_conditions.builtin import CONTAINS
>>> registry = new_operator_registry()
>>> _ = registry.register("contains", CONTAINS)
>>> sorted(operator_map(registry))
['contains']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

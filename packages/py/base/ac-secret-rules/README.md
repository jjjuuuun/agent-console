# agent-console-secret-rules

평문 비밀로 **의심되는** 값을 찾고(`find_suspected`), 텍스트 안의 의심 부분을 가린다(`redact_suspected`).
스키마를 모를 때 쓰는 휴리스틱이다. 스키마에 `x-secret`이 있으면 그쪽 검사가 우선이다.
가림은 멱등이다: 이미 있는 가림 문자열(`mask`) 자리는 다시 가리지 않으므로 두 번 적용해도 결과가 같다(4R.22). 가림 문자열에 붙은 평문은 그대로 가린다.
가림 문자열을 사이에 끼워 비밀의 뒤 조각을 남기는 입력도 막는다(5R.19): 텍스트에 가림 문자열이 있으면 그 자리를 값 글자로
채운 사본도 함께 훑고, 가린 자리에 붙은 조각은 그 자리와 한 덩어리로 가린다(`password=[REDACTED]hunter2` →
`password=[REDACTED]`). 대입 값의 닫는 괄호(`)`·`}`·`]`)는 뒤에 값 글자가 이어지면 값의 일부로 본다
(`password=abc]hunter2` → `password=[REDACTED]`, `{password=abc}` → `{password=[REDACTED]}`). 비밀 규칙에
걸리지 않는 글(`AAAA[REDACTED]BBBB`처럼 이름·접두어가 없는 것)은 그대로 둔다.
사내 의존은 `ac-safe-regex`(사용자 정규식 검사·시간 제한 실행)뿐이라 다른 프로젝트에 그대로 가져갈 수 있다.

쓰는 곳(Agent Console): `ac-imports`(가져올 때 인자·URL의 비밀을 참조로 바꿈), `ac-resources`(리소스가 없는
첨부 덮어쓰기 검사), 서버(평문 점검 경고 `secret.plain_found`, 실행 기록·상호작용 저장 전 의심 가림).

## 규칙은 데이터다

| 데이터 | 기본값 | 뜻 |
| --- | --- | --- |
| `key_names` | `DEFAULT_KEY_NAMES` | 비밀 이름 단어. 이름을 단어로 나눠(구분자·camelCase) 이어지는 단어를 붙인 것이 같으면 의심(`api_key`·`apiKey`·`x-api-key`·`APIKEY`). `author`·`max_tokens`는 단어가 달라 안 걸린다 |
| `name_exceptions` | `DEFAULT_NAME_EXCEPTIONS` | 비밀 단어 **뒤에** 오면 비밀이 아닌 이름(`--key-file`, `auth_mode`, `token_url`) |
| `value_patterns` | `DEFAULT_VALUE_PATTERNS` | 텍스트 안 비밀 모양(알려진 접두 토큰 — 앞이 단어 경계면 몸통 6자 이상, 앞에 글자가 붙었으면(`xxxsk-…`) 숫자·대문자가 있고 구분자 없는 16자 구간이 있는 키 모양 몸통만, JWT, PEM 개인 키, `Bearer x`, `--token x`, `API_KEY=x`·`?token=x`·`"password": "x"`, `user:pw@`). 이름 그룹 `secret` = 가릴 부분, `name` = 비밀 이름이어야 매치 |
| `is_reference` | `secret://…` | 참조(값이 아니라 이름)는 의심·가림에서 뺀다 |

사용자 규칙은 `with_extra(key_names=, value_patterns=)`로 **더하기만** 한다. 기본 규칙을 줄이는 공개 방법은
없다(줄이면 비밀이 샌다). 값 패턴은 `ac-safe-regex`로 검사하므로 위험한 패턴(`(a+)+`)은
`InvalidSecretRuleError`(저장 전 검사는 `check_extra_rules`가 문제 목록으로 돌려준다).

## 판정

- 문자열 잎: 비어 있지 않고 참조가 아니며, 가까운 비밀 키 이름 아래이거나(`key_name`) 안에 비밀 모양이 있으면
  (`value_pattern`) 의심.
- 숫자 잎(불리언·null 제외): 비밀 키 이름 아래면 의심(`{"API_KEY": 12345}`).
- 하위 객체·목록은 가장 가까운 비밀 키 이름을 **이어받는다**. 단 자기 이름의 마지막 단어가 예외 단어면
  이어받지 않는다(`{"auth": {"mode": "oauth"}}`).
- 인자 목록에서 비밀 플래그(`--token`) 다음 항목은 비밀 값으로 본다.
- 결과 `Finding{path, reason}`에는 **값이 없다**. path는 JSON Pointer(`path=` 접두 포함).
- 패턴 검사가 시간 제한을 넘으면 안전한 쪽으로 처리한다: 판정은 `timeout`으로 의심, 가리기는 텍스트 전체를 가림.
- 긴 텍스트는 `max_scan_chars`(기본 100만 자) 조각으로 겹쳐 나눠 훑는다.

## 설치

```bash
uv sync --all-packages                          # 워크스페이스 안에서
uv pip install ./packages/py/base/ac-safe-regex ./packages/py/base/ac-secret-rules   # 단독으로
```

## 최소 사용 예

```python
>>> from agent_console_secret_rules import SecretRules, check_extra_rules

>>> rules = SecretRules().with_extra(key_names=["session-id"], value_patterns=[r"corp_[0-9]{6}"])

>>> for f in rules.find_suspected(
...     {"env": {"API_KEY": "abc"}, "args": ["--token", "x"], "note": "corp_123456"}, path="/config"
... ):
...     print(f.path, f.reason)  # 위치와 이유만(값은 담지 않는다)
/config/env/API_KEY key_name
/config/args/1 key_name
/config/note value_pattern

>>> rules.redact_suspected("curl -H 'Authorization: Bearer abc123456' --token zzz")
"curl -H 'Authorization: Bearer [REDACTED]' --token [REDACTED]"

>>> [(p.field, p.index) for p in check_extra_rules([], ["(a+)+"])]  # 사용자 규칙 검증
[('extra_value_patterns', 0)]

```

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-secret-rules`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/base/ac-secret-rules/tests
```

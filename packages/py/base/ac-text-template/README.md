# agent-console-text-template

사용자가 데이터로 쓰는 틀 문자열(선언형 리소스 종류의 `template`, SDD 실행 프로필의 입력 틀 등)을
**안전하게 치환**하는 작은 라이브러리. 사내·외부 의존이 없다(표준 라이브러리만).

규칙:

- `{이름}`·`{이름:형식}`만 치환한다. 속성(`{o.x}`)·인덱스(`{l[0]}`) 접근은 하지 않는다.
- 형식 지정자는 숫자 정밀도(`.1f`, `.0%`, `.2`)만 허용한다. 그 밖의 형식(`>99999` 등)은 원문 그대로 둔다.
- 모르는 이름은 원문 그대로 둔다. 치환된 값은 다시 치환하지 않는다.
- 결과 길이는 `max_chars`(기본 `DEFAULT_MAX_RENDER_CHARS` = 1,000,000자)에서 잘라 `…`를 붙인다.
- 예외를 던지지 않는다(값에 맞지 않는 형식은 `str(value)`).

## 설치

```bash
uv sync --all-packages                                  # 워크스페이스 안에서
uv pip install ./packages/py/base/ac-text-template      # 다른 프로젝트에서 단독으로
```

## 최소 사용

```python
>>> from agent_console_text_template import fill_value, render_template, template_variables
>>> render_template("{task}: {score:.1f} {missing} {o.secret}", {"task": "T1", "score": 0.87})
'T1: 0.9 {missing} {o.secret}'
>>> fill_value({"prompt": ["{task}", 3]}, {"task": "T1"})
{'prompt': ['T1', 3]}
>>> sorted(template_variables("{task} {spec} {task}") - {"task"})
['spec']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 공개 API

| 이름 | 용도 |
| --- | --- |
| `render_template(template, values, *, max_chars=DEFAULT_MAX_RENDER_CHARS) -> str` | 문자열 하나 치환 |
| `fill_value(value, values, *, max_chars=...) -> Any` | 매핑·목록 안 문자열 전부 치환한 사본(키는 그대로, 튜플은 목록으로) |
| `template_variables(template) -> set[str]` | 틀(문자열 또는 매핑·목록)이 참조하는 이름. 형식이 허용되지 않는 자리의 이름도 포함 |
| `DEFAULT_MAX_RENDER_CHARS` | 결과 길이 기본 상한 |

## 의존성: 무엇을 / 왜 / 대안

- 없음(표준 `re`). 대안 Jinja2는 기능이 넘치고 샌드박스 부담이 있다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

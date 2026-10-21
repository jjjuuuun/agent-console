# agent-console-safe-regex

사용자가 설정 데이터로 넣는 정규식(라우팅 규칙, 수동 지정 문법, 콘솔 진입 지정 문법 등)을
**검증 → 컴파일 → 시간 제한 실행**하는 작은 라이브러리. 사내 의존이 없다(외부 의존: `regex`).

방어는 세 겹이다.

1. **실행 시간 제한(주 방어)**: 매치 1회마다 `timeout`(기본 0.1초). 넘으면 `RegexTimeoutError`.
2. **입력 길이 제한**: 입력 앞 `max_input_chars`(기본 4096자)만 검사한다.
3. **검증 단계 휴리스틱(보조)**: 패턴 길이(기본 512자), 문법 오류, 필수 이름 그룹, 그리고
   반복되는 그룹 안의 반복(`(a+)+`, `(.*a){20}`, `(x+){2,}`)과 반복되는 그룹 안의 겹치는
   대안(`(a|a)*`, `(a|ab)+`, `(.|x)*`)을 거부한다. 원자 그룹 `(?>...)`과 소유 수량자(`a++`)는
   허용한다. 휴리스틱은 완전하지 않으므로 시간 제한이 최종 보장이다.

## 의존성: 무엇을 / 왜 / 대안

- **무엇을**: [`regex`](https://pypi.org/project/regex/) (Apache-2.0, 활발히 유지보수). `re`와 호환되는
  문법에 매치별 `timeout=` 인자를 제공한다.
- **왜**: 표준 `re`에는 시간 제한이 없어 사용자 정규식 하나로 서버 이벤트 루프가 멈출 수 있다.
  `regex`의 timeout은 매치 엔진 안에서 확인하므로 프로세스·스레드 추가 없이 매치 1회 비용을
  상한으로 묶는다. 결과 타입은 `SafeMatch`로 감싸 구현 라이브러리를 공개 API에 노출하지 않는다.
- **대안**
  - 별도 프로세스에서 `re` 실행 후 시간 초과 시 종료: 확실히 끊을 수 있지만 매치마다 IPC·프로세스
    비용이 커서(수~수십 ms) 입력마다 여러 규칙을 도는 라우팅에 과하다. Windows/WSL에서 spawn이 느리다.
  - 스레드 + 타임아웃: Python 스레드는 강제 종료할 수 없어 폭주한 매치가 CPU를 계속 쓴다.
  - `google-re2`(선형 시간 엔진): 백트래킹 자체가 없지만 역참조·전후방 탐색을 지원하지 않아 기존
    `re` 문법과 다르고, 네이티브 빌드 의존이 생긴다.

## 설치

```bash
uv sync --all-packages                        # 워크스페이스 안에서
uv pip install ./packages/py/base/ac-safe-regex    # 다른 프로젝트에서 단독으로
```

## 최소 사용 예

```python
>>> from agent_console_safe_regex import RegexTimeoutError, UnsafeRegexError, compile_user_regex

>>> pat = compile_user_regex(
...     r"^@(?P<category>[\w-]+)\s+", required_groups=("category",), timeout=0.05
... )
>>> try:
...     m = pat.search("@spec 새 기능")
... except RegexTimeoutError:
...     m = None  # 호출자가 정한다(예: 매치 없음으로 보고 기록)
>>> m.group("category"), m.end, m.span("category")
('spec', 6, (1, 5))

>>> try:  # 검증 단계에서 사용자에게 보여 줄 설정 오류
...     compile_user_regex("(a+)+")
... except UnsafeRegexError as exc:
...     print(str(exc).split("(")[0])
반복되는 그룹 안에 다시 반복이 있다

>>> [(m.start, m.text) for m in compile_user_regex(r"tok_\d+").finditer("a tok_1 b tok_22")]
[(2, 'tok_1'), (10, 'tok_22')]

```

검증만 할 때는 `check_user_regex(pattern, required_groups=...)`.
모든 매치가 필요하면(예: 텍스트 안의 비밀 가리기) `pat.finditer(text)`를 쓴다. 시간 제한은 훑기 전체에
한 번 적용되며, 이름 그룹 위치는 `SafeMatch.span(name)`으로 얻는다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-safe-regex`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/base/ac-safe-regex/tests
```

# agent-console-path-glob

경로 글롭(`**` 지원)을 정규식으로 바꾸고 경로가 맞는지 판정하는 작은 기반 패키지다. 표준 라이브러리만 쓴다.
로그 출처의 포함·제외 패턴, 위키 페이지 규칙의 적용 경로처럼 "경로 모양" 설정을 받는 기능이 같은 규칙을
나눠 쓰려고 만들었다.

- `*`·`?`는 `/`를 넘지 않는다. `**/`는 0개 이상의 폴더, 끝의 `/**`는 그 폴더 자신과 모든 하위다.
- 패턴·경로를 바꾸지 않고 비교한다. Windows 경로는 `normalize_path`로 먼저 맞춘다.
- 대소문자는 기본으로 구분하고 `case_insensitive=True`로 무시한다.
- 형식 검사(빈 패턴·절대 경로 거부 등)는 쓰는 쪽 규칙이라 넣지 않았다.

## 설치

```bash
pip install agent-console-path-glob
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-path-glob
```

## 최소 사용

```python
>>> from agent_console_path_glob import glob_match, normalize_path
>>> glob_match("docs/**", "docs"), glob_match("docs/**", "docs/a/b.md")
(True, True)
>>> glob_match("*.md", "a/b.md"), glob_match("**/*.md", "a/b.md")
(False, True)
>>> glob_match("Notes/*", "notes/today", case_insensitive=True)
True
>>> glob_match("docs/**", normalize_path("docs\\a\\b.md\\"))
True

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

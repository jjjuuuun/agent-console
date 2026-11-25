# agent-console-numbered-id

"이미 있으면 뒤에 `-2`, `-3`…을 붙인다"는 규칙 하나를 담은 작은 기반 패키지다. 표준 라이브러리만 쓴다.
프로젝트 등록 id, 이름에서 만든 정의 id, 가져오기의 이름 바꾸기, 그래프 제안의 새 노드 id, 백업 파일 이름이
같은 규칙을 나눠 쓴다.

- 바라는 이름이 비어 있으면 그대로 돌려준다. 아니면 `-2`부터 처음 빈 번호를 붙인다.
- "이미 있음"의 판정(대소문자 무시·저장소 조회·파일 존재)은 쓰는 쪽이 함수 `is_taken`으로 준다.
- `max_length`를 주면 번호를 붙일 때 앞부분을 잘라 길이를 맞춘다. `limit`를 주면 그 번호 전까지만 찾고, 없으면
  `NoFreeId`(`LookupError`)를 던진다.

## 설치

```bash
pip install agent-console-numbered-id
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-numbered-id
```

## 최소 사용

```python
>>> from agent_console_numbered_id import numbered_id
>>> taken = {"notes", "notes-2"}
>>> numbered_id("notes", taken.__contains__), numbered_id("todo", taken.__contains__)
('notes-3', 'todo')
>>> folded = {t.casefold() for t in ["App"]}
>>> numbered_id("app", lambda name: name.casefold() in folded, max_length=128)
'app-2'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 의존성 (무엇을 / 왜 / 대안)

외부 의존은 없다(표준 라이브러리만).

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

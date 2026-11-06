# agent-console-safe-zip

사용자가 올린 zip을 **디스크에 풀지 않고** 메모리에서 상한 안에서 읽는 작은 라이브러리(design §5.7R.8·§7R.13).
메모리 마크다운 가져오기(`ac-memory`)와 위키 페이지 가져오기(`ac-wiki`)가 같은 안전 규칙을 여기서 쓴다(같은
검사를 두 벌 두지 않는다). 표준 라이브러리 `zipfile`만 쓴다.

- 묶음 전체 거부(`ZipLimitError`, `limit` = 넘은 상한 이름): 압축 크기·항목 수·항목 하나의 선언 크기·선언 크기
  합. 실제로 풀린 바이트도 상한으로 끊는다(머리 크기 거짓말 대비).
- 형식 오류(zip이 아님): `ZipFormatError`.
- 항목 하나만 표시(`ZipMember.kind`): `unsafe`(`..`·`.`·빈 마디·절대 경로·드라이브 문자·역슬래시·제어 문자·
  심볼릭 링크 — 읽지 않음), `encrypted`, `broken`(압축 데이터 깨짐), `dir`, `file`(바이트 있음). 무엇을 받을지
  (확장자·위치 규칙)는 호출자가 정한다.
- 쓰기 `write_zip`: 경로 순·고정 시각·deflate·권한 0644 — 같은 입력이면 같은 바이트.

## 설치

```bash
pip install agent-console-safe-zip
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-safe-zip
```

## 최소 사용

```python
>>> from agent_console_safe_zip import ZipLimitError, ZipLimits, read_zip, write_zip

>>> data = write_zip([("notes/a.md", b"# A\n"), ("b.md", b"B")])
>>> [(m.name, m.kind, m.data) for m in read_zip(data)]
[('b.md', 'file', b'B'), ('notes/a.md', 'file', b'# A\n')]

>>> try:
...     read_zip(data, ZipLimits(max_file_bytes=2))
... except ZipLimitError as exc:
...     print(exc.limit)
max_file_bytes

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

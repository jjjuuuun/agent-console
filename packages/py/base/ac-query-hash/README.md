# agent-console-query-hash

검색 이벤트에 남길 검색어 해시를 만든다. 검색어는 짧은 경우가 많아 솔트 없는 sha256이면 사전 대입으로 원문을
되찾을 수 있으므로 기본은 솔트 HMAC-SHA256이다. 표준 라이브러리만 쓴다. 방식과 솔트는 쓰는 쪽이 정해 넘기고
(예: 설치자 설정 + 환경변수), 이 패키지는 솔트를 저장하거나 출력하지 않는다.

- `query_hasher(mode="hmac", *, salt=None, random_bytes=secrets.token_bytes)`: 검색어 → 16진수 해시(또는 None).
  - `hmac`: HMAC-SHA256(솔트, 검색어). 솔트가 없거나 비면 만들 때 무작위 32바이트(그 해셔 안에서만 같은 값).
  - `sha256`: 솔트 없는 sha256(설치를 넘어 같은 값이 필요할 때).
  - `off`: 늘 None(해시를 싣지 않음).
- `query_hasher_from_env(mode, *, salt_env, environ)`: 설정 값(방식 + 솔트 환경변수 이름)으로 만든다. 변수가 없거나
  비면 무작위 솔트. `environ`은 주입한다(보통 `os.environ`).
- `QueryHasher`: `Callable[[str], str | None]`. 도구 묶음은 이 모양만 받는다.
- `QueryHashModes`·`QUERY_HASH_MODES`: 방식 이름(설정 검증·화면 선택지).

## 설치

```bash
pip install agent-console-query-hash
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-query-hash
```

## 최소 사용

```python
>>> import hashlib
>>> from agent_console_query_hash import QUERY_HASH_MODES, query_hasher
>>> QUERY_HASH_MODES
('hmac', 'sha256', 'off')
>>> keyed = query_hasher("hmac", salt=b"from-env")
>>> keyed("plan") == keyed("plan") != query_hasher("hmac", salt=b"other")("plan")
True
>>> query_hasher("sha256")("plan") == hashlib.sha256(b"plan").hexdigest()
True
>>> query_hasher("off")("plan") is None
True
>>> from agent_console_query_hash import query_hasher_from_env
>>> from_env = query_hasher_from_env("hmac", salt_env="MY_SALT", environ={"MY_SALT": "from-env"})
>>> from_env("plan") == keyed("plan")
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

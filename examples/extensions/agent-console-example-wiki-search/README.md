# agent-console-example-wiki-search

위키 검색 방식(색인)을 **플러그인 패키지 하나**로 더하는 예제이자 작성 가이드.
엔진·서버·웹 코드를 고치지 않는다. 설치하고 설정에서 고르면 위키 검색이 이 색인으로 돌고, 고르지 않거나
제거하면 mod-wiki 기본 방식(설치자 `search.backend`, 없으면 `search.fallback`)으로 돌아간다.

검색 방식 `example-inverted`
- 본문을 낱말로 나눠 `낱말 -> 경로 집합` 역색인을 **메모리에** 둔다. 외부 서비스·파일이 없고, 프로세스가
  끝나면 사라진다(서버가 시작할 때 페이지에서 다시 채운다 — 색인은 다시 만들 수 있는 캐시다).
- 질의 낱말은 색인된 낱말 중 그것을 포함하는 것을 찾는다(부분 일치: "위키는" 안의 "위키"). 모든 낱말이
  경로·제목·태그·별칭·본문 중 어디에든 있어야 한다. 점수·조각·강조 범위(`marks`)는 계약과 같다.
- 낱말 나누기 규칙은 옵션 데이터다(기본값 `data/defaults.json`): `tokenizer`가 이름 표(`tokenizers`)에서 정규식을
  고르거나 `token_pattern`으로 직접 준다. 기본(`whitespace`)은 부분 문자열 검색과 결과가 같다. `word`처럼
  다른 규칙은 낱말 경계에 걸친 질의(`a-b`)를 놓칠 수 있다.
- 의존: 계약(`agent-console-contracts`)·위키 라이브러리(`agent-console-wiki`, 색인 프로토콜·`search_marks`)·
  `agent-console-secret-rules`(색인에 넣기 전 비밀 가리기). 서버 모듈(`mod-wiki`)은 import하지 않는다(테스트에서만 쓴다).

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 색인 만드는 법

색인은 `agent_console_wiki.WikiSearchIndex` 프로토콜(`id`·`degraded`·`hashes`·`update`·`remove`·`rebuild`·`search`·
`close`)을 지킨다. 등록하는 쪽은 **공장** `(root, options) -> 색인`이다. `root` = 색인 파일 위치(파일을 쓰지 않으면
무시), `options` = 설치자·사용자 설정에서 온 값(`tokenizer`·`case_insensitive`·`max_results`와 이 예제가 읽는 값).

서버 없이 이 예제 색인만 쓰기:

```python
>>> from agent_console_example_wiki_search import make_index
>>> from agent_console_wiki import WikiSearchDocument
>>> index = make_index({"case_insensitive": True})
>>> index.update([WikiSearchDocument(path="guide/intro", title="소개", text="이 위키는 팀의 약속을 적는다.",
...                                  content_hash="h1")])
1
>>> index.update([WikiSearchDocument(path="guide/intro", title="소개", text="이 위키는 팀의 약속을 적는다.",
...                                  content_hash="h1")])
0
>>> hit = index.search("위키").items[0]
>>> (hit.path, hit.snippet, [(m.start, m.end) for m in hit.marks])
('guide/intro', '이 위키는 팀의 약속을 적는다.', [(2, 4)])
>>> index.search("없는낱말").items
[]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

규칙
1. **옵션은 데이터**: 낱말 나누기 규칙처럼 바뀔 수 있는 값은 코드에 두지 않고 옵션(패키지 데이터 기본값 +
   설정 덮어쓰기)으로 받는다. 모르는 옵션 값(mod-wiki가 넘기는 `tokenizer: trigram` 등)은 기본으로 돌린다.
2. **의미는 계약 묶음이 정한다**: 모든 낱말이 맞아야 하고, 점수는 제목 8·경로 4·태그/별칭 4·페이지당 1, 같으면
   경로 순. 본문은 점수에 세지 않는다(색인마다 순서가 같도록).
3. **비밀은 색인에 넣기 전에 가린다**: 색인에 원문이 없어야 한다(조각·검색 모두).
4. **`update`는 해시가 같으면 건너뛴다**: 증분 갱신 키는 `content_hash`.
5. **스레드 안전, `close` 여러 번 허용, 공장의 예외는 mod-wiki가 잡는다**(색인 없이 동작).

## 등록

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console.wiki_search_indexes`(`agent_console_wiki.SEARCH_INDEX_GROUP`),
이름 = 검색 방식 id. **값은 인자 없는 함수**이고, 이 함수가 공장 `(root, options)`를 돌려준다.

```toml
[project.entry-points."agent_console.wiki_search_indexes"]
"example-inverted" = "agent_console_example_wiki_search:index_factory"
```

서버 시작 때 mod-wiki의 호스트 플러그인 로더가 이 그룹을 읽는다. 쓸 방식은 이 순서로 고른다:
사용자 설정 `wiki.search_backend` → 설치자 `search.backend` → 설치자 `search.fallback`.
**설치만으로는 쓰이지 않는다** — 둘 중 한 곳에 `example-inverted`를 적어야 한다.

## 설정 예

사용자(워크스페이스) 설정, 화면 설정의 "위키" 섹션 `search_backend`:

```yaml
wiki:
  search_backend: example-inverted
```

또는 설치자 설정(`modules.options.mod-wiki.search`)으로 모든 사용자의 기본을 바꾼다:

```yaml
modules:
  options:
    mod-wiki:
      search:
        backend: example-inverted
        fallback: scan          # 못 쓸 때 대신 쓸 방식(비우면 색인 없이)
        tokenizer: whitespace   # 이 예제는 data/defaults.json의 이름 표에서 낱말 규칙을 고른다
```

| 옵션 | 기본(`data/defaults.json`) | 뜻 |
| --- | --- | --- |
| `tokenizer` | `whitespace` | 낱말 규칙 이름(`whitespace`=`\S+`, `word`=`\w+`). 모르는 이름이면 기본 |
| `token_pattern` | 없음 | 낱말을 뽑는 정규식을 직접 지정(빈 문자열과 맞으면 거부) |
| `case_insensitive` | `true` | 대소문자 무시(mod-wiki가 위키 문법 값으로 채움) |
| `max_results`·`max_terms`·`max_term_chars`·`max_body_chars`·`snippet_chars` | 위키 라이브러리 기본 | 검색 상한 |

mod-wiki가 넘기는 옵션은 `tokenizer`·`case_insensitive`·`max_results`다. `token_pattern` 같은 나머지는 이 예제를 직접
만들어(`make_index({...})`) 쓸 때 받는다.

## 설치·제거

저장소 루트에서 실행한다. 서버와 같은 Python 환경에 설치한다. 서버를 다른 가상환경에서 돌리면
`--python <그 가상환경 경로>`를 붙인다(예: `UV_PROJECT_ENVIRONMENT`로 정했다면 `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-wiki-search   # 설치
uv pip uninstall agent-console-example-wiki-search                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치 + 설정에서 고름: 위키 검색 결과의 `backend`가 `example-inverted`.
- 제거: 설정에 남은 이름은 지워지지 않는다. 서버는 대체 방식(`search.fallback`)으로 검색하고 서버 경고
  `wiki.search_degraded`(위키 정보 `issues`)를 남긴다.
- 설치한 채 로드하지 않기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example-inverted`를 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로
mypy·pytest를 돌린다(`uv run poe examples`). 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`
(저장소에서 `uv run poe wheels`) 뒤 `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-wiki-search
uv run --project ../../.. python -m pytest
```

- `tests/test_wiki_search_contract.py`: `agent_console_wiki.testing.WikiSearchContractTests` 전체(부분 일치·대소문자·
  점수·접두/태그·증분 갱신·UTF-16 강조·비밀 가림 등).
- `tests/test_agent_console_example_wiki_search.py`: entry point 선언, 라이브러리 로더로 로드, 파일을 만들지
  않음, 강조 범위, 지운 문서의 낱말 표 정리, 낱말 규칙 옵션, 틀린 `token_pattern` 거부.
- `tests/test_mod_wiki_assembly.py`: 테스트 호스트 + `mod-wiki` 조립 — 사용자 `search_backend`·설치자
  `search.backend`로 고르면 검색이 이 색인으로 동작, 새 페이지도 찾음, 고르지 않으면 기본 방식, 없는 이름이면
  대체 방식 + `wiki.search_degraded`.

자기 색인을 만들 때도 같은 방식으로 `WikiSearchContractTests`를 상속해 `make_index`만 채운다.

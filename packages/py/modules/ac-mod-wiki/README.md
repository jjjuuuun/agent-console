# agent-console-mod-wiki

Agent Console 위키 서버 모듈(`mod-wiki`, design §7R.3·§7R.7). `ac-wiki`(문법·파싱·링크 해석·색인·저장소·
규칙·점검·기록·검색·zip)를 서버에 붙인다. 실행·프로젝트를 모르고, 둘 다 연동 모듈이 포트로 붙인다.

- REST `/wiki/*`: 화면 정보 `GET /wiki/info`(페이지 폴더·능력·한도), 위키 목록·만들기·보기·저장·지우기
  (`/wiki/wikis[/{wiki}]`, 목록 카드 값 — 페이지·끊긴 링크·고아·점검 수·최근 변경 — 을 요청 하나로), 페이지
  (`…/pages[/{path}]`, `ETag` = 본문 sha256, 새 페이지 `If-None-Match: *`), 저장 전 시험 `…/preview`, 옮기기
  `…/move`(링크 문자열만 고침), 기록 `…/history[/{version}]`·`…/restore`, 링크 넣기 `…/link-text`, 페이지 틀
  `…/templates[/{id}/render]`, 검색·그래프·점검·변경(`?op=`·`?author_run=`, 공간 전체 `GET /wiki/changes`)·
  유효 문법·외부 변경 다시 읽기 `…/scan`, zip `…/export`(`Content-Disposition`)·`…/import`. 위키 규칙
  `/wiki/rules[/{id}[/files[/{path}]]]`·`POST /wiki/rules/check`(정의 모듈 없이도 동작). 모든 경로가
  `?project=<공간 이름>`을 받는다.
- WS 토픽 `wiki.changed`(본문 없음 — 화면은 다시 읽는다). 저장소는 알리지 않고 모듈이 결과를 보고 키트
  `LoopPublisher`로 낸다. 미리보기·`dry_run`은 알리지 않는다.
- 정의 종류 기여(X44): 위키 규칙(라이브러리·프로젝트, 여러 본문 파일 — 지침·페이지 틀)과 위키
  (`library=False`, 참조 추출 `rules` → 위키 규칙). 종류 이름·폴더 이름은 설치자 옵션(기본값은 패키지
  데이터 `data/defaults.json`).
- 사용자 설정 섹션 `wiki`(`include_default_syntax`·`syntax`·`secret_scan`·`max_versions_per_page`·
  `search_backend`·`write_checks`). 모르는 키는 보존하고, 깨진 부분만 빼고 `server.warnings`에
  `wiki.settings_invalid`로 알린다.
- 공간: `wiki.spaces`(선택, `link-projects-wiki`가 준다). 공간 이름이 없는 요청은 단독 루트
  (`standalone_root`, 기본 워크스페이스 안 `wiki/`). 이름이 왔는데 연동이 없으면 409
  `wiki.spaces_unavailable`. 단독 공간의 위키 규칙은 앱 라이브러리(`definitions.store`에 규칙 종류가
  있을 때)를 읽고, 없으면 단독 루트를 읽는다.
- 기록(X49): 계보 `wiki`(리비전은 `ac-wiki.sqlite`가 소유, 범위 `app`·`project`). 단독 공간 = 호스트 DB
  (메모리 DB이거나 DB가 없으면 프로세스 메모리), 프로젝트 공간 = `records.spaces`의 그 폴더 기록 DB(없으면
  기록 없음 — 호스트 DB에 대신 쓰지 않는다).
- 검색(X48): 사용자 `search_backend` → 설치자 `search.backend`(기본 `sqlite-fts`) → `search.fallback`
  (기본 `scan`). 색인 파일은 프로젝트 공간이면 공간이 준 `index_dir`, 단독이면 호스트 상태 폴더
  `wiki-index/`. 대체 방식이면 `GET /wiki/info`에 `wiki.search_degraded`.
- 쓰기 검사(X50): 포트 `wiki.write_checks`(늘 켜짐, 설정 `enabled: false`로 끔) + entry point
  `agent_console.wiki_write_checks`(설정 `wiki.write_checks[{id, enabled, options}]`로 켬, 값 = 검사 객체
  또는 옵션을 받는 공장).
- 능력 `WikiInfo.capabilities`는 포트 유무로 계산한다(`runs` = `wiki.integrations`에 `runs`를 낸 연동).

코드에 고정된 것: 머리말 역할·기본 점검·링크 대상 찾기의 뜻(`ac-wiki`), 쓰기 규칙을 거는 길(도구·화면·
REST — 파일을 직접 고친 것은 다음 읽기·`scan`에서 `external` 기록과 점검의 규칙 위반으로 보인다), 원본 =
파일. 페이지 경로의 마지막 구성요소가 `history`(또는 `history/<수>`)인 페이지는 `GET`으로 읽을 수 없다
(기록 경로와 겹침, `PAGE_ROUTE_WORDS`).

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-wiki[sqlite]`(위키 핵심·SQLite 기록·FTS5 색인), `agent-console-store`(정의
  저장소·버전·기록 DB 모양), `agent-console-conditions`(쓰기·점검 규칙 연산자), `agent-console-registry`
  (X48·X50 플러그인), `agent-console-secret-rules`(본문·정의 비밀 검사), `agent-console-safe-zip`(zip 상한),
  `agent-console-modkit[host]`(모듈·호스트). 새 외부 의존 없음(FastAPI·pydantic은 다른 모듈과 같다).

## 설치

```bash
pip install agent-console-mod-wiki
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-wiki
```

## 최소 사용 (모듈 하나 + 단독 루트)

```python
>>> import tempfile
>>> from pathlib import Path
>>> from fastapi.testclient import TestClient
>>> from agent_console_mod_wiki import module
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app

>>> tmp = Path(tempfile.mkdtemp())
>>> base = BaseServices(paths=Paths(base_dir=tmp, workspace=tmp / "ws", state=tmp / "state"))
>>> assembly = assemble([module], base=base)
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> client = TestClient(create_host_app(assembly, policy=policy))
>>> client.headers["X-Console-Token"] = "t" * 32
>>> with client:
...     print(client.get("/api/v1/wiki/wikis").json())
...     wiki = client.post("/api/v1/wiki/wikis", json={"name": "Notes"}).json()["wiki"]["id"]
...     page = client.put(
...         f"/api/v1/wiki/wikis/{wiki}/pages/index",
...         json={"content": "# Home\n\n[[other]]\n"},
...         headers={"If-None-Match": "*"},
...     ).json()
...     print(wiki, [(link["target"], link["status"]) for link in page["links"]])
[]
notes [('other', 'broken')]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

단독 실행: `python -m agent_console_mod_wiki [--with ID] [--config PATH] [--port 0] [--check]`. 사용자
설정은 워크스페이스 `settings.yaml`의 `wiki` 섹션. 정의 버전·페이지 기록은 `<state>/console.sqlite3`.

## 포트

| 포트 | 방향 | 모양 |
| --- | --- | --- |
| `wiki.service` | 제공 | `WikiServicePort`: `settings()`·`wiki_ids(space)`·`repository(space, wiki)`·`tool_targets(space)`·`notify(space, wiki, paths)` (+ 구현 `WikiService`의 `scope(space)`) |
| `definitions.kind_contributions` | 제공(여러) | `KindContribution(DefinitionKind, references)` 두 개 |
| `server.warnings` | 제공(여러) | 설정 형식 문제·설치되지 않은 쓰기 검사 |
| `wiki.spaces` | 선택 | `WikiSpaces.open(space) -> WikiSpace{store, config_writable, pages_root[, pages_dir, config_dir, index_dir]}` |
| `records.spaces` | 선택 | `agent_console_store.RecordsSpaces`(공간 이름 = `records_space_prefix` + 프로젝트 id) |
| `wiki.write_checks` | 선택(여러) | `agent_console_wiki.WikiWriteCheck{id, check(subject, text)}` |
| `wiki.integrations` | 선택(여러) | `WikiIntegration{id, capabilities}`(`runs` → `capabilities.runs`) |
| `workspace.settings`·`secrets.rules`·`definitions.store` | 선택 | 설정·비밀 규칙·라이브러리 |

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

# 변경 기록

## 미출시 (0.2.0)

- P1.19: The kind contributions carry `open_role` (wiki `wiki`, wiki rules `wiki:rules`, `WIKI_OPEN_ROLE` and `RULES_OPEN_ROLE`), so the copy dialog kind list (`CopyKindInfo.open_role`, contracts 0.16.0) can offer "Open" for these rows.
- P1.15: Added the freshness window, administrator option `freshness_seconds` (default `2.0`, `0` = check on every request as in 1.0.0). Inside the window the service reuses the last fingerprint check per space and wiki (wiki definition, rule versions, user settings, write checks, secret rule signature; the space values are still compared on every request), and the repository reuses its page listing (`agent-console-wiki` `WikiRepository(freshness_seconds=)`). Concurrent opens of the same wiki check once. Changes made through this server show at once: page writes (`notify` also drops the listing), wiki definition create/save/delete, wiki rule create/save/delete, rule body file writes/deletes, and rule version restores (`WikiService.rules_changed`), and the optional topic subscription `definitions.saved` (`WikiService.on_definition_saved`; wiki or rules kind = that space, other kinds = all). `POST …/scan` and the periodic scan ignore the window. Files edited outside the app can show up to the window late. Cards (`GET /wiki/wikis`) and `GET /wiki/wikis/{id}` read the wiki definition once per request instead of twice. New: `WikiService.repository_of(..., fresh=)`, `ports.DEFINITIONS_SAVED`. Consumer range: `agent-console-mod-wiki>=0.2,<0.3`; requires `agent-console-wiki>=0.2,<0.3`.
- REL.16(계약 0.15.0, wiki 1.3.0): `GET …/graph?depth=all`(계약 `WIKI_GRAPH_DEPTH_ALL`) — 깊이 제한 없음, 생략은
  그대로 1, 그 밖은 0 이상의 정수(아니면 422). `GET /wiki/info`가 `wiki_kind`(위키 정의 종류 이름)와
  `reserved_page_names`(`PAGE_ROUTE_WORDS`, `GET`으로 읽을 수 없는 마지막 경로 조각)를 채운다. `PAGE_ROUTE_WORDS`는
  `service`로 옮겼다(공개 이름·`routes`에서의 import는 그대로).
- FU.23: 색인 공장 옵션에 지금 비밀 의심 규칙(`secrets.rules`, 사용자 규칙 포함)의 가리기 `redact`와 서명
  `redact_signature`(`service.secret_rules_signature`)를 넘긴다(전에는 색인 구현이 기본 규칙으로만 가렸다). 규칙이
  바뀌면 저장소·색인을 다시 짓는다. 색인 캐시 키에는 함수 대신 서명이 들어간다.
- FU.19: 설치자 옵션 `search.index_options`(검색 방식 이름 → 그 방식이 받는 옵션, 예: `token_pattern`). 고른
  방식의 옵션을 색인 공장에 넘긴다(전에는 `tokenizer`·`case_insensitive`·`max_results`만 넘겼다). 앱 값
  `case_insensitive`·`max_results`는 덮이지 않는다. `WikiSearchOptions.factory_options(backend)`.
- FU.12: 설치자 옵션 `query_hash`(`hmac` 기본·`sha256`·`off`)·`query_hash_salt_env`(솔트 환경변수 이름) —
  에이전트 위키 검색 이벤트 `query_sha256`. 기본이 솔트 없는 sha256에서 서버를 켤 때마다 무작위 솔트 HMAC으로
  바뀌었다. `WikiService(query_hash=)`·`WikiService.query_hash`, `search_query_hasher(cfg, environ)`.
- FU.5: `unique_id`는 `agent_console_store.unique_id`를 다시 내보낸다(사본 삭제, 규칙 그대로).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 7R.12: 위키 서버 모듈 — REST `/wiki/*`(위키·페이지·미리보기·옮기기·기록·되돌리기·링크 넣기·틀 렌더·
  검색·그래프·점검·변경·문법·scan·zip, 위키 규칙), WS `wiki.changed`, 정의 종류 기여(위키·위키 규칙),
  사용자 설정 섹션 `wiki`, 포트 `wiki.service`·선택 `wiki.spaces`·`records.spaces`·`wiki.write_checks`·
  `wiki.integrations`, 계보 `wiki`(app·project), X48·X50 호스트 플러그인 로더, 단독 실행.
- 계약 0.14.1 후속: `GET /wiki/info`가 `writable`(공간 `config_writable`, 단독 공간은 true)을 채운다.
- 계약 0.14.2 후속: 위키 규칙 버전 경로 `GET /wiki/rules/{id}/versions[/{hash}]`·`…/versions/{hash}/files[/{path}]`·
  `POST …/versions/{hash}/restore`(`/sdd/templates`와 같은 모양, 본문 파일 비밀 검사·읽기 전용 공간 409),
  `GET /wiki/info`가 `rules_kind`를 채운다.
- FU.1: 위키 폴더를 `LocalWikiPages(within=)`로 연다(프로젝트 = 공간 `folder`, 단독 = 단독 루트 폴더 —
  `WikiService(standalone_boundary=)`). 기준 폴더는 만들지 않는다. 공간을
  연 뒤 위키 폴더가 밖을 가리키는 링크로 바뀌어도 밖을 읽거나 쓰지 않는다.

# 변경 기록

## 미출시

- FU.17: `WikiIssueCodes.UNKNOWN_TITLE_SOURCE`·`REDACTED_CONTENT`가 계약 0.14.11(`common` 1.16.0)
  `KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE`·`WIKI_REDACTED_CONTENT`의 별칭이 되었다(값·공개 이름 그대로).
  이벤트 상태 `WikiEventStatus`는 그대로(`secret_rejected` + 사유 코드).
- FU.14: 마크다운 링크 규칙이 참조 링크(`[글][이름]`·`[이름][]`·`[이름]` + 정의 `[이름]: 경로`)도 읽는다 — 그래프·
  백링크·이름 바꾸기(정의 줄 경로를 한 번만 고침)에 들어간다. `ParsedLink.reference`(정의 이름 키), 내부
  `scan_inline(text, references)`.
- FU.14: 문법 `title_sources`의 모르는 값에 warning `wiki.unknown_title_source`(`/title_sources/<i>`, 규칙 검사에도
  `/syntax/...`로). 전에는 이슈 없이 건너뛰었다.
- FU.14: 가린 본문 다시 쓰기 막기 — `compose_write`가 기존 페이지의 새 본문에 가린 비밀 표시가 새로 들어 있으면
  `WikiRedactedContentError`(`wiki.redacted_content`, `details.lines`)를 던지고, 도구는 같은 사유 코드(이벤트 상태
  `secret_rejected`)로 돌려준다. 읽기 결과에 가린 곳이 있으면 안내 줄(`tool_text.yaml` `read_redacted`). 새 공개
  `WikiSecretPolicy.reused_redactions`·`redaction_marks`·`WikiIssueCodes`(계약 후보 코드).

- FU.12: `WikiToolkit(query_hash=)` — 검색 이벤트 `query_sha256`의 기본이 솔트 없는 sha256에서 묶음마다 무작위 솔트
  HMAC-SHA256으로 바뀌었다(`query_hasher("sha256")`으로 옛 값, `off`면 싣지 않음). `query_hasher`·
  `query_hasher_from_env`·`QueryHasher`·`QueryHashModes`·`QUERY_HASH_MODES`는 `agent-console-query-hash`를 다시
  내보낸 것.
- FU.5: 페이지 글롭은 `agent-console-path-glob`, 쓰기 한도 `WriteBudget`은 `agent-console-write-budget`을 쓴다(다시 내보냄,
  `WikiWriteBudget` = `WriteBudgetLike`). 동작 그대로.

## 0.1.0

- FU.1: `LocalWikiPages`가 링크 바꿔치기(TOCTOU — 검사한 뒤 열기 전에 폴더가 링크로 바뀜)를 막는다. 디렉터리 fd를
  쓸 수 있는 OS는 한 칸씩 `O_NOFOLLOW`로 열어 내려가 그 fd 기준으로 읽기·쓰기·지우기·옮기기·목록을 하고, Windows는
  연 뒤 다시 확인한다(링크·실제 경로 + `fstat` 동일성). 새 선택 인자 `within`(루트가 들어 있어야 하는 기준 폴더 —
  루트가 그 안을 가리키는 링크인 것은 된다). 루트 자체가 링크면 목록도 따라간다(읽기·쓰기와 같게).

- 에이전트 도구 묶음(7R.10): `WikiToolkit`(도구 7개 — search·read(절)·list·links·write(replace·append·section·
  template)·move·delete, 위키별 접근·`wiki.denied`·`wiki_unavailable`, 사유 코드, 본문 없는 이벤트, 결과 가림·
  최대 글자, `WriteBudget`), 지침 `instructions()`·`wiki_instructions`, 문구 데이터 `data/tool_text.yaml`
  (`WikiToolText`), 절 함수 `section_span`·`replace_section`.

- 쓰기 방식 공개(7R.17): `compose_write`·`PageComposition`·`WIKI_WRITE_MODES`(도구 `write`가 같은 함수를 쓴다),
  예외 `WikiSectionNotFoundError`(`wiki.not_found`, `reason=section_not_found` — 도구 사유 코드는 전과 같음),
  `wiki_failure`·`WikiFailure`(저장소 예외 → 이벤트 상태·사유 코드).

- SQLite 기록 저장소(7R.11): `sqlite.SqliteWikiHistory`(표 `wiki_page_versions`·`wiki_blobs`, 블롭 공유, 원자적
  `record`, `prune` 고아 블롭 삭제, 공간 전체 `changes`), 계보 `wiki`의 리비전 폴더 `sqlite.MIGRATIONS_DIR`·
  `BRANCH_NAME`(`wiki_0001`), 선택 의존 `sqlite`.

- 저장소·규칙·점검·기록(7R.8): `merge_rules`·`check_rules`·`load_wiki_rules`·`definition_kinds`, 쓰기 판단
  `check_write`·`WikiSecretPolicy`·X50 `WikiWriteCheck`, 점검 `lint`(쓰기 규칙 다시 보기 포함), 틀
  `render_page_template`, 기록 X49 `WikiHistory`·`InMemoryWikiHistory`·`WikiHistoryContractTests`,
  `WikiRepository`(쓰기·미리보기·옮기기·지우기·되돌리기·`scan`), `export_zip`·`import_zip`, `read_pages(cache=)`,
  `WikiIndex.resolve_page`·`link_views`, 예외 8종, `WikiPageNotFoundError.has_history`.

- 검색 색인 X48(7R.9): `WikiSearchIndex` 프로토콜, `ScanSearchIndex`, `sqlite.SqliteFtsSearchIndex`(FTS5
  trigram, `unicode61`·훑기 폴백 + `degraded`), 해시 증분 갱신, 비밀 가린 조각 + UTF-16 `marks`, 플러그인 로더
  `load_search_plugins`, 계약 묶음 `WikiSearchContractTests`.

- 처음 만듦(7R.7): 위키 문법 데이터(패키지 기본·층 병합·출처·끄기·컴파일), 페이지 파싱(머리말·제목 출처·
  태그·별칭·제목들·링크 원문 위치, 코드 블록·인라인 코드 제외), 링크 색인(해석 순서·대소문자·백링크·끊긴
  링크와 만들 경로 제안·바깥 링크·스킴·고아·제목 겹침), 그래프 주변, 링크 대상만 고치는 이름 바꾸기, 링크
  넣기 글, 판단 대상 만들기, 검색 강조, 페이지 파일 접근(`WikiPages`·`LocalWikiPages`·`read_pages`), 시험
  도구(`MemoryWikiPages`·`WikiPagesContractTests`).
- 계약 0.14.1 후속(코드 변화 없음): `WikiSecretPolicy()` 기본 방식은 계약 `WikiSettings` 기본값을 읽으므로 이제
  `system`도 `reject`다(보안 강화). 위키 고치기 노드처럼 앱이 대신 쓰는 본문의 비밀 의심 값을 거부한다.
- 계약 0.14.2 후속: 합친 규칙 항목에 `applies_to`·`path`·`title`, `lint()`가 페이지 하나의 실패를 건너뛰고
  (`partial`·`skipped`·이슈 `wiki.lint_failed`) 켜진 점검 이름(`enabled_checks`)을 낸다, 그래프 스킴 칸에
  `scheme_target`.

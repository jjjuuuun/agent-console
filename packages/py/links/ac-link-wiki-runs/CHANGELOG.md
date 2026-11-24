# 변경 기록

## 미출시

- FU.12: 위키 도구 묶음에 검색어 해셔를 넘긴다 — 서비스의 선택 속성 `query_hash`(`QueryHashSource`,
  `service_query_hash`)가 먼저, 없으면 `WikiRunScope(query_hash=)`(기본: 범위 하나에 무작위 솔트 해셔 하나).
  `WikiToolProvider(query_hash=)`.
- FU.5: `merge_access`가 `agent_console_nodes_core.merge_access_layers`로 합친 뒤 검증만 한다(메모리 연동과 같은 규칙, 동작 그대로).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`, 7R.14).
- 리소스 종류 `wiki`(패키지 데이터 `data/wiki_resource_type.yaml`, 설정 스키마 = 계약
  `WikiAccessConfig`), entry point `agent_console.resource_types`.
- X30 공급자 `WikiToolProvider`(층 합치기 `merge_access`, 그 실행 공간의 위키만, 지침 =
  `WikiToolkit.instructions()`, 쓴 주체 `author_for`(+ 에이전트 정의 이름 `label`), 도구 호출마다
  RunEvent `wiki.*`, 성공한 쓰기·옮기기·지우기 뒤 `notify`, 공간에 없는 위키 경고
  `wiki.wiki_unavailable`), 실행 범위 `WikiRunScope`(`runs.scopes`, 루트 Run마다 공급자·쓰기 한도),
  저장 전 검사 `WikiResourceCheck`(`definitions.checks`, 모르는 위키 id 경고 `wiki.unknown_wiki`),
  `wiki.integrations` 선언 `{runs}`. `wiki.service` 필수, `projects.lookup` 선택.
- 설정 `max_writes_per_run`(기본 100). 단독 실행용 `testing.wiki_service_module`·`StaticWikiService`·
  `memory_repository`.
- 노드 종류 `wiki-update`(7R.17, entry point `agent_console.node_types`): LLM 없이 앞 노드 결과를 위키 페이지에
  쓴다(`WikiUpdateNode`·`WikiUpdateConfig` — 위키·경로 틀·`mode` append·section·replace·절 제목·내용 틀·새 페이지
  틀·기록 메모, 틀 = `ac-text-template`, 변수 `WIKI_UPDATE_VARIABLES`·`render_values`). 쓴 주체 `system`
  (`label` = 노드 id, `system_author`). 노드 서비스 `WIKI_UPDATE_SERVICE`를 `runs.services`(`WikiNodeServices`)로
  준다. 서비스가 없으면 검증 경고·실행 때 건너뜀(`wiki.update_unavailable`). 새 사내 의존
  `agent-console-text-template`.
- 계약 0.14.1 후속: `WikiUpdateCodes.UNAVAILABLE`이 계약 문서 상수 `KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE`을 쓴다(값 같음).
  설정 `wiki`·`page_template` id 검증은 복사한 정규식 대신 계약 공개 별칭 `Slug`(모양 같음). 계약 기본값 변경으로
  설정을 고치지 않은 workspace에서 이 노드(쓴 주체 system)의 평문 비밀 쓰기는 거부된다(전: 경고 후 저장).

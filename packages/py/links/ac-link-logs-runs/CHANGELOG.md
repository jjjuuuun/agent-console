# 변경 기록

## 미출시

- 5.7R.7(M-2): 대응표 목록 값 `{each: <목록 포인터>, ...항목 틀}` — `tags`·`correlation` 값·새 키
  `documents`(문서 틀 하나 또는 목록, `LogDocumentRef` 모양). 항목 틀 안 `{./키}`·`{.}`·`pointer: ./키`는
  원소 기준, 빈 항목은 빼고 같은 항목은 한 번. 순수 함수 `resolve_strings`·`resolve_documents`, 상수
  `EACH_KEY`·`DOCUMENT_FIELDS`. 기본 대응표 `agent.context_prepared`가 붙은 리소스를 문서로 옮긴다(종류
  `rule` → 문서 종류 `rules`, 규칙이 첫 문서). 기존 값 형식은 같은 뜻.
- 5.5R.11: 로그 범위 종류(X27) `run`·`run-tree`를 포트 `logs.scope_kinds`로 등록(`RunScopeKind`·`run_scope_kinds`·`run_sessions`·`run_tree_ids`). 소비 프로토콜 `RunReader.list`에 `parent_run_id`, `testing.run_record(parent_run_id=)`. `/runs/{id}/logs`는 그대로(세션 계산을 `run_sessions`로 옮김).
- 5.2R.34: 대응표 규칙 필드 `cwd_from`(포인터) — 알린 Run 작업 폴더를 그 뒤 같은 Run 이벤트의 `cwd`로(커서 `state.cwd`). 기본 대응표
  `run.started: cwd_from: /payload/cwd`.
- 5R.14: 대응표 데이터에 `run.child_started`·`run.child_finished`(자식 Run 상태, `child_run` 상관)·`edge.skipped`·`loop.iteration`·`loop.exhausted` 규칙과 `node.started`(호출 NodeRun이면 위임자 → 대상 넘김, via `delegate`)를 더했다. 자식 Run도 출처 `platform-runs`의 Run 단위로 읽힌다(테스트).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- 런타임 로그 출처 `platform-runs`(분류기 `platform-run-event`, 대응표 데이터 `run_event_map.yaml` + 설정 `event_map`), `runs.event` 구독 수집 예약(디바운스), `GET /runs/{id}/logs`(`total` 채움), 웹 역할 `logs:runs`(4R.11).

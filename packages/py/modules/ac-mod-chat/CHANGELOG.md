# 변경 기록

## 0.1.0

- 요청 11/08 후속: 대화 위치 찾기(`SpacedChatService.locate`)의 후보·기억 정책을 `agent_console_store.SpaceLocator`로 옮겼다(실행 위치 찾기와 공유). 동작·설정·`DEFAULT_LOCATE_LIMIT` 이름은 같다.
- 요청 11/07 후속: `GET /conversations/{id}/locate`(`ConversationLocation`, 계약 0.14.7) — 대화 id → 그 대화가 있는 기록 공간(이 프로세스에서 연 공간 + 선택 포트 `projects.lookup`의 등록 프로젝트 기록 DB를 상한 `locate_max_projects`(기본 200)까지 읽기만, 앱 기록 = null). 없으면 404, 여러 곳이면 409 `conversation.ambiguous`(`ConversationAmbiguousError`). 상세 `GET /conversations/{id}`는 그대로(`?project=` 없이 다른 공간을 대신 읽지 않음). WS `conversation:<id>`도 `service_of` → `locate`로 아직 열지 않은 프로젝트 기록 DB의 대화를 찾는다(작업 스레드에서). 새 모듈 설정 `locate_max_projects`.
- 6R.12: `GET /conversations/page`(`ConversationPage`, `cursor`·`limit`·`graph_id`·`archived`·`project`·`source`, 폴더 기록 끝 → `source=app` 잇기, Q14), 옛 `GET /conversations` OpenAPI deprecated, `InvalidCursor` → 400 `bad_request`.

- 5.7R.33j2: `POST /conversations/move-to-project`(앱 DB 옛 대화 + 대기열 → 프로젝트 기록 DB, `ConversationMover`), 선택 포트 `chat.move_hooks`(`MoveHook` - 딸린 기록 옮기기·옮긴 뒤 훅), `SqliteChatStorage.engine`. 표 변경 없음.
- 5.7R.33y2: 선택 포트 `records.spaces` — 프로젝트 대화·대기열을 그 기록 DB에(`SpacedChatService.for_project`), 대기열 `host_id`(다른 앱 항목 `other_host`), 경로 `?project=`·목록 `?source=app`, 모듈 설정 `records_space_prefix`(새 설정 스키마).
- 5.7R.33w2: 계보 `chat`에 `chat_0003`(`chat_queue.host_id`), 서술자 `scopes=("app","project")`.
- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 대화 조립(대화·턴·메시지·대기열 경로, WS `conversation:`)을 옮겼다(3R.14). 턴 실행·Run 조회·상호작용은 선택 포트 `chat.turn_launcher`·`chat.runs`·`chat.run_events`·`chat.interactions`로 받는다(없으면 전송 409 `feature_unavailable`). 
- 3R.15: 대화·대기열 저장소(SQLite·인메모리)를 `storage/`로 가져왔다(`ac-store`에서 제거). 마이그레이션 계보 `chat`(첫 리비전은 기준점, 테이블은 legacy 0002·0003 그대로). 대화 삭제는 대기열을 같은 트랜잭션에서 지운다.

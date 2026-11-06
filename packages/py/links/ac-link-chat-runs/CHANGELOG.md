# 변경 기록

## 미출시

- 5.7R.33j2: 선택 포트 `runs.move_hook`을 `chat.move_hooks`로 낸다(대화를 프로젝트 기록 DB로 옮길 때 그 Run도 함께).
- 5.7R.33y2: 대화 이어 가기·알림이 대화 서비스의 선택 메서드 `for_project(run.project_id)`를 쓴다, `RootInteractions.for_project`.
- 5R.13: `chat.interactions` = `RootInteractions`(턴 상호작용을 루트 Run 기준으로 — 자식 Run 요청 포함), `ConversationNotifier`가 자식 Run 이벤트를 루트 대화로 알린다. 소비자 포트 `interactions.port` 모양 `RootInteractionReader`.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `apps/server` 통짜 모듈의 대화 턴 시작(`RuntimeTurnLauncher`)·턴 이어 가기(`ConversationResume`, `runs.resume_handlers`)·`runs.event` 구독 알림·재시작 대기열 정책·종료 순서(대기열 멈춤 → `runs.starter.shutdown()` → 채팅 감시 정리)를 옮겼다(3R.14).

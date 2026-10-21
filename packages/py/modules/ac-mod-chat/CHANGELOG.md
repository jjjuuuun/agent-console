# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 대화 조립(대화·턴·메시지·대기열 경로, WS `conversation:`)을 옮겼다(3R.14). 턴 실행·Run 조회·상호작용은 선택 포트 `chat.turn_launcher`·`chat.runs`·`chat.run_events`·`chat.interactions`로 받는다(없으면 전송 409 `feature_unavailable`). 
- 3R.15: 대화·대기열 저장소(SQLite·인메모리)를 `storage/`로 가져왔다(`ac-store`에서 제거). 마이그레이션 계보 `chat`(첫 리비전은 기준점, 테이블은 legacy 0002·0003 그대로). 대화 삭제는 대기열을 같은 트랜잭션에서 지운다.

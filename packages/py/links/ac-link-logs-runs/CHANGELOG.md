# 변경 기록

## 미출시

- 5.2R.34: 대응표 규칙 필드 `cwd_from`(포인터) — 알린 Run 작업 폴더를 그 뒤 같은 Run 이벤트의 `cwd`로(커서 `state.cwd`). 기본 대응표
  `run.started: cwd_from: /payload/cwd`.
- 5R.14: 대응표 데이터에 `run.child_started`·`run.child_finished`(자식 Run 상태, `child_run` 상관)·`edge.skipped`·`loop.iteration`·`loop.exhausted` 규칙과 `node.started`(호출 NodeRun이면 위임자 → 대상 넘김, via `delegate`)를 더했다. 자식 Run도 출처 `platform-runs`의 Run 단위로 읽힌다(테스트).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- 런타임 로그 출처 `platform-runs`(분류기 `platform-run-event`, 대응표 데이터 `run_event_map.yaml` + 설정 `event_map`), `runs.event` 구독 수집 예약(디바운스), `GET /runs/{id}/logs`(`total` 채움), 웹 역할 `logs:runs`(4R.11).

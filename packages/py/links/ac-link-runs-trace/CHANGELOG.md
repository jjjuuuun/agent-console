# 변경 기록

## 미출시

- 5R.14: `/runs/{id}/trace`가 자식 Run(중첩 팀)의 흐름을 재귀로 붙이고(`TraceViews.trace(children=True)`), 호출 span의 연결(`call_edges`)·위임 과제(NodeRun 입력)를 채운다. `/runs/handoffs`는 Run마다 자기 흐름만 센다(자식 이중 집계 없음). 포트 `runs.reader`에 `list(parent_run_id=)`·`list_node_runs`를 쓴다.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `/runs/{id}/trace`·`/runs/handoffs`를 `apps/server`에서 옮겼다(3R.13). 당시 팀 구성은 선택 포트 `definitions.lookup`.

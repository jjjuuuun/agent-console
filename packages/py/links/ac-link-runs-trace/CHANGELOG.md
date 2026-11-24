# 변경 기록

## 미출시

- FU.3: `/runs/handoffs`·`/runs/{id}/trace`가 선택 `?project=`를 받는다(`TraceViews.in_project` — `runs.reader`·`runs.events`의 선택 메서드 `for_project`, 없으면 Run의 `project_id`로 거름 `ProjectRuns`). 모르는 프로젝트 404 `project.not_found`, 그 프로젝트 기록을 읽을 수 없음 409 `project.records_unavailable`(`ERROR_MAP`). 질의가 없으면 지금처럼(넘김 집계 = 호스트 기록, 흐름 = 실행 기록이 찾은 자리). 선택 포트 `definitions.spaces`: `project_id`가 있는 Run의 당시 팀 구성은 그 공간 저장소에서만 읽는다(`TraceViews(space_history=)`, 못 열면 연결 종류 없이).
- 5R.14: `/runs/{id}/trace`가 자식 Run(중첩 팀)의 흐름을 재귀로 붙이고(`TraceViews.trace(children=True)`), 호출 span의 연결(`call_edges`)·위임 과제(NodeRun 입력)를 채운다. `/runs/handoffs`는 Run마다 자기 흐름만 센다(자식 이중 집계 없음). 포트 `runs.reader`에 `list(parent_run_id=)`·`list_node_runs`를 쓴다.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `/runs/{id}/trace`·`/runs/handoffs`를 `apps/server`에서 옮겼다(3R.13). 당시 팀 구성은 선택 포트 `definitions.lookup`.

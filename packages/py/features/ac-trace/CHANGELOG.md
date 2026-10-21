# 변경 기록

## 미출시

- 5R.14: 호출 NodeRun(`call`) = 위임자 span 아래 별도 세션 `node` span(`call:<경로>#<call>`, 호출 회차마다), 위임자 → 호출 링크(`build_trace(call_edges=)`로 연결 id·종류), 위임 과제 미리보기(`node_runs=` 입력). 반복 회차마다 span(`node:<노드>#<시도>@<회차>`, `iteration`), 사이클 연결 통과는 다음 회차로 가는 링크. 자식 Run 묶음(`children=`, `run.child_started`가 가리키는 노드 span 아래, `run_id`·`child_span_id`). 넘김 출발은 그 노드의 가장 최근 span. 새 공개 함수 `call_span_id`·`child_span_id`, `node_span_id(…, iteration)`.

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.

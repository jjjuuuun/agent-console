# 변경 기록

## 미출시

- 5.2R.5: 검증 문구가 노드를 이름(label → 타입 title)으로 부른다. 노드·연결 id는 `node_id`·`edge_id`·`details`에만.
- 5R.12: `validate_graph(cycle_edge=)`를 주면 `cycle` 이슈에 "되돌아가는 연결을 사이클 연결 종류로 바꾸기" 제안(`remove_edge_ids` + `add_edges`)과 이름이 든 문구가 붙는다(맞는 종류가 없으면 지금 그대로).
- 5R.5: 반복 — 공개 술어 `descriptor_cycle_edge`(디스크립터 `cycle`), 순수 함수 `loop_regions(graph, edge_types) -> {edge_id: LoopRegion}`, `effective_max_iterations(edge, descriptor, settings_value)`, 상수 `CYCLE_LIMIT_CONFIG_KEY`(`max_iterations`).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.

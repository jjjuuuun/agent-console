# 변경 기록

## 미출시

- 5.2R.6: 매니페스트 선택 키 `featured`·`badges`·`start_graph`(`start_graph_id()` — 생략 = `default_entry`,
  null = 열지 않음). 항목 훑기 `collect_values`.

- 5.2R.31: `apply_preset(stamp=)` — 쓰는 항목(만듦·덮어씀·이름 바꿈)의 최상위 필드에 값을 찍는다(값 `None` =
  필드 빼기, 종류 모델이 선언하지 않은 필드는 찍지 않고 `warnings`). 도우미 `Stamp`·`stamp_fields`·`apply_stamp`.

- 5R.15: 적용 순서 `apply_preset(dependencies=ItemDependencies)`·`order_items` — 쓰는 정의(같은 프리셋 안)를
  먼저 쓴다. 없으면 매니페스트 순서(기존 동작).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.

# 변경 기록

## 미출시

- 5.2R.6: `GET /presets` 요약에 `badges`(매니페스트 + 쓰는 백엔드 디스크립터 `ui_hints.badge`)·`featured`·
  `start_graph`(항목에 없는 팀 구성이면 null)를 싣는다. `summarize`, `registry_backend_badge`, `PresetService(backend_badge=)`.

- 5.2R.31: 적용 요청 `project` → 만든 정의에 범위를 찍는다(`PresetService.apply(stamp=)`, `scope_stamp`).
  생략 = 공용(기존과 같다).

- 5R.15: 선택 포트 `definitions.dependencies`(`DocumentDependencies`) — 있으면 프리셋 항목을 쓰는 정의부터
  적용한다. `item_dependencies`, `PresetService(dependencies=)`.
- 4R.18: 옛 최상위 `presets`(그 아래 `set_default_entry` 포함) 읽기 호환 제거. 환경변수·`--apply-preset`은 그대로.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 `/presets`·`/presets/{id}/apply`와 시작 시 적용을 옮겼다(3R.10). 저장 전 검사는 포트 `definitions.checks`(multi). 설정 `modules.options.mod-presets`(옛 `presets.*`).

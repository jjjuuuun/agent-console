# 변경 기록

## 미출시

- REL.2: 토큰 집계(`IncrementalTokenRollups(batch=)`)와 이벤트 조회(`MergedEventQuery(batch=)`) 한 번을 `RecordsStores.batch` 블록 안에서 돈다(새 공개 이름 `Batch`). 프로젝트 12개·상한 8에서 집계 한 번 열기 12, 다음 집계 다시 열기 4(전에는 12). 목록과 공간 사이에 지워진 프로젝트(`UnknownSpace`)는 그것만 건너뛴다(전에는 뒤 프로젝트까지 빠졌다). 개발 의존 `agent-console-link-projects-records`(실제 풀 테스트).
- FU.11: "이 프로젝트" 토큰 집계(`rollups(project_id=)`)가 앱 기록에서 그 `project_id`의 최근 `limit`개를 저장소 조건으로 바로 읽는다(색인 `ix_runs_project_created`). 전에는 앱 기록 최근 `limit`개를 먼저 읽고 걸러서, 다른 실행이 많으면 옛 프로젝트 Run이 빠졌다. `runs.reader`에 선택 메서드 `for_project(None)`(앱 기록만, `mod-runs`)이 있으면 그것으로 읽는다(기록 공간이 있는 조립에서 `list(project_id=)`는 프로젝트 기록 DB를 읽으므로). 받는 모양 `AppRunSource`(+`project_id`), 선택 능력 `AppScopedRuns`.
- FU.11: 다시 읽을 Run을 출처마다 묶어 읽는다(선택 메서드 `list_many`·`list_node_runs_many`가 있으면 이벤트·NodeRun 각각 묶음 질의, 없으면 Run마다). 처음 집계 = 출처마다 목록·이벤트·NodeRun 질의 하나씩(전에는 Run마다 3번). 선택 능력 `BatchEvents`·`BatchNodeRuns`.
- 5R.13: 토큰 집계는 루트 Run만 센다(`ac-usage.counts_toward_usage`, 자식 Run 이중 집계 방지).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `usage.event_query`·`usage.token_rollups`를 `apps/server`에서 옮기고 토큰 집계를 증분 캐시(Run별 이벤트 seq 워터마크, `runs.event` 구독)로 바꿨다(3R.13, design §3R.5).

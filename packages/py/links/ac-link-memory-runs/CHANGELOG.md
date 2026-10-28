# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`, 5.7R.15).
- 리소스 종류 `memory`(패키지 데이터 `data/memory_resource_type.yaml`, 설정 스키마 = 계약
  `MemoryAccessConfig`), entry point `agent_console.resource_types`.
- X30 공급자 `MemoryToolProvider`(층 합치기 `merge_access`, 도구 호출마다 RunEvent `memory.*`),
  실행 범위 `MemoryRunScope`(`runs.scopes`, Run마다 공급자·쓰기 한도), 저장 전 검사
  `MemoryResourceCheck`(`definitions.checks`, 모르는 범위 종류 경고). `memory.service` 필수.
- 설정 `max_writes_per_run`. 단독 실행용 `testing.memory_service_module`.

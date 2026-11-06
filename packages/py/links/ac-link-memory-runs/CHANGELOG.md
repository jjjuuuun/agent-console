# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`, 5.7R.15).
- 리소스 종류 `memory`(패키지 데이터 `data/memory_resource_type.yaml`, 설정 스키마 = 계약
  `MemoryAccessConfig`), entry point `agent_console.resource_types`.
- X30 공급자 `MemoryToolProvider`(층 합치기 `merge_access`, 도구 호출마다 RunEvent `memory.*`),
  실행 범위 `MemoryRunScope`(`runs.scopes`, Run마다 공급자·쓰기 한도), 저장 전 검사
  `MemoryResourceCheck`(`definitions.checks`, 모르는 범위 종류 경고). `memory.service` 필수.
- 설정 `max_writes_per_run`. 단독 실행용 `testing.memory_service_module`.
- 5.7R.33z: 프로젝트 실행(`project_id` 있음)은 메모리 서비스의 `space(project_id)` 저장소만 쓴다(맥락 바꾸기는 공간 서비스가 적용). `space`가 없거나 실패하면 같은 도구 모양에 모든 호출 `memory.scope_unavailable` + 메모리 칸 노드 경고(`UnavailableMemoryService`·`space_service`). `testing.StaticMemoryService(spaces=...)`·`space`.

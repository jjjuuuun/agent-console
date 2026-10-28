# 변경 기록

## 미출시

- 5.7R.33w: `DefinitionKind.portable`·`is_portable`(프로젝트 사본 공간에 둘 수 있는 종류, 싱글턴·`settings`는 아님),
  쓰기 전 검사 훅 `WriteGuard`(`write_guard=`, `FileDefinitionStore`·`InMemoryDefinitionStore`), YAML 도구 공개
  (`load_yaml_text`·`dump_yaml`·`merge_into`·`wrap_value`·`to_plain`·`atomic_write_bytes`). 기존 동작·표 변경 없음.

- 5.2R.33: `LazyVersionRepository`·`versions_for(database)`(`ac-mod-definitions`에서 옮김). 같은 워크스페이스를 나눠 맡는 저장소 인스턴스(정의·프로젝트 모듈)가 같은 버전 기록소를 쓴다.
- 5.2R.31: 기본 종류 graph·agent·resource의 `summary_fields`에 범위 필드 `project`(`SCOPE_FIELD`, 공개).
  값이 있을 때만 요약 `extra`에 실린다. `list_graph_summaries`가 `GraphSummary.project`를 채운다.

## 0.1.0

- 5R.4: 실행 기록 계보 `runs`(소유는 `ac-mod-runs`). `RunRepository.list(root_run_id=)`(루트 아래 모든 자손), `InteractionRepository.list(root_run_id=)`(`root_run_id or run_id` 기준), NodeRun 키에 `call` 추가(인메모리·SQLite), `Run.root_run_id`·`parent_node_id`·`NodeRun.call`·`invoked_by`·`Interaction.root_run_id`를 열로 저장(있을 때만). `schema.runs_lineage_metadata`·`runs_lineage_active`, `MODULE_OWNED_TABLES`에 실행 기록 표 4개 추가. legacy 마이그레이션 0001~0003은 불변.

- 3R.15: 대화·채팅 대기열 저장소(`ConversationRepository`·`QueueRepository`·`QueuedItem`·`QueueCounts`, SQLite·인메모리, `SqliteStorage`/`InMemoryStorage`의 `conversations`·`queue`)를 `ac-mod-chat/storage`로 이동(공개 API 제거). 테이블·마이그레이션 0001~0003 불변, `MODULE_OWNED_TABLES`에 `conversations`·`chat_queue` 추가.

- 3R.12: `DefinitionStore.delete(..., expected_version=)`(삭제 If-Match, 다르면 `VersionConflict`).

- 3R.11: `SqliteDatabase`(DB 핸들: legacy + 모듈 계보별 upgrade, 계보마다 버전 테이블), `MigrationBranchLike`, `migrate.upgrade(versions=, version_table=)`. `usage_observations` 저장소(`storage.usage`, `UsageObservationRepository`)와 테이블 정의는 `ac-mod-usage/storage`로 이동(테이블·마이그레이션 0001~0003 불변). `schema.MODULE_OWNED_TABLES`·`include_object`.

- 3R.10: `ObservedVersionRepository`(버전 기록마다 콜백 — 저장 알림 `definitions.saved`용, 저장소 코드·스키마 변경 없음).

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.

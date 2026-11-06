# 변경 기록

## 미출시

- 6R.12: 이벤트 `EventRepository.list(node=)`(`node_path`에 그 노드 id가 있는 이벤트 — 첫 칸은 `node_id` 열 색인, 하위 그래프는 `json_each`), 출처 잇기 커서 `page_across_sources`·`SourcePage`·`encode_source_cursor`·`decode_source_cursor`(`<출처>.<저장소 커서>`, design §6R.18 Q14). 더하기만, 표 변경 없음.

- 6R.6: `RunRepository.page(cursor, limit, project_id, root_only, status, graph_id, labels) -> (items, next_cursor)`(커서 = `created_at`·`id` 내림차순, 불투명), `descendants(root_run_id)`, 루트 Run `labels`를 표 `run_labels`(계보 `runs_0004`)에 투영(`save`가 다시 쓰고 `delete`가 지움, 표가 없으면 `doc`에서 거름), 공개 `InvalidCursor`·`MAX_PAGE_LIMIT`·`encode_cursor`·`decode_cursor`. 더하기만.

- 5.7R.33j2: `RecordsMove`·`MoveSpec`·`MoveDependent`·`run_moves`·`MoveVerifyError`·`MovePartialError`(표 단위 옮기기: 복사 → 확인 → 원본 삭제, 실패 시 대상 롤백). 더하기만, 표 변경 없음.

- 5.7R.33y2: `RecordsStores`(프로젝트 id → 기록 DB 위 저장소 묶음, 처음 열기 훅), `RecordsUnavailable.project_id`·`details()`.

- 6R.5: `DefinitionKind.library`(기본 참, 거짓 = 라이브러리 공간에 두지 않는 종류, X36 확장)와 `DefinitionKind.with_summary_fields(*fields)`. 저장소 동작 변경 없음.

- 5.7R.33x: 공간 고르기 `spaces`(`DEFINITIONS_SPACES_PORT`·`DefinitionSpaces`·`SpaceStores`·`UnknownSpace` 404 `project.not_found`·`SpacesUnavailable` 409 `feature_unavailable`), 기록 DB 위 버전 기록소 `RecordsVersionRepository`(읽기 `read_engine`, 쓰기 `writable_engine`), 선택 프로토콜 `VersionWriteCheck.ensure_writable`(`ObservedVersionRepository`가 안쪽으로 넘김), `StoreError.field_issues()` — `store_error_body`가 `validation_failed`의 `details.issues`를 채운다(기본 빈 목록, 기존 동작 같음).

- 5.7R.33f: `BaseDefinitionStore.kind_info(name) -> DefinitionKind`(등록된 종류 정보, 같은 종류로 프로젝트 사본 공간을 열 때). 더하기만.

- 5.7R.33w2: `open_records_db`·`RecordsDb`·`inspect_records`(프로젝트 기록 DB 열기: 없음·같음·뒤처짐(백업 후 올림)·앞섬(읽기만)·깨짐·읽기 전용),
  `RecordsHandle`·`RecordsSpaces`·`RECORDS_SPACES_PORT`·`RecordsState`·`RecordsUnavailable`, `is_network_fs`·`can_write_path`,
  `migrate.upgrade_on`·`script_revisions`, `create_sqlite_engine(journal_mode=None, timeout=)`. 기존 동작·표 변경 없음.

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

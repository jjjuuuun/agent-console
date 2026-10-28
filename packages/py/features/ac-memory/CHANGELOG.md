# 변경 기록

## 0.1.0

- 처음 만듦(5.7R.9, design §5.7R.2): 저장소 프로토콜 `MemoryStore`(X31)·`InMemoryMemoryStore`(버전·`if_version` 충돌·동시 쓰기 순서·표시 삭제·완전 삭제·되돌리기·보관·옮기기·검색), 쓰기 정책(키 규칙·한도·비밀 검사 주입 `reject`·`redact`), 범위 종류(X29: 패키지 기본 데이터 `data/default_scope_kinds.yaml`, 병합·출처·끄기, id 틀 해석, entry point 로더), 접근 판단 `allowed`, 도구 묶음 `MemoryToolkit`(도구 4개, 사유 코드, 본문·검색어 없는 이벤트 payload), `testing`(가짜 시계·표본·저장소 계약 묶음).
- SQLite 저장소 하위 모듈 `sqlite`(5.7R.10): `open_sqlite_memory_store`·`SqliteMemoryStore`(표 `memory_entries`·`memory_versions`·`memory_tags`·`memory_stats` + FTS5 trigram `memory_search`, `BEGIN IMMEDIATE` 쓰기·바쁨 재시도, 3글자 미만·FTS5 없음은 포함 검색, 완전 삭제는 버전·태그·검색 행까지, `warnings()`), 표 정의 `sqlite.schema`, 규모 측정 도구 `testing.build_scale_store`·`WorkCounter`. 의존 `sqlalchemy` 추가.
- 정리 규칙·내보내기/가져오기(5.7R.11): `retention_plan`·`apply_retention`·`compile_retention_rules`·`retention_issues`·`retention_subject`(기본 규칙 없음, 고정 제외, 첫 맞는 규칙, `ac-conditions` 컴파일 경로, 적용 버전 `system`·`label` = 규칙 id), `export_markdown`·`write_markdown_archive`·`import_markdown`(`skip`·`overwrite`·`rename`, `dry_run`, 경로 공격·zip 폭탄·비밀 거부, `MemoryTransferLimits`·`MemoryTransferCodes`·`InvalidArchiveError`), 항목 훑기 `iter_entries`·`SearchableStore`·저장소 선택 능력 `EntryScanner`(`InMemoryMemoryStore.scan_entries`), 표본 `testing.sample_entry`·`sample_entry_summary`.

# agent-console-mod-memory

공유 메모리 기능 모듈(`mod-memory`, design §5.7R.2·§5.7R.5.2·§5.7R.6). 기능 라이브러리
`agent-console-memory`(저장소·범위 종류·정리 규칙·내보내기/가져오기)를 서버에 꽂는다. 사람은 REST·웹
화면으로 기록을 보고 고치고 지우며, 실행 연동(`link-memory-runs`)은 포트 `memory.service`로 에이전트
도구를 만든다. 실행·로그를 모른다(메모리는 실행 없이도 쓴다).

| 무엇 | 내용 |
| --- | --- |
| REST | `GET /memory/scope-kinds`, `GET /memory/scopes?kind=`, `GET /memory/tags?scope=&include_archived=`, `GET·POST /memory/entries`, `GET·PUT·DELETE /memory/entries/{id}`(`PUT`은 `If-Match` 필수, `DELETE ?purge=true`는 완전 삭제 204), `POST /memory/entries/{id}/move·archive·unarchive·restore?version=`, `GET /memory/entries/{id}/versions[/{v}]`, `POST /memory/retention/plan·apply`, `POST /memory/settings/check`, `GET /memory/export?scope=`(zip), `POST /memory/import?policy=skip\|overwrite\|rename&dry_run=`(본문 = zip) |
| WS | 토픽 `memory.changed`(메시지 `memory.changed`, 본문 없음 — 범위·키·id·버전·동작·쓴 주체 종류) |
| 오류 | `not_found`(404), `already_exists`(409, `details.entry_id`), `version_conflict`(412, `details.current_version`), `version_required`(428), `memory.invalid_key`·`memory.too_large`·`memory.secret_rejected`(422, 값·본문 조각 없음), `validation_failed`(422, 틀린 질의·zip 아님) |
| 제공 포트 | `memory.service`(모양 `MemoryServicePort`: `store`·`catalog()`·`settings()`·`limits`·`toolkit(access, context, ...)`), `server.warnings`(`memory.storage_memory`·`memory.search_fallback`·`memory.settings_invalid`) |
| 선택 포트 | `workspace.settings`(사용자 설정 `memory` 섹션. 없으면 기본값) |
| 저장 | 계보 `memory`(`memory_0001`, 버전 표 `alembic_version_memory`). 기본은 호스트 DB 파일, 옵션 `store_path`면 그 파일(같은 계보를 올림), DB가 없으면 프로세스 메모리 + 경고 |
| 설치자 옵션 | `modules.options.mod-memory.{store_path, retention_interval_seconds, full_text_search, busy_timeout_seconds, max_entry_bytes, max_entries_per_scope, max_total_bytes, max_key_chars, max_tags, max_tag_chars, preview_chars, max_page_size, max_tag_list, max_search_results, max_import_archive_bytes, max_import_files, max_import_file_bytes, max_import_total_bytes}` |
| 사용자 설정 | 워크스페이스 설정 `memory`(계약 `MemorySettings`: `include_default_scope_kinds`, `scope_kinds`, `secrets`, `max_versions_per_entry`, `retention.rules`). 깨진 부분만 빼고 쓰고 경고로 알린다 |
| 플러그인(X29) | entry point `agent_console.memory_scope_kinds`. 호스트 플러그인 로더(`agent_console.host_plugin_loaders`의 `memory`)가 호스트 묶음의 `memory_scope_kinds` 확장에 읽는다 |
| 웹 역할 | `memory`(메모리 화면·사이드바 항목·설정 "메모리" 섹션 데이터가 이 역할을 요구한다) |

- 범위 종류·태그·키 이름은 전부 데이터다. 빈 워크스페이스에서는 패키지 기본 범위 종류만 있고 기록은 0개다.
- 정리 규칙의 패키지 기본은 빈 목록이다(아무것도 자동으로 지우거나 보관하지 않는다). 자동 정리는
  `retention_interval_seconds`(기본 3600, 0 = 끔)마다 저장된 규칙만 적용한다.
- 메모리 내용은 다른 에이전트에게 지시처럼 읽힐 수 있다(보안 경계가 아니다). 쓰기 권한은 리소스 `memory`의
  접근 설정으로 좁히고, 사람이 화면에서 바로잡는다.
- 모듈을 끄면 위 경로가 404이고 계보를 올리지 않는다(다른 DB 모듈도 끄면 DB 파일이 생기지 않는다).

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-memory`(저장소·검색·정리·내보내기), `agent-console-conditions`(정리 규칙 연산자
  X22), `agent-console-modkit`(모듈·호스트), `agent-console-registry`(X29 레지스트리),
  `agent-console-store`(계보 실행·호스트 DB·단독 실행의 `settings.yaml` 읽기).
- 외부: FastAPI·pydantic(서버 모듈 공통), SQLAlchemy·Alembic(계보 `memory`). 새 외부 의존 없음.

## 설치

```bash
pip install agent-console-mod-memory
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-memory
```

## 최소 사용: 서버 없이 서비스

```python
>>> from agent_console_contracts.memory import MemoryScopeRef, MemoryWriteRequest
>>> from agent_console_memory import InMemoryMemoryStore, MemoryQuery
>>> from agent_console_mod_memory import MemoryService

>>> changes = []
>>> section = {"include_default_scope_kinds": False,
...            "scope_kinds": {"notes": {"label": "노트", "id": "{/project_id}"}}}
>>> service = MemoryService(
...     InMemoryMemoryStore(), section=lambda: section, on_change=changes.append
... )
>>> [k.kind for k in service.scope_kinds().kinds]
['notes']
>>> entry = service.create(MemoryWriteRequest(
...     scope=MemoryScopeRef(kind="notes", id="p1"), key="결정/api", content="v2 사용"))
>>> (entry.version, entry.created_by.kind, [c.op for c in changes])
(1, 'user', ['create'])
>>> [i.key for i in service.entries(MemoryQuery(text="v2")).items]
['결정/api']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 로그·구조도에서 보기(예시 데이터)

실행 연동(`link-memory-runs`)이 남긴 실행 이벤트 `memory.<op>`는 플랫폼 실행 로그 대응표
(`ac-link-logs-runs` `run_event_map.yaml`의 `memory.*`)가 범주 `memory`, 문서 표지
`{kind: memory, path: <범위 종류>/<범위 id>/<키>, action: read|written|removed|searched}`, 근거
`tool_use_id`·`memory_scope`(범위 종류)로 옮긴다. 범위를 모르는 호출(권한 없음 등)은 문서 표지가 없다.
지우기는 `removed`다(`deleted`는 파일 변경 어휘라 기본 구조도 Workspace 칸에도 맞는다).

기본 구조도 프로필에는 Memory 칸이 없다. 보고 싶으면 워크스페이스 설정에 프로필을 더한다. 아래는
기본 프로필(`GET /architecture/profiles/agent-architecture`의 `profile`)을 복제해 칸·연결·coverage만
더한 예시다(`...`은 복제한 나머지 내용). 저장소에 이 데이터를 두지 않는다. 사용자가 직접 넣는다.

```yaml
architecture:
  profiles:
    with-memory:
      title: 에이전트 아키텍처 + 메모리
      # ... 기본 프로필의 canvas·zones·error_when·source_priority·cells·edges·coverage를 그대로 복제 ...
      cells:
        # ... 기본 칸 ...
        memory:
          label: Memory
          description: 공유 메모리 읽기·쓰기
          x: 810
          y: 730
          zone: runtime
          tone: gold
          metrics: [count, errors]
          group_by: /correlation/memory_scope      # 범위 종류별 묶음
          when: {all: [{path: /category, op: eq, value: memory}]}
      edges:
        # ... 기본 연결 ...
        - id: memory_access
          from: dispatch
          to: memory
          label: 메모리 접근
          kind: observed
          style: request
          points: [[1054, 610], [1030, 610], [1030, 730], [906, 730]]
          label_at: [968, 730]
          metrics: [count, errors]
          when: {all: [{path: /category, op: eq, value: memory}]}
      coverage:
        # ... claude-code-jsonl는 그대로 ...
        platform-runs:
          cells: [sdk, api, rules, context, llm, dispatch, hook, tools, mcp, result, delegation,
                  subagents, response, memory]
```

- 범주 이름도 데이터다. 로그 설정 `logs.sources[id=platform-runs].config.event_map`에서 `memory.*` 규칙을
  통째로 다시 적어 `category: notes`로 바꾸면, 위 조건의 `value`도 `notes`로 바꾼다.
- 규칙을 끄려면 같은 자리에 `"memory.*": {}`를 적는다. 메모리 이벤트는 범주 `other`(제목 = 형식 이름)가 되고
  Memory 칸은 0회다. 다른 로그는 그대로다.
- 칸 횟수 = 그 실행의 메모리 이벤트 수 = 칸을 눌렀을 때 이벤트 표 수다(저장소 통합 테스트
  `test_integration_memory_cell_57r16.py`가 같은 데이터로 확인한다).

## 단독 실행

```bash
python -m agent_console_mod_memory --config standalone.json --port 0
```

`--with`를 주지 않으면 워크스페이스 `settings.yaml`을 읽는 작은 설정 모듈(`local-settings`)이 붙는다.
사용자 설정은 그 파일의 `memory` 섹션에 적는다. 기록은 상태 폴더의 `console.sqlite3`(계보 `memory`)에 둔다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

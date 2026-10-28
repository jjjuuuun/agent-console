# agent-console-mod-logs

로그 기능 모듈(`mod-logs`). 로그 출처(X5)·분류기(X6) 플러그인으로 로그를 모아 색인하고(배경·수동 수집),
`/logs…` REST와 WS 토픽 `logs`로 질의·알림을 낸다.

- **기능 이름·출처 이름을 모른다.** 출처·분류기는 호스트 레지스트리 묶음(`log_sources`·`log_classifiers`)에서
  오고, 그 묶음은 이 패키지의 호스트 플러그인 로더(entry point `agent_console.host_plugin_loaders` = `logs`)가
  entry point X5·X6으로 채운다. 묶음이 없으면(단독 실행) entry point에서 직접 읽는다.
- **혼자 켜진다.** 필수 포트가 없다. 선택 포트가 없으면 그 부분만 꺼진다.
  - `workspace.settings` 없음 → 기본 설정(출처 디스크립터 `default_enabled`, 기본 분류 체계)
  - `secrets.rules` 없음 → 색인을 가리지 않고 `logs.redaction_unavailable` 경고
  - `logs.sources` 없음 → 플러그인 출처만
- **원본은 읽기만 한다.** 수집은 `agent-console-logs`의 `LogIngestor`가 읽기 전용 열기로만 한다.
- 서버 앱(`apps/server`)은 이 모듈 이름을 모른다. 설치되면 entry point로 들어온다.

## 포트·토픽·경로

| 구분 | 이름 | 모양 |
| --- | --- | --- |
| 제공 | `logs.query` | `LogQueryPort`(목록·목록 행(`iter_event_rows`, 모델 없는 JSON 행, 5.5R.36)·상세·세션·타임라인·집계·handoff·토큰 표본·분류 체계·질의 맥락) |
| 제공 | `logs.ingest` | `LogIngestPort`(`add_runtime_source`·`request_scan(source_ids, ref_hint=)`·`scan`) |
| 제공 | `server.warnings` | `logs.storage_memory`·`logs.redaction_unavailable`·`logs.source_failed`·`logs.unknown_classifier` |
| 선택(multi) | `logs.sources` | `RuntimeLogSource`(`source`·`classifier` 속성, 예: `testing.RuntimeSource`) |
| 선택 | `workspace.settings` | `() -> WorkspaceSettings`(`logs.*`, `secrets.redact_suspected_in_logs`) |
| 선택 | `secrets.rules` | `() -> SecretRules`(`redact_value`) |
| 선택(multi) | `logs.source_defaults` | `() -> {출처 id: bool}` — 설정에 `enabled`가 없는 출처의 기본값(5.2R.27, 예: `link-logs-usage`가 이 PC에 Claude Code 로그가 있으면 켬). 사용자가 적은 `enabled`가 이기고 설정 파일은 그대로다(`apply_source_defaults`). 없으면 디스크립터 `default_enabled` |
| 선택(multi) | `logs.scope_kinds` | X27 `LogScopeKind`(`id`·`resolve(value) -> LogScope{sessions, run_ids}`) — 필터 `scope=<id>:<값>`. 없으면 `scope`는 422 |
| 선택(multi) | `logs.filter_predicates` | X28 `LogFilterExtension`(`fields`·`build(values, context) -> 판정 함수`) — 이름이 `GET /logs/schema` filters에 실리고 목록·세션·타임라인·집계·handoff·보관본이 따른다. 없으면 그 이름은 422. 이름이 겹치면 먼저 온 것만(경고 로그) |
| 토픽 | `logs.ingested` | `LogsIngestedPayload{source_ids, count, max_seq}` |
| WS | `logs` | `logs.ingested` 메시지 |
| 웹 역할 | `logs` | 로그 화면 |
| 계보 | `logs` | `storage.BRANCH`(버전 테이블 `alembic_version_logs`) |

경로(`/api/v1` 아래, 모듈이 꺼지면 404):
`GET /logs/sources`, `GET /logs/classifiers`, `POST /logs/scan`(202, 본문 `{source_ids?}`),
`GET /logs/events?<LogFilter>`, `GET /logs/events/{uid}`, `GET /logs/sessions?<LogFilter>`,
`GET /logs/sessions/{session}/timeline?<LogFilter>`, `POST /logs/aggregate`, `GET /logs/handoffs?<LogFilter>`,
`GET /logs/taxonomy`, `GET /logs/dashboard-templates`, `GET /logs/schema`,
`GET /logs/archive?<LogFilter>&format=json|html&tz=<IANA>`(첨부),
`POST /logs/index/purge`(색인 비우기, M-3, 아래).
기본 필터에는 `thread`(여러 값)·`scope`(`<종류>:<값>`)·`max_seq`(이 seq 이하)가 있다.
모르는 필터·차원·지표·시간대·범위 종류는 422 `validation_failed`(`details.path`, `details.issues[].code = logs.invalid_query`).
프로젝트 필터 `project=~ungrouped`는 묶기 규칙에 맞지 않는 로그다.

### 색인 비우기 `POST /logs/index/purge`(M-3)

본문 `LogPurgeRequest{sources?, categories?, before?, rescan=true, dry_run=true, all=false}`(모듈 안 모델, 모르는 키·빈 목록은 422),
응답 `LogPurgeResponse{dry_run, events, usage, cursors, agents}`(지운, dry_run이면 지울 행 수). 두 모델은 계약 밖이라
OpenAPI에는 인라인 스키마(`routes.PURGE_BODY_SCHEMA`·`PURGE_RESPONSE_SCHEMA`)로만 싣는다. 의미는
`agent_console_logs.purge_index`다. **dry_run이 기본**이라 `"dry_run": false`를 줘야 지운다. 본문을 생략하면 색인 전체를
센다. `rescan`이면 범위 출처의 커서도 지워 다음 수집(`POST /logs/scan` 또는 배경 수집)이 지금 분류 규칙으로 다시
색인한다. 진행 중인 수집이 끝난 뒤 수집 잠금 안에서 돌고, 원본 파일은 건드리지 않는다. 범위(출처·범주·시각) 없이
실제로 지우려면(`"dry_run": false`) `"all": true` 확인이 있어야 한다(없으면 아무것도 지우지 않고 422, `details.path =
"all"` — CLI `--all`과 같은 안전장치). 색인이 비우기를 지원하지 않으면 400 `logs.purge_unsupported`. 서비스에서는
`LogsService.purge(...)`(async). 서버 없이 색인 파일을 고치려면 `agent-console logs purge`(apps/cli).

```bash
# 옛 색인의 Claude Code 요청 본문(api-request-blob, 범주 meta)을 지우고 다시 수집
curl -X POST .../api/v1/logs/index/purge -d '{"sources":["claude-code-jsonl"],"categories":["meta"]}'   # 세기
curl -X POST .../api/v1/logs/index/purge -d '{"sources":["claude-code-jsonl"],"categories":["meta"],"dry_run":false}'
curl -X POST .../api/v1/logs/scan -d '{"source_ids":["claude-code-jsonl"]}'
```

## 설치자 옵션(`modules.options.mod-logs`)

| 키 | 기본 | 뜻 |
| --- | --- | --- |
| `scan_interval_seconds` | 30 | 배경 수집 주기(초). 0이면 반복 수집 없음 |
| `startup_scan` | true | 시작 직후 한 번 수집(주기와 따로) |
| `scan_budget_bytes` | 8,000,000 | 출처 하나를 한 번 수집할 때 읽는 최대 바이트 |
| `batch_size` | 500 | 한 트랜잭션의 이벤트 수 |
| `retention_days` | null | 이보다 오래된 색인 이벤트 삭제(원본은 그대로). null = 영구 |
| `index_path` | null | 별도 SQLite 파일에 색인(같은 계보를 모듈이 직접 올림). null = 호스트 DB |
| `max_detail_bytes` | 80,000 | 상세 응답 detail·raw 상한 |
| `timeline_limit` | 5000 | 타임라인 한 번에 싣는 이벤트 수 |
| `dashboard_templates_dir` | null | 대시보드 템플릿 폴더. null = 패키지 기본(`data/dashboard_templates`) |
| `archive_max_events` | 5000 | 보관본에 담는 최대 이벤트 수(넘으면 앞부분만, `truncated`) |
| `archive_max_bytes` | 20,000,000 | 보관본 이벤트 JSON 바이트 합 상한 |
| `archive_file_prefix` | `agent-console-logs` | 보관본 파일 이름 앞부분(`<앞부분>-<UTC 시각>.json\|html`) |
| `archive_title` | `Agent Console 로그 보관본` | 보관본 HTML 제목 |
| `session_title_rules` | null | 세션 제목 순위 규칙 `[{tag, pick: first\|last}]`(위에서부터, 후보가 있는 첫 규칙). null = `agent-console-logs` 기본 데이터, `[]` = 제목 없음 |
| `base_taxonomy_file` | null | 기본 분류 체계 YAML 파일. null = `agent-console-logs` 기본 데이터(`default_taxonomy.yaml`), 경로 = 그 파일(없으면 경고 후 빈 분류), `false`·빈 문자열 = 기본 분류 없음(워크스페이스 설정 `logs.taxonomy`만 얹힌다) |

보관본(`/logs/archive`)은 필터 범위의 이벤트(본문은 `max_detail_bytes`까지)·세션·줄·근거 연결·유효 분류 체계를
담는다(`limit`·`cursor`는 쓰지 않는다). `format=json`(기본)은 `LogArchive` v1, `format=html`은 스크립트 없는 HTML
(`agent_console_logs.render_archive`, 시각은 `tz` 또는 서버 로컬)이고 둘 다 첨부로 내려준다. 가림 규칙이 있으면
내보낼 때 지금 규칙으로 한 번 더 가린다(수집 뒤 규칙이 바뀐 경우). 모르는 `format`·`tz`·필터 이름은 422다.

상대 경로는 호스트 `base_dir`(설정 파일 폴더) 기준이다. 대시보드 템플릿은 기본 데이터다. 파일 하나가
`LogDashboard` 하나이고 위젯마다 `options.w`·`h`가 있으며 질의 필터에 기간이 없다. 폴더를 비우거나 지워도 동작한다.

## 설치

```bash
pip install agent-console-mod-logs
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-logs
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `agent-console-logs` | `LogIngestor`·`SqliteLogIndex`·`MemoryLogIndex`·질의·기본 플러그인 | 수집·색인·질의는 라이브러리에 둔다 | — |
| `agent-console-modkit[host]` | 모듈 인터페이스·호스트·단독 실행 | 모든 서버 모듈의 공통 키트 | — |
| `agent-console-store` | 계보 실행기(`upgrade`)·정의 파일 저장소(단독 실행의 `settings.yaml`) | 호스트와 같은 방식 | 직접 alembic 호출 |
| `fastapi` | 라우터 | 호스트와 같은 웹 프레임워크 | — |
| `ruamel-yaml` | 대시보드 템플릿(YAML 데이터) 읽기 | 워크스페이스 YAML 표준 | PyYAML |
| `sqlalchemy` | 엔진 | 호스트 `DatabaseHandle.engine`과 같은 타입 | — |

## 최소 사용

서버 없이 서비스만 쓴다: 임시 폴더의 v1 jsonl을 메모리 색인에 수집하고 질의한다.

```python
>>> import asyncio, json, tempfile, time
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogRegistries
>>> from agent_console_logs.testing import MemoryLogIndex
>>> from agent_console_mod_logs import LogsService

>>> folder = Path(tempfile.mkdtemp())
>>> rows = [{"schema_version": 1, "category": "input", "title": "안녕", "session": "S"},
...         {"schema_version": 1, "category": "llm", "title": "답", "session": "S"}]
>>> _ = (folder / "a.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}]}
... )
>>> registries = LogRegistries()
>>> _ = registries.load()
>>> service = LogsService(MemoryLogIndex(), registries, settings=lambda: settings, clock=time.time)
>>> asyncio.run(service.scan()).new_events
2
>>> [(s.session, s.events) for s in service.sessions(LogFilter())]
[('S', 2)]

```

모듈로 조립하면 REST가 붙는다(설정은 `workspace.settings` 포트로 받는다).

```python
>>> from fastapi.testclient import TestClient
>>> from agent_console_contracts import WorkspaceSettings
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app
>>> from agent_console_mod_logs import module
>>> from agent_console_mod_logs.testing import static_settings_module
>>> workspace = WorkspaceSettings.model_validate({"logs": settings.model_dump(exclude_unset=True)})
>>> assembly = assemble(
...     [module, static_settings_module(workspace)],
...     ModulesConfig(options={"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}}),
... )
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> with TestClient(create_host_app(assembly, policy=policy)) as client:
...     client.headers["X-Console-Token"] = "t" * 32
...     print(client.post("/api/v1/logs/scan").json()["new_events"])
...     print([e["title"] for e in client.get("/api/v1/logs/events").json()["items"]])
2
['안녕', '답']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 단독 실행

```bash
python -m agent_console_mod_logs [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`를 주지 않으면 `testing.local_settings_module`(워크스페이스 폴더의 `settings.yaml`)을 붙인다. 읽을 출처는
그 파일의 `logs.sources`에 켠다. 색인은 상태 폴더의 `console.sqlite3`(계보 `logs`)다. 비밀 의심 가림까지 쓰려면
`--with mod-definitions`(설치돼 있을 때).

## 저장 계층

- **계보 `logs`**: 패키지 데이터 `storage/migrations/versions/logs_0001_index.py`(테이블)·`logs_0002_scope_indexes.py`(`thread`·`run_id`·`session` + `seq` 색인, 5.5R.6), 버전 테이블 `alembic_version_logs`.
  모듈이 켜질 때만 올라가고, 되돌리기(`downgrade`)는 이 계보 단위로만 한다.
  `ac-store.MODULE_OWNED_TABLES`에는 넣지 않는다(F-2) — legacy 이관 전용 목록이다.
- **색인 위치**: 기본은 호스트 DB(F-9). `index_path`를 주면 그 SQLite 파일에 같은 계보를 직접 올려 쓴다.
  DB가 없으면 `MemoryLogIndex`다(`LogStorage.kind == "memory"`, `logs.storage_memory` 경고).
- 색인 구현·질의는 `agent-console-logs`의 `agent_console_logs.sqlite`에 있다.

```python
from agent_console_mod_logs import open_log_storage

storage = open_log_storage(None, index_path="logs.sqlite3")  # 별도 파일에 계보를 올리고 연다
open_log_storage(None).kind  # DB도 경로도 없으면 "memory"
```

## 공개 API

| 이름 | 설명 |
| --- | --- |
| `module` / `LogsModule` / `MODULE_ID` / `WEB_ROLES` | 서버 모듈(entry point `agent_console.server_modules`) |
| `base_taxonomy_of` | 옵션 `base_taxonomy_file` → 기본 분류 체계(`LogsService(base_taxonomy=)`에 넘길 값) |
| `LogsService` | 수집 스케줄(`scan`·`request_scan`·`run_periodic`·`start`·`stop`) + 질의(`parse_filter`·`extensions`·`events`·`iter_event_rows`·`event`·`sessions`·`timeline`·`aggregate`·`handoffs`·`token_samples`·`taxonomy`·`schema`·`dashboard_templates`·`sources`·`classifiers`) |
| `LogsModuleSettings` | 설치자 옵션 |
| `LogRedaction` | 저장 직전 비밀 의심 가리기(포트 값으로) |
| `LOGS_QUERY`·`LOGS_INGEST`·`SERVER_WARNINGS`·`LOG_SOURCES`·`LOG_SCOPE_KINDS`·`LOG_FILTER_PREDICATES`·`WORKSPACE_SETTINGS`·`SECRET_RULES`·`LOGS_INGESTED`·`LOGS_TOPIC` | 포트·토픽·WS 토픽 |
| `LogQueryPort`·`LogIngestPort`·`RuntimeLogSource` | 포트 프로토콜(구조 타입) |
| `load_dashboard_templates`·`parse_dashboard` | 대시보드 템플릿 읽기 |
| `plugins.load_plugins`·`plugins.bundle_registries` | 호스트 플러그인 로더 |
| `standalone.main` | 단독 실행 진입점 |
| `storage.BRANCH`·`open_log_storage`·`LogStorage` | 계보·색인 열기 |
| `testing.local_settings_module`·`static_settings_module`·`runtime_sources_module`·`RuntimeSource`·`query_extensions_module`(X27·X28 등록 흉내) | 단독 실행·테스트용 모듈 |

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

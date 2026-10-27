# agent-console-logs

로그 분석 코어. 여러 도구의 로그를 같은 구조(정규화 이벤트)로 모으고 질의한다.

- **출처·분류기는 확장 지점이다.** 로그 출처(X5, entry point `agent_console.log_sources`)와
  분류기(X6, `agent_console.log_classifiers`)를 등록해 쓴다. 기본 제공 `normalized-v1`·`mapped-jsonl`도
  entry point로 들어오는 첫 구현이다. 특정 도구 형식(Claude Code 등)은 이 패키지가 모른다.
- **원본은 읽기만 한다.** 출처는 파일을 주입된 `open_read`로만 연다. 이 패키지에는 원본 쓰기 경로가 없다.
- **분류기는 행 단위 무상태다**(F-7). 응답 묶기·호출 짝·소요 시간은 질의 때 명시 id로 계산한다.
- **토큰은 응답당 한 번 센다**(F-8, R8.1). (출처, thread, message_id)마다 output이 가장 큰 표본 하나다.
- **범주 이름을 코드가 해석하지 않는다.** 표시 이름·숨김·오류(`tone: danger`, F-25)는 분류 체계 데이터
  (`data/default_taxonomy.yaml` + 설정 `logs.taxonomy`)다. 분류 체계를 비워도 동작한다.
  기본 분류 체계에는 숨김 범주 `meta`(`visible: false`, 형식 내부 기록 — 타임라인에서만 숨김)가 있다(5R.19).
- **세션 제목 순위는 데이터다(5R.19).** `QueryContext.session_title_rules`(`SessionTitleRule(tag, pick=first|last)`
  목록)를 위에서부터 보고 후보가 있는 첫 규칙이 이긴다. 기본은 `data/default_session_title_rules.yaml`(마지막
  `session_title.renamed` > 마지막 `session_title.generated` > 첫 `session_title`), 파일이 없거나 비면
  `DEFAULT_SESSION_TITLE_RULES`(첫 `session_title`). `query_context(..., session_title_rules=)`로 바꾼다.
- SQLite 색인의 목록·타임라인 `duration_ms` 짝 질의는 (`thread`, `call_id`) 색인 `ix_log_events_thread_call`을 탄다(실행 계획 테스트, 5R.19).
- 서버·웹 없이 쓴다. fastapi·starlette를 import하지 않는다.

## 설치

```bash
uv sync --all-packages                              # 워크스페이스 안
uv pip install ./packages/py/features/ac-logs       # 단독(contracts·registry 함께)
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `agent-console-contracts` | `LogEvent`·`TokenSample`·`LogSettings`·디스크립터·DTO | 계약 단일 소스 | — |
| `agent-console-registry` | X5·X6 레지스트리·entry point 로딩 | 모든 확장 지점이 같은 등록 방식 | — |
| `jsonschema` | 출처·분류기 설정을 `config_schema`로 검증하고 기본값 채움 | 워크스페이스에서 이미 쓰는 검증기 | pydantic 동적 모델 |
| `ruamel-yaml` | 기본 분류 체계(YAML 패키지 데이터) 읽기 | 워크스페이스 YAML 표준 | PyYAML |
| `sqlalchemy` | SQLite 색인(`agent_console_logs.sqlite`, Core) | 워크스페이스 저장소 표준, 서버 DB 핸들의 엔진을 그대로 받는다 | 표준 `sqlite3` 직접 사용(스키마 공유·이식성 약함) |

## 최소 사용

임시 폴더의 v1 jsonl을 메모리 색인으로 수집하고 질의한다.

```python
>>> import json, tempfile
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex

>>> folder = Path(tempfile.mkdtemp())
>>> rows = [
...     {"schema_version": 1, "category": "llm", "title": "답변", "session": "S", "thread": "main",
...      "message_id": "m1", "usage": {"input_tokens": 10, "output_tokens": 3}},
...     {"schema_version": 1, "category": "llm", "title": "답변(이어짐)", "session": "S",
...      "thread": "main", "message_id": "m1", "usage": {"input_tokens": 10, "output_tokens": 8}},
...     {"schema_version": 1, "category": "error", "title": "실패", "session": "S"},
... ]
>>> _ = (folder / "events.jsonl").write_text(
...     "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
... )

>>> registries = LogRegistries()
>>> _ = registries.load()                       # entry point X5·X6
>>> index = MemoryLogIndex()                    # 실제로는 SQLite 색인
>>> ingestor = LogIngestor(index, registries)   # redact=, environ=, open_read= 주입 가능
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}]}
... )
>>> ingestor.scan(settings).new_events
3
>>> ingestor.scan(settings).new_events          # 증분: 바뀐 것이 없으면 0
0

>>> ctx = query_context(settings)               # 분류 체계·프로젝트 묶기(설정 데이터)
>>> [e.title for e in index.query_events(LogFilter(), ctx).items]
['답변', '답변(이어짐)', '실패']
>>> session = index.list_sessions(LogFilter(), ctx)[0]
>>> (session.events, session.errors, session.tokens.output)   # 같은 응답 m1의 토큰은 한 번
(3, 1, 8)

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 공개 API

| 묶음 | 이름 |
| --- | --- |
| 출처·분류기·초안 | `LogSource`, `SourceRef`, `Cursor`, `RawRecord`, `ReadResult`, `LogSourceContext`, `JsonlFileSource`(+`JSONL_CONFIG_SCHEMA`), `LogClassifier`, `ClassifyContext`, `LogEventDraft`, `AgentInfo`, 약속 태그 `TAG_TOOL`·`TAG_SESSION_TITLE`·`TAG_DIAGNOSTIC`, `DIAGNOSTIC_META_KEY` |
| 레지스트리·수집 | `LogRegistries`(`load()` → `{"log_sources": [LoadReport], "log_classifiers": [...]}`, 레지스트리 이름 `LOG_SOURCES_EXTENSION`·`LOG_CLASSIFIERS_EXTENSION` = 호스트 묶음의 확장 이름), `LogIngestor`(`scan`·`sources`·`add_runtime_source`), `source_enabled` |
| 색인 | `LogIndex` 프로토콜, `IndexRecord`·`IndexBatch`·`BatchResult`·`StoredCursor` |
| SQLite 색인 | `agent_console_logs.sqlite`: `SqliteLogIndex(engine)`, `open_log_index(path)`(단독, `create_all`), `create_log_engine`, 테이블 `log_metadata`·`log_events`·`log_bodies`·`log_search`·`log_tags`·`log_links`·`log_corr`·`log_agents`·`log_cursors`·`log_usage` |
| 질의 | `LogFilter`(`thread`·`scope`·`max_seq`·`extra` 포함)·`parse_log_filter(extra=)`·`LogQueryError(path)`, `QueryContext`(`scope`·`predicates`·`extra_names`)·`query_context`·`require_refined`, `query_schema(extra_filters)`·`DIMENSIONS`·`METRICS`·`FILTER_FIELDS`, 하위 모듈 `query`(질의 의미 순수 함수) |
| 질의 확장(X27·X28) | `LogScopeKind`(`id`·`resolve(value) -> LogScope`), `LogScope`(세션·run_id 합집합), `LogFilterExtension`(`fields`·`build(values, LogFilterContext) -> EventPredicate`), 묶음 `LogQueryExtensions`(`collect`·`parse`·`refine`·`schema`·`skipped`) |
| 순수 함수 | `bounded`, `event_uid`·`identity_for`·`build_record`, `link_events`·`pair_durations`, `merge_taxonomy`·`load_default_taxonomy`, `group_projects`·`resolve_project`·`git_worktree_root`, `block_windows`·`rolling_totals`·`sum_samples`, `glob_match`, `json_pointer`, `scrub_surrogates`·`dirty_surrogates`(외톨이 서로게이트 → U+FFFD·검사, `build_record`가 모든 문자열에 적용) |
| 보관본 | `build_archive`(`LogArchive` v1: 필터 범위·`max_events`·`max_bytes`·`redact`, `ARCHIVE_VERSION`·`DEFAULT_ARCHIVE_MAX_EVENTS`·`DEFAULT_ARCHIVE_MAX_BYTES`), `filter_to_params`, `render_archive`(스크립트 없는 HTML, `DEFAULT_ARCHIVE_TITLE`), `escape_html` |
| 테스트 지원 | `testing.TableScopeKind`·`testing.FieldFilter`(X27·X28 예제·가짜), `testing.MemoryLogIndex`, `testing.LogIndexContractTests`(다른 색인 구현이 상속), `testing.RecordingOpen`·`no_writes_under`·`tree_digest`(원본 쓰기 감시·해시) |

## SQLite 색인

`SqliteLogIndex`는 `MemoryLogIndex`와 같은 계약 테스트 묶음(`LogIndexContractTests`)을 통과하고,
무작위 데이터에서 모든 질의의 답이 `MemoryLogIndex`와 같음을 테스트로 확인한다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_logs import IndexBatch, LogFilter, QueryContext
>>> from agent_console_logs.sqlite import open_log_index
>>> from agent_console_logs.testing import make_record
>>> path = Path(tempfile.mkdtemp()) / "logs.sqlite3"
>>> index = open_log_index(path)               # 단독 사용: 테이블을 직접 만든다(create_all)
>>> index.write(IndexBatch(records=[make_record("llm", title="안녕", session="S")])).inserted
1
>>> index.close()
>>> [e.title for e in open_log_index(path).query_events(LogFilter(), QueryContext()).items]
['안녕']

```

- 서버 안에서는 테이블을 `ac-mod-logs`의 마이그레이션 계보 `logs`가 만든다(`create_all`은 단독 사용 전용).
  두 모양이 같음은 `ac-mod-logs` 테스트가 `compare_metadata`로 확인한다.
- 큰 열은 분리했다. `log_events`는 필터·정렬·집계에 쓰는 좁은 열만, 본문 JSON(`log_bodies.body`)·원문(`heavy`)·
  검색 문자열(`log_search`)은 따로 둔다. 목록·세션 요약·집계는 좁은 행만 읽는다.
- 같은 uid는 한 번만 들어가고(`INSERT ... DO NOTHING`), 쓰기는 `BEGIN IMMEDIATE`로 시작해 다른 프로세스와
  섞이지 않는다. seq는 `AUTOINCREMENT`라 지운 뒤에도 다시 쓰이지 않는다(키셋 커서 안전).
- 토큰은 `log_usage`의 (source, thread, message_id) 한 행이며, 같은 키가 다시 오면 output이 크거나 같을 때만 바꾼다.
- 한계: 검색어 `q`는 `log_search`를 훑는다(10만 건에서 수백 ms). 세션 목록은 질의마다 집계한다.

## 질의 확장: 범위 종류(X27)·필터 확장(X28)

필터 `scope=<종류>:<값>`과 확장 필터 이름은 등록으로 들어온다. `LogQueryExtensions`가 필터를 읽고
(`parse`), 질의 전에 풀어(`refine`) 질의 맥락에 세션·run_id 합집합(`QueryContext.scope`)과 이벤트 판정
함수(`QueryContext.predicates`)를 싣는다. 색인 구현은 풀린 맥락만 본다(메모리·SQLite 결과가 같음을
차등 테스트로 확인). 등록이 없으면 맥락은 그대로이고, 풀지 않은 `scope`·확장 필터를 색인에 넘기면
`LogQueryError`다.

- 범위: 이벤트의 세션 또는 run_id가 합집합에 들어야 한다. 토큰 표본은 세션이 들거나, run_id 범위
  이벤트와 응답 키가 같아야 한다.
- 확장 판정·`max_seq`는 이벤트 전용 필터다(표본은 맞는 이벤트의 응답 키로 거른다). SQLite는 판정을
  연결 전용 SQL 함수로 부르므로 페이지·커서·집계가 그대로지만, 후보 행마다 본문 JSON을 읽는다.

```python
>>> from agent_console_logs import IndexBatch, LogQueryExtensions, QueryContext
>>> from agent_console_logs.testing import FieldFilter, MemoryLogIndex, TableScopeKind, make_record
>>> index = MemoryLogIndex()
>>> _ = index.write(IndexBatch(records=[
...     make_record("tool_call", tool="Bash", session="S1"),
...     make_record("tool_call", tool="Read", session="S1"),
...     make_record("llm", session="S2", run_id="r1"),
... ]))
>>> ext = LogQueryExtensions.collect(
...     [TableScopeKind("run", {"r1": ([], ["r1"])})],     # 범위 종류(X27)
...     [FieldFilter("only_tool", "tool")],                # 필터 확장(X28)
... )
>>> flt = ext.parse({"only_tool": "Bash"})
>>> [e.tool for e in index.query_events(flt, ext.refine(flt, QueryContext())).items]
['Bash']
>>> flt = ext.parse({"scope": "run:r1"})
>>> [e.session for e in index.query_events(flt, ext.refine(flt, QueryContext())).items]
['S2']

```

## 수집 규칙(agent_bench `_ingest`와 같음)

- 바이트 오프셋 커서로 이어 읽는다. 출처당 수집 한 번의 예산은 `budget_bytes`(기본 8 MB)이고 남은 것은
  다음 수집에서 읽는다.
- 끝나지 않은 마지막 줄은 보류하고, `scan(final=True)`면 읽는다.
- 파일이 커서보다 작아지면 처음부터 다시 읽는다. identity 덕분에 중복되지 않는다.
- **회전 감지**: 읽은 앞부분(최대 4 KB, 완성된 줄까지)과 첫 줄의 sha256 지문을 커서 `state.jsonl_head`에 둔다.
  다음 수집에서 앞부분이 다르면(같은 이름의 더 큰 새 파일, 같은 크기 다른 내용 등) 처음부터 다시 읽고
  내용 세대(`state.jsonl_generation`, `RawRecord.generation`)를 올린다. 세대는 기본 identity에 들어가
  (`{source}:{ref}@{세대}:{offset}`) 같은 위치의 새 줄이 옛 줄과 겹쳐 버려지지 않는다. 같은 세대를 다시
  읽으면 중복 0. 지문이 없는 옛 커서는 그대로 이어 읽는다.
- **한계**: 크기와 앞부분 4 KB가 같고 그 뒤만 바뀐 파일은 감지하지 못한다(크기·mtime까지 같으면 읽지도
  않는다). 파일이 줄면 앞부분(파일이 그보다 짧으면 첫 줄)의 지문이 같을 때만 같은 파일이 잘린 것으로 보고
  세대를 유지한다(identity로 중복 0). 다르거나 확인할 수 없으면(첫 줄보다 짧음, 지문 없는 옛 커서) 새 내용으로
  보고 세대를 올린다. 이때 같은 내용을 다시 쓴 파일이면 이벤트가 중복될 수 있다(데이터 손실 대신 택함, 토큰은
  message_id 규칙으로 한 번만 센다).
- **심볼릭 링크**: 폴더 링크는 따라가지 않는다. 파일 링크는 실제 위치가 그 루트 안일 때만 읽고, 루트 밖을
  가리키는 링크는 건너뛴다(`discover`에서 빼고 `resolve`도 거절). 같은 실제 파일을 가리키는 경로가 여럿이면
  하나만 낸다(링크가 아닌 경로 우선, 그다음 이름순).
- 해석·분류에 실패한 줄은 버리지 않고 진단 이벤트(`source = "diagnostic"`, 범주 `error`, 태그 `diagnostic`)로 남긴다.
- 이벤트 묶음과 커서는 같은 `write` 호출(한 트랜잭션)로 쓴다. 바뀌지 않은 파일은 읽지 않는다.
- identity: 초안 `identity` → 도구 이벤트(`TAG_TOOL` + `call_id`) `tool:{source}:{thread}:{call_id}:{stage}` →
  `{source}:{ref}[@{세대}]:{offset}[:{index}]`(세대는 회전된 파일만). uid = `sha256(identity)[:24]`.
- `repo_root`: cwd의 `.git`이 worktree 표시 파일이면 본 저장소 경로(읽기 전용, 수집마다 캐시).
  설정 `logs.projects.git_worktrees: false`면 계산하지 않는다.

## 오프라인 보관본

`build_archive`는 필터에 맞는 이벤트(본문 포함)·세션 요약·줄·근거 연결·분류 체계를 `LogArchive` v1로 묶는다
(agent_bench `LogStore.export`). `render_archive`는 그것을 **스크립트 없는** HTML 한 장으로 그린다(F-13,
agent_bench `render_archive`는 웹 JS를 박아 넣었다). 네트워크 없이 열리고, 외부 자원·스크립트는
`Content-Security-Policy`로 막는다.

- 범위: 필터 그대로(`limit`·`cursor`는 쓰지 않고 끝까지 넘긴다). 세션 요약도 같은 필터로 센다.
- 크기: `max_events`(기본 5000)·`max_bytes`(이벤트 JSON 합, 기본 약 20 MB)·`max_detail_bytes`(이벤트 하나의 본문).
  넘으면 앞부분만 담고 `truncated = True`(HTML은 안내 문구).
- 가림: 색인 사본은 수집 때 가려졌다. `redact`를 주면 제목·요약·본문·원문·세션 제목·필터 값을 지금 규칙으로 한 번 더 가린다.
- HTML: `<meta charset="UTF-8">`, 한글 폰트 목록(시스템 폰트 폴백), `word-break: keep-all`, 본문·원문·긴 요약은
  `<details>`로 접고, 모든 값을 이스케이프한다(`&<>"'`, U+2028·U+2029 → 숫자 참조, 제어 문자 → U+FFFD).
  범주 이름·색·강조는 보관본의 분류 체계 데이터에서 온다(오류 표시는 `tone: danger` 범주).

```python
>>> from agent_console_logs import IndexBatch, LogFilter, QueryContext, build_archive, render_archive
>>> from agent_console_logs.testing import MemoryLogIndex, make_record
>>> index = MemoryLogIndex()
>>> _ = index.write(IndexBatch(records=[
...     make_record("llm", title="<답변>", session="S", detail={"text": "본문"}),
...     make_record("llm", title="다른 세션", session="T"),
... ]))
>>> archive = build_archive(index, LogFilter(session=("S",)), QueryContext(), exported_at=0.0)
>>> [(e.title, e.detail) for e in archive.events], archive.truncated
([('<답변>', {'text': '본문'})], False)
>>> page = render_archive(archive)
>>> "&lt;답변&gt;" in page, "<script" in page, "다른 세션" in page
(True, False, False)

```

## 기본 플러그인

| id | 출처 | 분류기 설정 |
| --- | --- | --- |
| `normalized-v1` | `roots`·`include`(기본 `**/*.jsonl`)·`exclude`, 기본 꺼짐 | `default_actor`(기본 `controller`). 필수 `schema_version: 1`·`category`·`title`, 예약 키 무시, actor = actor → thread → `default_actor` |
| `mapped-jsonl` | 위와 같음 | `fields`(필드 → JSON 포인터), `defaults`(기본 `{category: other}`), `value_maps`, `correlation`, `usage`, `skip_if_missing` |

새 출처는 `LogSource`(파일이면 `JsonlFileSource` 상속)를, 새 분류기는 `LogClassifier`를 구현하고
`pyproject.toml`의 entry point에 이름을 적는다. 다른 모듈의 데이터를 읽는 출처는
`LogIngestor.add_runtime_source(source, classifier=...)`로 더한다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

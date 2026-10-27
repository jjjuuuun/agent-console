# agent-console-link-logs-runs

로그·실행 연동 모듈(design §4R.8 연동 표 첫 행, R8.1·R8.2·R8.4·R8.6). 실행 기록(`runs.reader`·`runs.events`)을 로그(`mod-logs`의 `logs.ingest`·`logs.query`)에 잇는다.

- 런타임 출처 `platform-runs`(포트 `logs.sources`, 기본 켜짐): 이 콘솔의 실행 이벤트(RunEvent)를 Claude Code 세션 로그와 같은 정규화 이벤트로 색인한다. Run마다 마지막으로 읽은 이벤트 seq(워터마크) 뒤만 읽는다. 실행 기록은 읽기만 한다.
  - 분류기 `platform-run-event`(레지스트리 없이 출처가 직접 지정): 형식 → 범주·필드 대응표는 **데이터**다. 기본값 = 패키지 데이터 `run_event_map.yaml`, 덮어쓰기 = 설정 `logs.sources[id=platform-runs].config.event_map`(키별로 통째로). 대응표에 없는 형식은 범주 `other`.
  - 세션: 대응표의 `session_from` 규칙 이벤트(기본 `agent.session_started`)가 알린 세션 id를 그 노드와 하위 노드(서브에이전트) 이벤트에 붙이고, 없으면 NodeRun `backend_session_id`를 쓴다. 이벤트의 `session`과 `correlation.session`이 된다.
  - hook·MCP(R8.4): 수집기(X7)가 낸 `hook.*`·`mcp.*` 이벤트가 범주 `hook`·`mcp`로 보인다. MCP 호출은 `tool_use_id` 짝(시작·완료)으로, `hook.finished`처럼 소요 시간만 실린 이벤트는 대응표 `duration_ms`로 시작(근거 `inferred`)·끝 두 이벤트를 내어 타임라인에 소요 시간이 붙는다.
  - 토큰: 기본 대응표는 `agent.usage`를 토큰 표본으로 쓰지 않는다(같은 세션을 Claude Code 세션 로그 출처로도 읽으면 두 번 세어진다). 쓰려면 대응표에 `usage` 포인터를 넣는다.
- `runs.event` 구독 → 그 Run의 수집을 예약한다(디바운스, 설치자 옵션 `debounce_seconds` 기본 1초).
- `GET /runs/{id}/logs?<LogFilter>` → `LogEventPage`(`total` 항상 채움): 그 Run 세션 id들의 **외부 세션 이벤트**. 플랫폼 실행 이벤트(실행 상세의 다른 탭)는 기본으로 빼고, `source`를 직접 주면 그것을 따른다.
- 이 연동이 꺼지면 로그 화면에 플랫폼 실행이 없고, 실행 상세의 "세션 로그" 탭이 숨는다(웹 역할 `logs:runs`). `mod-logs`나 `mod-runs`가 꺼져도 꺼진다(필수 포트).

## 설치

```bash
pip install agent-console-link-logs-runs
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-logs-runs
```

## 최소 사용

서버 없이 메모리 실행 기록을 `platform-runs` 출처로 수집하고 질의한다(실제로는 `mod-runs`의 저장소와 `mod-logs`의 SQLite 색인).

```python
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex
>>> from agent_console_link_logs_runs import platform_runs
>>> from agent_console_link_logs_runs.testing import MemoryRunRecords, run_event, run_record

>>> records = MemoryRunRecords()                 # runs.reader·runs.events 모양
>>> records.runs.save(run_record("r1"))
>>> records.events.append(
...     run_event(1, "agent.session_started", {"session_id": "s1", "backend": "fake-agent"}),
...     run_event(2, "mcp.call_started", {"server": "docs", "tool": "find", "tool_use_id": "t1"}),
...     run_event(3, "mcp.call_completed", {"server": "docs", "tool": "find", "tool_use_id": "t1"}),
... )
>>> item = platform_runs(records.runs, records.events)   # 출처 + 분류기(같은 기본 대응표)
>>> index = MemoryLogIndex()
>>> ingestor = LogIngestor(index, LogRegistries())
>>> ingestor.add_runtime_source(item.source, classifier=item.classifier)
>>> ingestor.scan().new_events
3
>>> ingestor.scan().new_events                    # seq 워터마크: 새 이벤트가 없으면 0
0
>>> timeline = index.timeline("s1", query_context(None))
>>> [(e.category, e.stage, e.duration_ms) for e in timeline.events]
[('system', 'info', None), ('mcp', 'start', 1000.0), ('mcp', 'complete', 1000.0)]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 대응표(`run_event_map.yaml`)

```yaml
types:
  "*": {category: other, title: "{type}"}          # 키: 형식 또는 글롭(정확한 이름 → 긴 글롭 순)
  mcp.call_completed:
    category: mcp
    stage: complete
    tool: "mcp__{/payload/server}__{/payload/tool}" # 틀: {/JSON 포인터}·{type}·{node}·{parent_node}·{thread}·{actor}·{run_id}
    call_id: "{/payload/tool_use_id}"
    status: {pointer: /payload/is_error, map: {"true": error}, default: ok}
  hook.finished: {category: hook, duration_ms: /payload/duration_ms}   # 끝난 구간 → 시작·끝 두 이벤트
  agent.session_started: {category: system, session_from: /payload/session_id}
  agent.text_delta: {skip: true}
```

규칙 키 전체와 JSON Schema는 `RULE_SCHEMA`(설정 폼은 출처 디스크립터 `config_schema`의 `event_map`)에 있다. 파일을 비우거나 지워도 동작한다(모든 형식이 `other`).

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `logs.ingest` | `request_scan(source_ids, ref_hint=)` |
| 필수 | `logs.query` | `events(flt, with_total=)`·`aggregate(request)` |
| 필수 | `runs.reader` | `get(run_id)`·`list(limit=)`·`list_node_runs(run_id)` |
| 필수 | `runs.events` | `list(run_id, since_seq=, limit=)`·`last_seq(run_id)` |
| 구독 | `runs.event` | 그 Run 수집 예약(디바운스) |
| 제공 | `logs.sources` | `PlatformRunsLogSource(source, classifier)` |

설치자 옵션(`modules.options.link-logs-runs`): `debounce_seconds`(1.0, 0 = 바로). 출처 설정(사용자 데이터 `logs.sources[id=platform-runs].config`): `max_runs`(200, 수집 때 살펴볼 최근 Run 수), `event_map`.

출처 상태의 `pending_bytes`는 이 출처에서 "아직 읽지 않은 이벤트 수"다(단위가 Run 안 seq라서).

## 단독 실행

```bash
python -m agent_console_link_logs_runs [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_logs_module`(메모리 색인, 수집 예약 = 바로 수집)·`testing.runs_module`(빈 메모리 실행 기록)을 붙인다. 실제 실행·로그와 함께 띄우려면 `--with mod-logs --with mod-runs --with mod-definitions`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

# agent-console-link-logs-runs

로그·실행 연동 모듈(design §4R.8 연동 표 첫 행, R8.1·R8.2·R8.4·R8.6). 실행 기록(`runs.reader`·`runs.events`)을 로그(`mod-logs`의 `logs.ingest`·`logs.query`)에 잇는다.

- 런타임 출처 `platform-runs`(포트 `logs.sources`, 기본 켜짐): 이 콘솔의 실행 이벤트(RunEvent)를 Claude Code 세션 로그와 같은 정규화 이벤트로 색인한다. Run마다 마지막으로 읽은 이벤트 seq(워터마크) 뒤만 읽는다. 실행 기록은 읽기만 한다.
  - 분류기 `platform-run-event`(레지스트리 없이 출처가 직접 지정): 형식 → 범주·필드 대응표는 **데이터**다. 기본값 = 패키지 데이터 `run_event_map.yaml`, 덮어쓰기 = 설정 `logs.sources[id=platform-runs].config.event_map`(키별로 통째로). 대응표에 없는 형식은 범주 `other`.
  - 세션: 대응표의 `session_from` 규칙 이벤트(기본 `agent.session_started`)가 알린 세션 id를 그 노드와 하위 노드(서브에이전트) 이벤트에 붙이고, 없으면 NodeRun `backend_session_id`를 쓴다. 이벤트의 `session`과 `correlation.session`이 된다.
  - hook·MCP(R8.4): 수집기(X7)가 낸 `hook.*`·`mcp.*` 이벤트가 범주 `hook`·`mcp`로 보인다. MCP 호출은 `tool_use_id` 짝(시작·완료)으로, `hook.finished`처럼 소요 시간만 실린 이벤트는 대응표 `duration_ms`로 시작(근거 `inferred`)·끝 두 이벤트를 내어 타임라인에 소요 시간이 붙는다.
  - 토큰: 기본 대응표는 `agent.usage`를 토큰 표본으로 쓰지 않는다(같은 세션을 Claude Code 세션 로그 출처로도 읽으면 두 번 세어진다). 쓰려면 대응표에 `usage` 포인터를 넣는다(아래 "실행 단위 토큰").
  - 구조도 재료(design §5.5R.1): 맥락 구성 `agent.context_prepared`(범주 `context`, 리소스 id·종류·바이트 수·해시만), 모델 호출 소요(`agent.usage`의 `duration_ms`가 있으면 시작·끝 두 이벤트), MCP 서버 근거 `correlation.mcp_server`, 위임 호출 id 근거 `correlation.tool_use_id`(호출 NodeRun의 `node.*`). `node.started`의 `from`·`to`·`via`는 위임 호출(payload `call`)일 때만 채운다(조건부 값).
  - 메모리(design §5.7R.9): 메모리 도구 호출 `memory.*`(`link-memory-runs`)는 범주 `memory`, 문서 표지 `{kind: memory, path: <범위 종류>/<범위 id>/<키>, action: read·written·removed·searched}`(범위를 모르는 호출은 표지 없음), 근거 `tool_use_id`·`memory_scope`. 설정 `event_map`에 `"memory.*": {}`를 적으면 꺼져 범주 `other`가 된다.
- `runs.event` 구독 → 그 Run의 수집을 예약한다(디바운스, 설치자 옵션 `debounce_seconds` 기본 1초).
- `GET /runs/{id}/logs?<LogFilter>` → `LogEventPage`(`total` 항상 채움): 그 Run 세션 id들의 **외부 세션 이벤트**. 플랫폼 실행 이벤트(실행 상세의 다른 탭)는 기본으로 빼고, `source`를 직접 주면 그것을 따른다.
- 범위 종류(X27, 포트 `logs.scope_kinds`, design §5.5R.5): 로그 질의 필터 `scope=run:<Run id>` = 그 Run의 플랫폼 실행 이벤트(`run_id`) ∪ 그 Run의 세션들(NodeRun `backend_session_id` + 색인된 플랫폼 이벤트의 `session`, `/runs/{id}/logs`와 같은 계산)의 이벤트. `scope=run-tree:<Run id>` = 그 Run과 아래 모든 자식 Run(중첩 팀, `parent_run_id`)에 같은 계산. 위임 대상(호출 NodeRun)은 같은 Run 안이라 `run`에 든다. 없는 Run·빈 값은 422(`details.path = scope`). 이벤트 목록·집계·세션 목록·타임라인이 같은 범위를 따른다. 부품 `RunScopeKind`·`run_scope_kinds(runs, logs, kinds=)`(종류 id는 인자)·`run_sessions`·`run_tree_ids`.
- 이 연동이 꺼지면 로그 화면에 플랫폼 실행이 없고, 실행 상세의 "세션 로그" 탭이 숨는다(웹 역할 `logs:runs`). `scope=run:`·`run-tree:`는 모르는 범위 종류(422)가 된다. `mod-logs`나 `mod-runs`가 꺼져도 꺼진다(필수 포트).

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

값 규칙(`category`·`status`·`from`·`to` 등)은 틀 문자열 또는 조건부 값 `{pointer, map, default}`이고, 찾은 `map` 값과 `default`도 틀이다. 예: 호출 NodeRun일 때만 받는 쪽을 채운다.

```yaml
  node.started:
    to: {pointer: /payload/call, map: {"null": ""}, default: "{node}"}
```

### 목록 값(`each`, 5.7R.7)

`tags`·`correlation` 값·`documents`는 이벤트 안 목록의 원소마다 항목을 만들 수 있다. 형식은
`{each: <목록 포인터>, ...항목 틀}`이고, 항목 틀 안의 `{./키}`·`{.}`(원소 자체)와 조건부 값의
`pointer: ./키`는 그 원소 기준이다(`/…`는 이벤트 기준 그대로).

- `tags`: 글자 그대로의 태그 목록에 `{each, value}` 항목을 섞을 수 있다(또는 `{each, value}` 하나).
- `correlation`: 근거 이름 → 틀 문자열(값 하나, 전과 같음) 또는 `{each, value}`(값 여러 개).
- `documents`(새 키): 문서 틀 `{path, kind?, action?}`(값은 틀 또는 조건부 값) 하나 또는 목록. 틀에
  `each`를 주면 원소마다 문서 하나. 계약 `LogDocumentRef` 모양으로 목록 본문에 실린다.
- 결과가 빈 항목(문서는 `path`가 빈 항목)은 빼고 같은 항목은 한 번만 남긴다. 그래서 조건부 값의
  `default: ""`로 원소를 거를 수 있다. 목록이 비었거나 목록이 아니거나 원소가 객체가 아니면 항목 0개.
- 기존 값 형식(글자 그대로의 태그, 틀 문자열 근거)은 같은 뜻이다.

기본 대응표는 맥락 구성(`agent.context_prepared`)의 붙은 리소스를 문서로 옮긴다. 구조도 칸 조건은
목록 본문만 보므로(payload는 `detail`), 이렇게 옮겨야 기본 구조도 Rules 칸이 플랫폼 실행을 센다.
리소스 종류 id → 문서 종류 대응은 데이터다(종류 `rule` → `rules`, 규칙 리소스가 첫 문서).

```yaml
  agent.context_prepared:
    category: context
    documents:
      - each: /payload/resources        # 규칙 리소스만(다른 종류는 path가 비어 빠진다)
        kind: rules
        path: {pointer: ./kind, map: {rule: "{./id}"}, default: ""}
        action: read
      - each: /payload/resources        # 나머지(문서 종류 = 리소스 종류 id)
        kind: "{./kind}"
        path: {pointer: ./kind, map: {rule: ""}, default: "{./id}"}
        action: read
  x.done:
    tags: [done, {each: /payload/labels, value: "label:{.}"}]
    correlation: {resource: {each: /payload/resources, value: "{./id}"}}
```

순수 함수 `resolve_strings`·`resolve_documents`(모듈 `event_map`)로 서버 없이 같은 규칙을 쓸 수 있다.

규칙 키 전체와 JSON Schema는 `RULE_SCHEMA`(설정 폼은 출처 디스크립터 `config_schema`의 `event_map`)에 있다. 파일을 비우거나 지워도 동작한다(모든 형식이 `other`).

## 실행 단위 토큰(C3)

플랫폼 실행의 토큰을 로그 집계에 넣는 것은 **기본으로 꺼져 있다**. 백엔드가 Claude Code이면 같은 세션을 `claude-code` 출처(세션 로그)로도 읽어 토큰이 두 번 세어지기 때문이다. Claude Code 세션 로그를 읽지 않는 백엔드만 쓰거나 실행 단위 합계가 필요하면, 사용자 설정에서 `agent.usage` 규칙을 통째로 바꿔 `usage` 포인터를 넣는다.

```yaml
logs:
  sources:
    - id: platform-runs
      config:
        event_map:
          agent.usage:
            category: usage
            title: 사용량
            model: "{/payload/model}"
            duration_ms: /payload/duration_ms
            usage:
              input_tokens: /payload/usage/input_tokens
              output_tokens: /payload/usage/output_tokens
              # 긴 포인터는 접힘 스칼라(>-)로 다음 줄에 쓴다. 값은 한 줄 문자열과 같다.
              cache_read_input_tokens: >-
                /payload/usage/cache_read_tokens
              cache_creation_input_tokens: >-
                /payload/usage/cache_creation_tokens
```

`agent.usage`는 실행 중 누적값이라 `message_id`가 없으면 표본 키가 `<run_id>:<노드 경로>:<시도>`로 같아져 마지막 값만 남는다(이중 집계 없음). 켜면 구조도의 토큰 지표가 "수집 안 됨" 대신 값으로 보인다.

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `logs.ingest` | `request_scan(source_ids, ref_hint=)` |
| 필수 | `logs.query` | `events(flt, with_total=)`·`aggregate(request)` |
| 필수 | `runs.reader` | `get(run_id)`·`list(parent_run_id=, limit=)`·`list_node_runs(run_id)` |
| 필수 | `runs.events` | `list(run_id, since_seq=, limit=)`·`last_seq(run_id)` |
| 구독 | `runs.event` | 그 Run 수집 예약(디바운스) |
| 제공 | `logs.sources` | `PlatformRunsLogSource(source, classifier)` |
| 제공 | `logs.scope_kinds` | `RunScopeKind`(`id`·`resolve(value) -> LogScope`) — `run`·`run-tree` |

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

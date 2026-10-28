# agent-console-link-memory-runs

Agent Console 메모리·실행 연동 모듈(`link-memory-runs`, design §5.7R.2·§5.7R.3). 에이전트에게 공유
메모리 도구(검색·읽기·쓰기·지우기)를 준다. 실행 모듈(`mod-runs`)과 메모리 모듈(`mod-memory`)은 서로를
모르고, 이 연동이 실행 범위(X26 `runs.scopes`)로 Run마다 에이전트 도구 공급자(X30 `TOOL_PROVIDERS`)를
넣어 둘을 잇는다.

| 무엇 | 내용 |
| --- | --- |
| 받는 포트(필수) | `memory.service`(`mod-memory`). 없으면 이 연동은 꺼진다 |
| 주는 포트 | `runs.scopes`(Run마다 메모리 도구 공급자), `definitions.checks`(메모리 리소스의 모르는 범위 종류 → warning `memory.unknown_scope_kind`) |
| 리소스 종류 | `memory`(entry point `agent_console.resource_types`, 패키지 데이터 `data/memory_resource_type.yaml`, 설정 스키마 = 계약 `MemoryAccessConfig`, 범위 종류 칸은 `x-ui` 위젯 `memory-scope-kind`) |
| 실행 이벤트 | 도구 호출마다 `memory.read`·`memory.search`·`memory.write`·`memory.delete`(payload = 계약 `MemoryEventPayload`: 범위·키·id·버전·바이트 수·해시·결과 수·검색어 길이·해시·도구 이름·`tool_use_id`·처리 시간. **본문·검색어 원문 없음**) |
| 설치자 옵션 | `modules.options.link-memory-runs.max_writes_per_run`(기본 200, 비우면 한도 없음 — 넘으면 `rate_limited`) |
| 웹 역할 | `memory:runs`(실행 상세의 메모리 칩) |

- **opt-in**: 리소스 `memory`를 붙인 에이전트만 도구를 받는다. 도구 이름·설명·결과 머리 줄·범위별 권한은
  리소스 config(데이터)다. `delete` 도구는 지우기를 허용한 범위가 있을 때만 준다.
- **층**: 같은 칸에 여러 첨부(공통 → 팀 구성 → 에이전트 → 노드)가 있으면 범위 종류마다 가까운 층의
  허용 동작을 쓴다. 나머지 키(기본 범위·도구 이름 등)도 가까운 층이 정한 값이 이긴다(`merge_access`).
- **범위 id**는 맥락(`MemoryAccessContext`)에서 계산한다. `graph_id`는 그 노드를 실행한 Run의 팀
  구성(중첩 팀이면 자식 팀), `root_graph_id`·`project_id`는 루트 Run 값이다. 에이전트가 범위 id를 고를 수 없다.
- **실행당 쓰기 한도**는 Run 하나(자식 Run 포함)의 모든 에이전트가 함께 쓴다.
- **끄기**: `mod-memory`나 이 연동이 꺼지면 실행은 그대로 끝나고, 메모리 리소스를 붙인 노드마다 "백엔드가
  적용하지 못한 칸" 경고(R13.5, `resource.slot_unsupported`)가 1건 난다. 리소스 종류는 이 패키지가 설치돼
  있으면 연동을 꺼도 등록돼 있다(리소스를 만들 수는 있다).
- 메모리 내용은 다른 에이전트에게 지시처럼 읽힐 수 있다(보안 경계가 아니다). 쓰기 권한을 리소스로 좁힌다.

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-memory`(도구 묶음·범위 종류), `agent-console-nodes-core`(X30 공급자 프로토콜·서비스
  키), `agent-console-runtime`(`HostTool`), `agent-console-resources`(리소스 종류 베이스),
  `agent-console-store`(정의 종류 이름 `resource`), `agent-console-modkit`(모듈).
- 외부: pydantic, ruamel.yaml(디스크립터 데이터). 새 외부 의존 없음.

## 설치

```bash
pip install agent-console-link-memory-runs
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-memory-runs
```

## 최소 사용

서버·실행 엔진 없이 공급자 하나로 도구를 만들고 부른다(메모리 서비스는 주입).

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_memory import merge_scope_kinds
>>> from agent_console_nodes_core import ToolProvisionContext
>>> from agent_console_runtime import CancelToken
>>> from agent_console_link_memory_runs import MemoryToolProvider
>>> from agent_console_link_memory_runs.testing import StaticMemoryService
>>> service = StaticMemoryService(catalog=merge_scope_kinds(
...     include_defaults=False, user={"notes": {"label": "노트", "id": "{/graph_id}"}}))
>>> events = []
>>> async def emit(event_type, payload):
...     events.append((event_type, payload["status"], payload["scope"]))
>>> config = {"scopes": [{"kind": "notes", "access": ["read", "write"]}],
...           "tools": {"write": {"name": "jot", "description": "기록을 남깁니다"}}}
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="a", node_path=["a"],
...     agent_id="a", call=0, iteration=0,
...     bundle=ResourceBundle(slots={"memory": [{"config": config}]}),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken())
>>> provision = MemoryToolProvider(lambda: service, slot="memory").provide(ctx)
>>> [t.name for t in provision.host_tools], sorted(provision.consumed_slots)
(['memory_read', 'jot'], ['memory'])
>>> asyncio.run(provision.host_tools[1].handler({"key": "결정", "content": "v2"})).is_error
False
>>> events
[('memory.write', 'ok', {'kind': 'notes', 'id': 'team'})]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

단독 실행(메모리 저장소 서비스 모듈과 함께): `python -m agent_console_link_memory_runs --check`.
실제 모듈과: `--with mod-memory --with mod-runs`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

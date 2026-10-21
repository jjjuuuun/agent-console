# agent-console-trace

한 실행의 RunEvent에서 **위임 흐름**("누가 누구에게 일을 넘겼고 언제 돌아왔는지")을 만들고,
여러 실행을 모아 **"누가 누구에게 몇 번"** 을 센다. `agent_console_contracts`에만 의존하는 순수 라이브러리다.

- `build_trace(events, *, edge_kinds=, call_edges=, node_runs=, children=) -> Trace`
  - 노드 실행 = `node` span(자기 NodeRun·세션, 시도·반복 회차마다 하나, `iteration`).
  - 위임자가 부른 호출 NodeRun(독립 위임) = 위임자 span의 **자식** `node` span(별도 세션, `call`, 호출
    회차마다 하나). 위임자 → 호출 링크도 싣는다(`call_edges`로 연결 id·종류, 부모-자식이라 화면은
    화살표로 그리지 않는다). 위임 과제 미리보기는 `node_runs`(호출 NodeRun 입력)에서.
  - 서브에이전트 = 위임자 span의 **자식** `delegated` span(같은 세션 id, 위임 과제·결과 미리보기·사용량).
  - 넘기기 = 형제 `node` span 사이의 화살표 `TraceLink`(`edge.traversed`). 도착 span에 넘김 순번 `order`.
    사이클 연결(반복)은 다음 회차 span으로 가는 링크다(`kind` = 연결 종류).
  - 상호작용 = 요청한 span의 자식 `interaction` span("사용자 대기", `interaction_id`).
  - 자식 Run(중첩 팀) = `children`(자식 Run id → 그 Run의 trace)을 `run.child_started`를 낸 노드 span
    아래에 붙인다. 자식 Run의 span·링크에는 `run_id`가 실리고 span id는 `run:<자식 Run>/<원래 id>`다.
- `handoff_matrix(traces) -> HandoffMatrix` — (넘긴 쪽, 받은 쪽, 종류)별 횟수, 많은 순.
  agent_bench `log_store`의 handoff edges 질의(보낸 쪽·받는 쪽·via·횟수, 횟수 내림차순)를 위임 흐름 위로 옮겼다.

## 연결 원칙: 명시 id만

시간상 가까운 이벤트를 인과로 잇지 않는다(agent_bench `link_events` 원칙). 연결 키가 없으면 부모 없이 남긴다.

| 관계 | 연결 키 |
| --- | --- |
| 노드 span | `node.*`의 `node_path == [노드]` + `attempt` + payload `iteration` |
| 호출 span | `node.*`의 `node_path`(위임자 경로 + 대상) + payload `call`. 부모 = 경로 앞부분(NodeRun `invoked_by`)의 span |
| 호출 span 안 이벤트 | 같은 경로의 **열린** 호출 span(엔진이 같은 대상을 직렬로 돌려 경로마다 하나). 끝난 호출에는 붙이지 않는다 |
| 반복 회차 span 안 이벤트 | 그 노드의 가장 최근 회차 span(한 노드는 한 번에 한 회차만 돈다) |
| 자식 Run 묶음 | `run.child_started.child_run_id` → 이벤트 `node_path`가 가리키는 span. 없으면 부모 없이 붙인다 |
| 위임 span의 부모 | `agent.subagent_started.tool_use_id` = 부모의 `agent.tool_call.tool_use_id`, 없으면 `node_path` 앞부분 |
| 위임 span의 끝 | `agent.subagent_stopped.subagent_id`(없으면 `tool_use_id`) |
| 상호작용 span | `interaction.requested/answered/closed`의 `interaction_id`, 부모는 상호작용의 `node_path`·`attempt` |
| 넘김 화살표 | `edge.traversed`의 출발·도착 노드 id |

같은 경로로 위임이 여러 번 열려 있어 경로만으로 어느 쪽인지 모르면, 가장 최근 것에 붙이지 않고 한 단계 위(위임자 노드)에 붙인다.

## 설치

```bash
uv sync --all-packages                    # 워크스페이스 안에서
uv pip install ./packages/py/features/ac-trace     # 다른 프로젝트에서 단독으로(ac-contracts 필요)
```

## 최소 사용 예

```python
>>> from agent_console_contracts import RunEvent
>>> from agent_console_trace import build_trace, handoff_matrix

```

실제로는 저장소의 이벤트(`event_repo.list(run_id)`)를 넘긴다. 여기서는 pl → qa 넘기기 하나를 손으로 만든다.

```python
>>> def events(run_id):
...     rows = [
...         ("node.started", ["pl"], {"status": "running"}),
...         ("node.completed", ["pl"], {"status": "succeeded"}),
...         (
...             "edge.traversed",
...             [],
...             {
...                 "edge_id": "h1",
...                 "source": {"node": "pl", "port": "out"},
...                 "target": {"node": "qa", "port": "in"},
...             },
...         ),
...         ("node.started", ["qa"], {"status": "running"}),
...         ("node.completed", ["qa"], {"status": "succeeded"}),
...     ]
...     return [
...         RunEvent(
...             event_id=f"{run_id}-{seq}",
...             run_id=run_id,
...             seq=seq,
...             ts=float(seq),
...             node_path=path,
...             attempt=1 if path else None,
...             actor=path[0] if path else None,
...             type=type,
...             payload=payload,
...         )
...         for seq, (type, path, payload) in enumerate(rows, start=1)
...     ]
>>> edge_kinds = {"h1": "handoff"}  # 선택: 화살표에 연결 종류 표시(그래프의 edge.id → kind)
>>> trace = build_trace(events("r1"), edge_kinds=edge_kinds)  # Trace{spans, links}
>>> [s.id for s in trace.spans]
['node:pl#1', 'node:qa#1']
>>> [(link.source, link.target, link.kind) for link in trace.links]
[('node:pl#1', 'node:qa#1', 'handoff')]

>>> matrix = handoff_matrix(build_trace(events(r), edge_kinds=edge_kinds) for r in ["r1", "r2"])
>>> for cell in matrix.cells:  # 여러 실행의 "누가 누구에게 몇 번"
...     print(cell.source, "→", cell.target, cell.kind, cell.count)
pl → qa handoff 2

```

span 종류 이름은 상수 `SPAN_KIND_NODE`·`SPAN_KIND_DELEGATED`·`SPAN_KIND_INTERACTION`, span id는
`node_span_id`·`call_span_id`·`delegated_span_id`·`interaction_span_id`·`child_span_id`로 만든다.
깊이 초과·순환으로 거부된 호출은 NodeRun이 없어(`log.warning`만) span도 없다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-trace`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-trace
```

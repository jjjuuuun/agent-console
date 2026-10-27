# agent-console-graph

그래프 정의 순수 로직: 구조 검증, 포트 해석, 위상 정렬·사이클 검사, 버전 해시.
특정 노드·엣지 타입을 모른다. 타입 목록(디스크립터)과 동적 포트 해석기는 **인자로 받는다**.

## 설치

워크스페이스 안에서:

```bash
uv sync --all-packages
```

단독 설치(다른 프로젝트에서):

```bash
uv pip install ./packages/py/base/ac-graph
```

의존: `agent-console-contracts`, `jsonschema`, `referencing`

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `jsonschema` (>=4.23) | 노드·엣지 `config`를 타입의 `config_schema`로 검사 | JSON Schema 2020-12 등 초안 전체를 지원하는 사실상 표준 구현, 오류 위치(`absolute_path`)를 줘서 `Issue.path`(JSON Pointer)로 바로 변환 가능. `_schema.py` 한 곳에 가둬 교체 쉬움 | `fastjsonschema`(빠르지만 첫 오류만, 위치 정보 약함), Pydantic 모델 동적 생성(스키마 기능 일부만) |

| `referencing` (>=0.28, jsonschema의 의존) | `$ref` 해석 레지스트리를 직접 지정 | 외부 `$ref`(URL·파일)를 **가져오지 않고** 해석 불가(`invalid_config_schema`)로 처리하기 위해. 로컬 `#/...`·`$defs`만 허용 | jsonschema 기본 동작에 맡기기(버전마다 달라질 수 있음) |

> mypy 타입은 루트 dev 그룹의 `types-jsonschema`가 제공한다.
> 한 번의 `validate_graph` 호출 안에서 디스크립터별 검사기를 캐시한다(5,000노드 ≈ 0.2초).

## 공개 API

```python
validate_graph(graph, node_types, edge_types, *, resolve_ports=None, cycle_edge=None,
               validate_node=None) -> list[Issue]
graph_hash(graph) -> str                 # sha256 hex
canonical_graph(graph) -> dict           # 해시 대상 정규 문서
topology(graph, *, ignore_edge=None) -> Topology
node_ports(descriptor, config, resolve_ports=None) -> PortSpec
schedule_view(graph, node_types, edge_types) -> ScheduleView
non_flow_edges(edge_types) -> EdgeFilter   # topology(ignore_edge=)용: scheduling != flow면 참
descriptor_cycle_edge(edge, descriptor) -> bool          # validate_graph(cycle_edge=)용: 디스크립터 cycle이 있으면 참
loop_regions(graph, edge_types) -> dict[str, LoopRegion] # 사이클 연결 id → 반복 영역
effective_max_iterations(edge, descriptor, settings_value=None) -> int | None
```

- `node_types` / `edge_types`: `NodeTypeDescriptor` / `EdgeTypeDescriptor`의 iterable(여러 버전 가능).
  `NodeSpec.type_version`이 없으면 같은 id의 최신 버전, 엣지는 항상 최신 버전.
- `resolve_ports(descriptor, config) -> PortSpec`: 동적 포트 해석기(`PortResolver`). 보통 노드 타입 구현의
  `resolve_ports(config)`를 감싼다. 없으면 동적 포트 노드는 `ports_unresolved` 경고 후 포트 검사 생략.
- `cycle_edge(edge, edge_descriptor) -> bool`: 참이면 그 흐름 엣지는 사이클 검사에서 빠진다. 기본은 DAG만 허용.
  디스크립터 `scheduling`이 `flow`가 아닌 엣지(`none`·`entry`·`exit`)는 항상 사이클 계산에서 빠진다
  (예: `사용자 → A →(답변) 사용자`는 순환이 아니다, design §R3.1).
- `validate_node(node, descriptor) -> Iterable[Issue]`: 스키마 외 의미 검증(스키마 통과 노드에만 호출).

### Issue code (`GraphIssueCodes`)

| code | 대상 | severity | `path` / `details` |
| --- | --- | --- | --- |
| `duplicate_node_id` | node_id | error | |
| `duplicate_edge_id` | edge_id | error | |
| `unknown_node_type` | node_id | error | `{type, type_version}` |
| `unknown_edge_type` | edge_id | error | `{kind}` |
| `invalid_config` | node_id 또는 edge_id | error | `path`=config 기준 JSON Pointer, `{validator, schema_path}` |
| `invalid_config_schema` | node_id 또는 edge_id | error | 타입의 `config_schema` 자체가 잘못됨(메타스키마 위반, 해석 불가 `$ref`), `path=""` |
| `port_resolution_failed` | node_id | error | `{error}` (예외 클래스 이름) |
| `ports_unresolved` | node_id | warning | 동적 포트인데 해석기 없음 |
| `unknown_node` | edge_id | error | `{end: source\|target, node}` |
| `unknown_port` | edge_id | error | `{end, node, port, available}` |
| `cycle` | 그래프 | error | `{nodes: [...]}` (강한 연결 요소, 자기 루프 포함). `cycle_edge` 술어가 참인 연결은 빼고 계산. 술어를 주면 수정 제안이 붙는다(아래) |

### 반복 영역 (design §5R.4)

- **사이클 연결** = 연결 종류 디스크립터에 `cycle`(`CyclePolicy`)이 있는 흐름 연결. 이름을 보지 않는다.
  `validate_graph(..., cycle_edge=descriptor_cycle_edge)`이면 흐름 사이클마다 사이클 연결이 하나 이상 있어야 한다(없으면 `cycle`).
- **"반복 연결로 바꾸기" 제안**(`cycle_edge`를 줬을 때): 사이클 묶음 안의 되돌아가는 연결(묶음 밖에서 들어오는 노드부터
  깊이 우선으로 따라가 탐색 경로로 돌아가는 연결)마다, 바꿨을 때 술어가 참이 되는 흐름 종류 중 `connects`(노드 타입
  `role`)와 config 스키마가 맞는 첫 종류(숨긴 종류 제외)로 바꾸는 `Issue.suggestions[{id: "cycle:<엣지>:<종류>", label,
  patch: {remove_edge_ids: [엣지], add_edges: [같은 id·포트, 새 종류, 새 스키마가 선언한 config 키만]}}]`. 맞는 종류가 없으면
  제안이 없고 문구도 그대로다.
- `loop_regions`: 사이클 연결 `e(s → t)`마다 `LoopRegion{edge_id, nodes, entry=t, exit=s}`. `nodes` = `t`에서 `s`로 가는 흐름 경로 위
  노드(`graph.nodes` 순서, 모든 사이클 연결을 빼고 계산 — 중첩 반복의 안쪽 영역은 바깥 영역의 부분 집합). `s = t`면 `(s,)`.
  사이클을 닫지 않는 앞쪽 연결, 없는 노드를 가리키는 연결은 결과에 없다.
- `effective_max_iterations`: 엣지 config `max_iterations`(`CYCLE_LIMIT_CONFIG_KEY`) → 설정 값 → 디스크립터 `cycle.max_iterations`
  (생략 = 상속). 사이클 연결이 아니거나 config 값이 정수가 아니면 None, 1 미만도 그대로 돌려준다(판단은 호출자).

```python
>>> from agent_console_contracts import CyclePolicy, EdgeTypeDescriptor, Graph
>>> from agent_console_graph import loop_regions
>>> again = EdgeTypeDescriptor(id="my-again", title="다시", cycle=CyclePolicy(max_iterations=2))
>>> loop_graph = Graph.model_validate(
...     {
...         "id": "g",
...         "name": "g",
...         "nodes": [{"id": "a", "type": "x"}, {"id": "b", "type": "x"}],
...         "edges": [
...             {"id": "ab", "source": {"node": "a", "port": "o"},
...              "target": {"node": "b", "port": "i"}, "kind": "my-wire"},
...             {"id": "back", "source": {"node": "b", "port": "o"},
...              "target": {"node": "a", "port": "i"}, "kind": "my-again"},
...         ],
...     }
... )
>>> loop_regions(loop_graph, [again])["back"].nodes
('a', 'b')

```

### `graph_hash` 정규화 규칙

1. 계약 모델로 직렬화(`mode="json"`, 별칭) — 생략한 필드 = 기본값을 명시한 필드. 보존된 모르는 필드는 포함.
2. 표시 전용 필드 제거: 그래프 `ui`, 노드 `position`·`layout`, 엣지 `layout`(화면 배치, E-3).
3. `nodes`·`edges`는 `id` 순으로 정렬(목록 순서 무관). 그 밖의 목록 순서는 유지.
4. 정규 JSON(키 정렬, 공백 없는 구분자, UTF-8) → sha256 hex.

### `schedule_view` (design §R3.1)

엣지 디스크립터 `scheduling`(`flow`·`none`·`entry`·`exit`)과 노드 디스크립터 `executable`만으로 계산한다(이름을 모른다).

| 필드 | 뜻 |
| --- | --- |
| `entry_nodes` | `entry` 엣지가 들어오는 실행 가능 노드(입구). **명시된 엣지뿐**이며 그래프 모양으로 추론하지 않는다 |
| `scheduled` | 실행 가능하고 `entry`·`flow` 엣지가 하나 이상 들어오는 노드(스케줄 대상) |
| `incoming` / `outgoing` / `exits` | 스케줄 대상의 `entry`·`flow` 입력, 노드별 `flow` 출력, `exit` 출력 엣지 id |
| `exit_nodes` | `exit` 엣지가 나가는 노드(답변을 내는 노드) |
| `scheduling`, `*_edges` | 엣지별·종류별 분류(타입을 모르는 엣지는 빠짐) |
| `topology` | `flow` 엣지만으로 계산한 위상 정보 |

## 최소 사용 예

```python
>>> from agent_console_contracts import (
...     EdgeTypeDescriptor,
...     Graph,
...     NodeTypeDescriptor,
...     PortDef,
...     PortSpec,
... )
>>> from agent_console_graph import graph_hash, topology, validate_graph

>>> src = NodeTypeDescriptor(
...     id="my-src", title="Src", static_ports=PortSpec(outputs=[PortDef(name="o")])
... )
>>> dst = NodeTypeDescriptor(
...     id="my-dst", title="Dst", static_ports=PortSpec(inputs=[PortDef(name="i")])
... )
>>> wire = EdgeTypeDescriptor(id="my-wire", title="Wire")
>>> graph = Graph.model_validate(
...     {
...         "id": "g",
...         "name": "g",
...         "nodes": [{"id": "a", "type": "my-src"}, {"id": "b", "type": "my-dst"}],
...         "edges": [
...             {
...                 "id": "e",
...                 "source": {"node": "a", "port": "o"},
...                 "target": {"node": "b", "port": "i"},
...                 "kind": "my-wire",
...             }
...         ],
...     }
... )
>>> validate_graph(graph, [src, dst], [wire])  # 문제 없음
[]
>>> topology(graph).order
('a', 'b')
>>> len(graph_hash(graph))  # 정규화한 그래프의 sha256(버전 식별)
64
>>> [i.code for i in validate_graph(graph, [src], [wire])]  # 모르는 노드 종류는 이슈로
['unknown_node_type']

```

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-graph`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/base/ac-graph/tests
```

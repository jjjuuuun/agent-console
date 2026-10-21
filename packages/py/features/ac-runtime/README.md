# agent-console-runtime

그래프 실행 엔진(토큰 기반 asyncio 스케줄러)과 확장 인터페이스.
엔진은 특정 노드·엣지 타입·백엔드를 모른다. 모든 능력은 `Registries`에 등록된 구현으로 들어온다.
설계: `specs/agent-console/design.md` §3.3, §4.2~§4.5, §5.6, §R3.1~§R3.5, §R14.5.

## 설치

```bash
uv sync --all-packages                     # 워크스페이스 안
uv pip install ./packages/py/features/ac-runtime    # 단독
```

의존: `agent-console-contracts`, `agent-console-registry`, `agent-console-graph` (저장소·라우팅·플러그인을 모른다)

## 최소 사용 예

```python
>>> import asyncio
>>> from agent_console_runtime import GraphRuntime, InMemoryEventBus
>>> from agent_console_runtime.testing import (
...     InMemoryRecorder,
...     edge,
...     graph,
...     make_registries,
...     node,
...     reply,
... )

```

실제로는 `registries = Registries(); load_registries(registries)`(entry point `agent_console.node_types` /
`edge_types` / `backends`)로 설치된 타입을 읽는다. 여기서는 엔진이 아무 타입도 모른다는 것을 보이는
테스트 타입(`t.step` 노드, `t.flow`·`t.entry`·`t.exit` 엣지)을 쓴다.

```python
>>> async def main():
...     registries = make_registries()
...     bus = InMemoryEventBus()
...     runtime = GraphRuntime(registries, InMemoryRecorder(), bus, max_concurrency=4)
...     # 그래프에는 입구 엣지(디스크립터 scheduling="entry")가 있어야 한다. 없으면 NoEntryError.
...     g = graph(
...         [node("a"), node("b", outputs={"out": "완료"})],
...         [edge("a", "b"), reply("b")],
...         entries=["a"],  # 사용자 자리 you → a 입구 엣지
...     )
...     events = bus.subscribe()  # run_id=로 한 Run만 받을 수도 있다
...     handle = await runtime.start(g, {"text": "hello"}, origin="api")
...     async for event in events:
...         if event.type == "run.reply":
...             print("답변:", event.payload["text"])
...         if event.type == "run.completed":
...             break
...     events.close()
...     run = await handle.wait()  # 또는 runtime.cancel(handle.run_id)
...     print(run.status)
...     await runtime.shutdown(timeout=10)  # 앱 종료: 협조 취소 → 넘으면 태스크 강제 취소
>>> asyncio.run(main())
답변: 완료
completed

```

**종료 공개 순서(5.2R.39)**: `RunHandle.run`이 종료 상태(`completed`·`failed`·`cancelled`·`interrupted`·parked
`waiting`)를 보이면, 그 Run의 기록 — 답변(`run.reply`) 등 모든 이벤트, 최종 Run 저장, `run.<상태>` 이벤트 — 은
이미 저장소에 저장되고 `event_sink`로 발행됐다. 종료 처리 중에는 직전 상태(`running` 등)를 보인다.

`start(..., conversation_id=)`는 Run 메타(`Run.conversation_id`)다. 엔진은 의미를 모르고 기록만 하며, 그 Run의
상호작용(`Interaction.conversation_id`)에 같은 값이 복사된다(채팅 어댑터가 채운다, 1R.14).

운영에서는 `agent_console_store`의 `SqliteStorage`/`InMemoryStorage`를 recorder로 넘긴다(구조적 타이핑).
서버 시작 시 `recover_unfinished_runs(storage, sink=bus)`로 이전 프로세스의 Run을 `interrupted`로 정리한다
(대기 중 상호작용 `expired(interrupted)` + `interaction.closed`, waiting 포함 끝나지 않은 NodeRun `cancelled(interrupted)`).

## 확장 인터페이스

| 지점 | 프로토콜 | 핵심 메서드 |
| --- | --- | --- |
| X1 노드 타입 | `NodeType` | `descriptor`, `resolve_ports(config)`, `validate(config, ValidationContext)`, `async execute(NodeContext, inputs) -> NodeResult` |
| X2 엣지 타입 | `EdgeType` | `descriptor`, `activates(NodeRunView, EdgeSpec) -> Activation \| Blocked \| None`. `Activation.condition`(근거 → `edge.traversed.condition`)·`warnings`(→ `log.warning`), `Blocked(reason, condition, warnings)` = dead-path + `edge.skipped`. 선택 능력 `EdgeValidator.validate_edge(edge, EdgeValidationContext)`(저장 전 의미 검사, `validate_graph_with`가 부름) |
| X1 선택 훅 | `NODE_ACTOR_HOOK = "actor_of"` | `actor_of(config) -> str \| None`: 이 노드 자리의 에이전트 정의 id. 엔진이 그 노드의 `node.*`·`run.reply`·`ctx.emit` 이벤트 머리 `actor`에 쓴다 |
| X1 선택 훅 | `NODE_NAME_HOOK = "display_name"` | `display_name(config, services) -> str \| None`: 노드에 `label`이 없을 때 사용자 문구에 쓸 이름(예: 묶인 에이전트 정의 이름). 실행 실패 요약·위임 거절 문구는 `node_display_name`(label → 이 훅 → 타입 `title`)으로 노드를 부르고 id는 `details.node_id`에 둔다. 실패 요약은 원인 `ErrorInfo.fix`를 그대로 잇는다 |
| X3 실행 백엔드 | `ExecutionBackend` | `descriptor`, `async list_models()`, `async run(AgentRequest, BackendEventSink, CancelToken) -> AgentResult`. `AgentRequest.run_folder`(노드 실행 폴더, 산출물용·없으면 None)·`run_context`(`run_id`·`node_path`)는 노드가 채운다(4R.9 hook probe 기록 위치) |
| X3 선택 sink 능력 | `SubagentResultListener` | `async on_subagent_result(name, *, text, status, actor, tool_use_id)`: 서브에이전트 호출 하나가 끝날 때마다. 백엔드는 `isinstance(sink, SubagentResultListener)`일 때만 알리고, 위임 방식이 sink를 감싸 대상 답변(`emit_replies`)을 낸다 |
| X3 선택 훅 | `ConfigurableBackend` (`BACKEND_OPTIONS_HOOK = "from_options"`) | `classmethod from_options(options: Mapping, *, secrets: SecretResolver, environ: Mapping[str, str]) -> ExecutionBackend`. 앱 설정 `backends.<id>`로 다시 만들 수 있는 백엔드가 구현한다. 앱은 훅 유무만 보고, 키 해석은 백엔드 패키지가 한다(모르는 키는 `ValueError`) |
| X3 선택 능력 | `StatusCapableBackend` / `ProbeCapableBackend` (디스크립터 `capabilities.status`·`probe`와 함께) | `async status(BackendCheckContext) -> BackendReadiness`(모델·네트워크 호출 금지, 빨리 끝남), `async probe(BackendCheckContext, timeout_s) -> BackendProbeResult`(가장 짧은 실제 호출 한 번, 실패는 `ok=false`+`reason`). `BackendCheckContext`는 `backend_id`·`clock`·`has_secret(name)`(존재만, 값 없음). 조회 서비스 `BackendReadinessService(backends, redact=, has_secret=, probe_timeout_max_s=)`: 능력 없으면 상태 `unknown`·probe는 `ProbeUnsupportedError`, 시간 상한·자르기, 같은 백엔드 동시 probe 합치기, 응답 글자 가림, 로그는 id·ok·reason·소요 시간만(ux-overhaul §15.8) |
| X10 비밀 공급자 | `SecretProvider` | `get_secret(name) -> str \| None` (기본 구현 `EnvSecretProvider(environ)`) |
| X12 위임 방식 | `DelegationStrategy` | `descriptor: DelegationStrategyDescriptor`, `validate(DelegationPlan) -> list[Issue]`, `async run(DelegationPlan, NodeContext) -> AgentResult`. 레지스트리 `registries.delegation_strategies`(= `extension(DELEGATION_STRATEGIES_EXTENSION)`), entry point `agent_console.delegation_strategies`. 선택 프로토콜 `ComposableDelegation`(`contribute(plan, ctx) -> DelegationContribution`, 디스크립터 `composable`): 노드가 여러 방식의 결과를 `merge_contributions`로 합치고 `apply_contribution`으로 요청에 더해 백엔드를 한 번 부른다(혼합 위임, design §5R.6). 저장 시점 선택 프로토콜(design §5.2R.7): `StaticDelegationChecks`(`static_issues(config, members) -> list[Issue]`, 스키마 밖 정적 규칙)·`DelegationNameDeclarer`(`declared_names(config, members) -> {묶음: [이름]}`, 묶음 예 `DelegationNameGroups`, 충돌 코드 `duplicate_names_code(묶음)`), 대상은 `DelegationMemberView`(정적 필드) |
| X15 상호작용 종류 | `InteractionKind` | `descriptor: InteractionKindDescriptor`(요청·응답 스키마, `expire_response`, 화면 힌트). 레지스트리 `registries.interaction_kinds`(= `extension(INTERACTION_KINDS_EXTENSION)`), entry point `agent_console.interaction_kinds`(`load_registries`가 로드, 디스크립터 객체를 가리켜도 `StaticInteractionKind`로 감싼다) |
| 저장 | `RunRecorder` | `runs.save/save_node_run/list_node_runs/interrupt_unfinished`, `events.append/append_many/last_seq`, `interactions.save/get/close/close_pending`(`InteractionWriter`, `close`는 pending 조건부, 이미 닫혔으면 `code == "interaction_closed"`·`interaction` 속성이 있는 예외) |
| 발행 | `EventSink` | `publish(event)` (막히지 않아야 함) |
| 자식 Run 준비 | `ChildRunPreparer` | `(ChildRunRequest) -> ChildRunPreparation \| Awaitable[...]`. `GraphRuntime(child_preparer=)`(속성으로 바꿔 끼울 수 있음). 막으려면 `GraphValidationError` (design §5R.7) |

레지스트리 key는 디스크립터 `id`와 같아야 한다(`NodeSpec.type`·`EdgeSpec.kind`로 찾는다).
runtime이 모르는 확장 지점(예: 플러그인이 정의한 분류기)은 `registries.extension("my_classifiers", validator=as_x)`로 담는다.
검사기를 붙이면 entry point·모듈·`register(registries)` 플러그인·직접 `register` 모두 같은 검사를 거친다(거부 →
`InvalidExtensionError`, 로더에서는 `failed`). 기본 레지스트리(노드·엣지·백엔드·비밀 공급자·위임 방식·상호작용 종류)에는
`as_node_type` 등이 이미 붙어 있다.

```python
from agent_console_runtime import load_registry_plugins, session_refs

# 설정 plugins.modules: register(registries) 플러그인. enabled에 없는 key는 해제하고 "disabled"로 보고
reports = load_registry_plugins(["my_pkg.plugin:register"], registries, enabled=None)

# 대화 저장본의 세션(계약 SessionRef) → 노드 서비스 SESSIONS 값(엔진 SessionRef)
services = services.with_(SESSIONS, session_refs(conversation_sessions))
```

### NodeContext

`run`, `graph`, `node`, `config`, `attempt`, `iteration`, `actor`, `registries`, `backends`, `services`, `secrets`,
`cancel`, `clock`/`now()`, `node_path`, `child_path(node_id)`, `await emit(type, payload, raw=, evidence=, actor=, node_path=)`,
`await emit_replies(node_id, outputs, status=, actor=)`,
`await request_input(InteractionRequest) -> InteractionOutcome`, `interaction_grant`, `incoming(port=None) -> list[Incoming]`,
`previous_session_id`, `await invoke_node(node_id, inputs, by_edge=, max_depth=None) -> NodeRunView`, `call`, `invoked_by`,
`await run_child(graph, input=None, graph_version=None, services=None) -> ChildRunResult`.

- `incoming`: 이 노드로 들어온 값(통과한 엣지마다 `Incoming{port, edge_id, source_node, source_port, value}`, 들어오는 엣지 순서).
  `execute`의 `inputs`는 호환을 위해 포트마다 첫 값만 담는다. join `all` 합류 값을 모두 쓰려면 이것을 쓴다.
  반복 회차(아래 "반복")에서는 이전 회차 전에 도착해 남아 있는 값에 `carried=True`가 붙고, `inputs` 첫 값은 새 값이 먼저다.
- `iteration`: 반복 회차(0부터). `previous_session_id`: 같은 노드 직전 회차 결과의 `backend_session_id`(없으면 None).

- `emit`: 머리 필드(run_id·seq·ts·attempt)는 엔진이 채운다. `run.*`·`node.*`·`edge.*`는 엔진 전용.
  알려진 type은 계약 payload 형식을 검사한다. `NodeContext`는 `BackendEventSink`를 만족하므로 `backend.run(req, ctx, ctx.cancel)`.
  `actor`를 생략하면 노드의 actor, `node_path`를 생략하면 `[노드]`. 위임 대상(하위 에이전트) 이벤트는
  `node_path=ctx.child_path(대상)`, `actor=대상 에이전트`로 낸다. 이 노드 경로로 시작하지 않는 경로는 `ValueError`.
- `emit_replies`: 이 노드에서 `invocation` 연결로 닿는 대상 노드의 답변 엣지(`scheduling = exit`)를 평가해 `run.reply`를 낸다
  (대상은 스케줄되지 않으므로 위임 방식이 결과마다 부른다). 호출 대상이 아니면 `ValueError`.
- `services`: 앱 제공 서비스의 타입드 조회. 서비스를 쓰는 플러그인이 `ServiceKey[T]("name")`를 정의·공개하고 앱이 같은 키로 주입한다.
- `secrets`: `resolve("secret://name")`, `resolve_refs(obj)`. 해석한 값은 이벤트·오류 메시지에서 `[REDACTED]`로 가려진다.

### 플랫폼 도구 (`HostTool`, design §5R.6, 런타임 전용)

위임 방식이 모델에게 줄 도구를 만들어 `AgentRequest.host_tools`에 넣고, `capabilities.host_tools`를 선언한 백엔드가
모델의 호출마다 `handler`를 부른다. 계약 타입이 아니며 `AgentRequest.model_dump()`에 나오지 않는다.

- `HostTool(name, description, input_schema, handler)`, `HostToolResult(text, is_error=False)`,
  `HostToolHandler = Callable[[dict], Awaitable[HostToolResult]]`
- 백엔드 공용: `await call_host_tool(tool, args, cancel=)`(예외 → 오류 결과(형식 이름만), 실행 취소 → 핸들러 취소 후
  오류 결과, 바깥 취소는 그대로 전파), `duplicate_host_tool_names(tools)`, `object_input_schema(schema)`

```python
>>> import asyncio
>>> from agent_console_runtime import HostTool, HostToolResult, call_host_tool
>>> async def handler(args):
...     return HostToolResult(text=f"맡김: {args['task']}")
>>> tool = HostTool("delegate", "다른 에이전트에게 맡긴다", {"type": "object"}, handler)
>>> asyncio.run(call_host_tool(tool, {"task": "검토"}))
HostToolResult(text='맡김: 검토', is_error=False)

```

## 스케줄러 의미

엔진은 연결 종류·노드 타입 이름을 모른다. 엣지 디스크립터 `scheduling`과 노드 디스크립터 `executable`만 본다
(`agent_console_graph.schedule_view`).

| `scheduling` | 엔진 동작 | 위상·사이클 |
| --- | --- | --- |
| `entry` | Run 시작 때 `activates`를 부른다. 소스는 `{소스 포트: Run 입력 dict}`를 출력으로 가진 성공 결과로 보인다. 통과 값이 도착 노드(입구) 입력 포트로 들어간다 | 제외 |
| `flow` | 소스가 끝나면(succeeded·failed) `activates` → 통과하면 도착 입력 포트에 값, 아니면 dead | 포함 |
| `exit` | 소스가 끝나면(succeeded·failed) `activates` → 통과하면 `run.reply`(값이 `Reply`면 label·order·final, 문자열은 그대로, 그 밖은 JSON) | 제외 |
| `none` | 부르지 않는다(위임·리소스·상호작용 허용 등 노드가 해석) | 제외 |

- Run 시작 시 그래프를 깊은 복사해 고정하고 `graph_version = graph_hash(graph)`. 기본적으로 시작 전 검증(`GraphValidationError`).
- **입구는 명시한 `entry` 엣지뿐**이다. 들어오는 엣지가 없는 노드를 입구로 추론하지 않는다. 실행 가능한 노드로 들어가는
  `entry` 엣지가 없으면 Run을 만들지 않는다(`NoEntryError`, issue code `no_entry`, `validate=False`여도 같다).
- 스케줄 대상 = `executable=true`이고 `entry`·`flow` 엣지가 하나 이상 들어오는 노드. 나머지(호출 대상, 리소스 같은
  `executable=false`, 연결이 덜 된 노드, 입구·답변만 있는 사용자 자리)는 NodeRun도 이벤트도 없다.
  스케줄되지 않는 노드에서 오는 `flow` 엣지는 처음부터 dead다.
- 답변(`exit`)은 소스 노드의 `node.completed`/`node.failed` 직후, 하류 흐름보다 먼저 나간다. 답변 엣지 통과는 실패를 "처리"하지 않는다.
  `entry`·`exit` 엣지는 `edge.traversed`를 내지 않는다(`run.reply`의 `edge_id`로 연결된다).
- join `any`(기본): 처음 통과한 엣지에서 바로 실행(입력은 도착한 것만, 이후 도착은 무시). `all`: 열린 엣지가 없고 하나 이상 통과하면 실행.
  들어오는 엣지가 모두 dead면 `skipped`로 확정하고 하류로 전파(dead-path elimination). 끝까지 도달하지 못한 노드도 `skipped`.
- 실패 노드는 나가는 엣지 중 하나라도 통과하면 "처리됨". 처리되지 않은 실패가 있으면 Run `failed`(`node_failed`), 아니면 `completed`.
- 동시 실행 한도 `max_concurrency`는 런타임 전체(모든 Run 합산) 기준. 상호작용을 기다리는 노드는 슬롯을 반납한다.
- 취소: `CancelToken`이 실행 중 노드에 전파(`on_cancel` 콜백) → `cancel_grace`초 뒤 남은 태스크 asyncio 취소 → 실행 중·대기열 노드 `cancelled`, 미도달 노드 `skipped`, Run `cancelled`.
- 모든 기록은 Run별 한 줄로 직렬화되어 워커 스레드에서 실행되고, 연속 이벤트는 `append_many`로 묶어 **저장한 뒤 발행**한다.

## 반복 — 사이클 연결 (design §5R.4)

엔진은 연결 이름을 모르고 연결 종류 디스크립터 `cycle`(사이클 연결)만 본다. 검증은 `validate_graph(cycle_edge=descriptor_cycle_edge)`:
흐름 사이클마다 사이클 연결이 하나 이상 있어야 한다(없으면 `cycle`).

- **반복 영역**(`agent_console_graph.loop_regions`): 사이클 연결 `e(s → t)`의 `t`에서 `s`로 가는 흐름 경로 위 노드(사이클 연결은 모두 빼고 계산).
- `s`가 끝나고 `e.activates`가 통과하면: 지금까지 `e`가 영역을 연 횟수 `k` < 한도 `m`이면 영역을 다시 연다.
  영역 노드는 **새 NodeRun**(`iteration` = 직전 + 1)으로 pending, 영역 안 흐름 연결은 open, `t`에는 `e`의 값(`ctx.incoming`에 `edge_id = e`).
  이벤트 `loop.iteration{edge_id, iteration(= t의 새 회차), nodes}`. `k ≥ m`이면 `e`는 dead, `loop.exhausted{edge_id, iteration = k, max_iterations = m}`.
- 한도 `m` = 엣지 config `max_iterations` → `start(flow_settings=)`(없으면 생성자 `flow_settings`)의 `max_iterations` → 디스크립터 `cycle.max_iterations`
  (`effective_max_iterations`). 정수가 아니거나 1 미만이면 다시 열지 않는다(저장 전 검증이 막는다).
- 영역 안 다른 노드가 아직 실행 중·대기열·live wait이면 다시 열기를 그 노드들이 끝날 때까지 미룬다(회차 경계 = 영역이 조용할 때).
- **영역 밖으로 나가는 연결**은 그 회차에 지나가면 바로 하류를 활성화한다. 하류는 한 번만 실행된다(이미 끝났으면 다시 열지 않는다).
  지나가지 않은 경우 영역이 다시 열릴 수 있는 동안은 dead로 확정하지 않고 기다린다(예: 반려 두 번 뒤 승인 — 승인 쪽 하류가 미리 skipped되지 않음).
  반복이 끝나면(사이클 연결이 지나가지 않거나 한도 도달, 출발 노드 skipped) 그때 dead.
- **중첩 반복**: 바깥 영역이 다시 열리면 그 안의 사이클 연결 횟수는 0으로 돌아간다.
- **안전 한도**: Run 하나의 노드 실행(활성화) 수가 `flow.max_node_runs`(기본 200, None = 제한 없음)를 넘으면 Run `failed`
  (`ErrorInfo.code = flow.max_node_runs_exceeded`, `details.limit`). 실행 중 노드는 같은 오류로 `cancelled`.
- 이전 회차의 처리되지 않은 실패는 남아 Run을 `failed`로 만든다. `totals`는 모든 회차 사용량의 합.
- 재시작 복구·이어 가기: NodeRun 키 (run_id, node_id, attempt, iteration, call)라 끝나지 않은 회차만 `cancelled`(payload `iteration`).
  `resume_options`는 노드마다 마지막 회차를 본다. 이어 간 Run의 반복 횟수는 0부터 다시 센다.

```python
>>> import asyncio
>>> from agent_console_contracts import FlowSettings
>>> from agent_console_runtime.testing import BUILDERS as b, make_harness
>>> h = make_harness()  # 테스트 연결 `t.loop`은 디스크립터 cycle(max_iterations 3)을 가진다
>>> g = b.graph(
...     [b.node("draft"), b.node("check", outputs={"out": "again"})],
...     [b.edge("draft", "check"), b.edge("check", "draft", kind="t.loop")],
...     entries=["draft"],
... )
>>> run = asyncio.run(h.make().run(g, flow_settings=FlowSettings(max_iterations=1)))
>>> sorted((nr.node_id, nr.iteration) for nr in h.recorder.runs.list_node_runs(run.id))
[('check', 0), ('check', 1), ('draft', 0), ('draft', 1)]

```

## 호출 NodeRun — `ctx.invoke_node` (design §5R.6)

위임 방식(X12, 예: 독립 위임 `host`)이 `invocation` 연결의 대상을 **자기 NodeRun**으로 실행할 때 쓴다.
대상 노드 타입의 `execute`가 스케줄되는 노드와 같은 길(상호작용·이벤트·기록·취소)로 돈다. 엔진은 연결·방식 이름을 모른다.

- 허용: `by_edge`가 부르는 노드에서 `node_id`로 가는 연결이고 디스크립터에 `invocation`이 있으며 대상이 실행 가능할 때만
  (아니면 `ValueError`). 엔진 밖에서 만든 맥락이면 `RuntimeError`.
- 기록: 대상 NodeRun `iteration` = 부른 노드의 회차, `call` = 이 Run에서 그 노드를 부른 순번(0부터, 스케줄되기도 하는 노드면 1부터),
  `invoked_by` = 부른 노드 경로. `node.*` 이벤트 `node_path = [...부른 노드 경로, 대상]`, payload `call`. 대상의 답변(`exit`) 연결은
  엔진이 평가해 `run.reply`를 낸다. 대상 `ctx.node_path`도 같은 경로라 대상 안 이벤트·상호작용·다시 부르기(깊이 2)가 그 아래로 이어진다.
- 결과: `NodeRunView`(`status`·`outputs`·`error`·`call`, 메모리 원본). 대상 실패는 예외가 아니라 결과이고 Run 실패로 세지 않는다(부른 쪽이 판단).
  `usage`는 Run `totals`에 더해진다. 같은 대상의 다음 호출은 직전 호출의 `backend_session_id`를 `ctx.previous_session_id`로 받는다.
- 동시성: 같은 대상은 직렬, 다른 대상은 동시에(런타임 `max_concurrency` 안). 부르는 동안 부른 쪽은 슬롯을 내놓고 끝나면 다시 잡는다
  (`max_concurrency=1`에서도 교착 없음).
- 대기: 대상이 상호작용을 기다리고 부른 쪽에 다른 일이 없으면 Run `waiting`(부른 쪽 NodeRun은 `running` 그대로).
- 한도: 노드 실행 총 한도(`flow.max_node_runs`)에 센다. 깊이(`len(경로) - 1`)가 `max_depth`·`delegation_settings.max_depth`
  (`GraphRuntime(delegation_settings=)`/`start(delegation_settings=)`) 중 작은 값을 넘거나 대상이 이미 경로에 있으면 실행하지 않고
  `failed` 결과(`error.code` = `delegation.depth_exceeded`·`delegation.cycle`) + `log.warning`.
- 취소·끊김: Run 취소 토큰을 따른다. 대상 NodeRun은 `cancelled`(끊김이면 `error.code = interrupted`). 재시작 복구도 끝나지 않은 호출 NodeRun을
  `cancelled`로 바꾸고 이벤트 `node_path = invoked_by + [노드]`, payload `call`. 이어 가기(`resume_options`·`resume_seed`)는 호출 NodeRun을 보지 않는다.

```python
>>> import asyncio
>>> from agent_console_runtime.testing import BUILDERS as b, make_harness
>>> h = make_harness()  # 테스트 연결 `t.invoke`(invocation `t.invoker`) + 위임자 `t.lead`
>>> g = b.graph(
...     [b.node("lead", type="t.lead", calls=["dev", "dev"]), b.node("dev")],
...     [b.edge("lead", "dev", kind="t.invoke", sp="alt", tp="in2")],
...     entries=["lead"],
... )
>>> run = asyncio.run(h.make().run(g))
>>> sorted((nr.node_id, nr.call, nr.invoked_by) for nr in h.recorder.runs.list_node_runs(run.id))
[('dev', 0, ['lead']), ('dev', 1, ['lead']), ('lead', 0, None)]

```

## 자식 Run — `ctx.run_child` (design §5R.7)

노드(예: 중첩 팀 노드)가 다른 그래프를 **자식 Run**으로 실행하고 결과를 기다린다. 엔진은 노드·팀 이름을 모른다.

- 자식 Run: `parent_run_id` = 부모, `parent_node_id` = 부른 노드, `root_run_id` = 맨 위 Run(손자도 루트 id, 루트 자신은 null),
  `origin` = 부모 값, `conversation_id` = null(대화 턴이 아님). 같은 런타임에 등록되어 `get`·`cancel`·`respond`·`pending`·`shutdown`이
  그대로 다루고, 같은 저장소·이벤트 발행·동시 실행 한도를 쓴다.
- 준비: `GraphRuntime(child_preparer=)`가 있으면 그것이 `ChildRunRequest{graph, input, parent, node_id, node_path, ancestors, services}`를
  받아 `ChildRunPreparation{services, interaction_grants, interaction_settings, flow_settings, delegation_settings, checked}`를 준다
  (None = 부모 Run 값, 허용 상호작용은 없음). 없거나 `checked=False`면 엔진 검증을 한다. 막히면(검증 오류·입구 없음·준비자 거절) 자식 Run을
  만들지 않고 `failed` 결과(`error.code = validation_failed`, `details.issues`).
- 한도: 중첩 깊이(루트 = 0)가 `delegation_settings.max_nesting`(없으면 계약 기본값 3)을 넘으면 `team.nesting_exceeded`, 자식 그래프 id가
  이미 Run 경로에 있으면 `team.recursive` — 둘 다 자식 Run 없이 `failed` 결과 + `log.warning`(`node_path` = 부른 노드).
- 이벤트: 부모 Run에 `run.child_started{child_run_id, node_id, graph_id}`·`run.child_finished{child_run_id, node_id, status = 자식 상태}`.
  자식 답변은 자식 Run의 `run.reply`로만 남고 부모 채팅에 흐르지 않는다(부모 답변은 노드의 답변 연결).
- 결과: `ChildRunResult{run_id, status, replies(답변 payload), totals, error}`. 자식 실패는 예외가 아니라 결과다.
  `totals`는 부모 합계에 자동으로 더하지 않는다 — 노드가 `NodeResult.usage`로 돌려주면 들어간다.
- 대기·슬롯: 기다리는 동안 부른 노드는 슬롯을 내놓는다(`max_concurrency=1`·2단 중첩에서도 교착 없음). 자식이 상호작용만 기다리면
  부모 Run도 `waiting`(부른 노드는 `running` 그대로). 자식 안 상호작용은 `Interaction.root_run_id` = 루트, `conversation_id` = 루트 대화.
- 취소·끊김: 부모 취소·끊김(종료)은 자식에 같은 방식으로 전파되고, 부모는 자식이 끝난 뒤(`run.child_finished` 뒤) 끝난다. 노드가 기다리지 않고
  남긴 자식도 부모가 끝날 때 멈춘다. 재시작 복구(`recover_unfinished_runs`)는 자식 Run도 일반 Run처럼 `interrupted`로 정리한다.
- 실행 폴더: 자식 Run 노드의 `ctx.run.id`는 자식 Run id다 — `<Run 파일 루트>/<자식 Run>/<노드>`(ac-nodes-core `run_folder` 규칙 그대로).

```python
>>> import asyncio
>>> from agent_console_runtime.testing import BUILDERS as b, make_harness
>>> h = make_harness()  # 테스트 노드 `t.nest`: config `graph`를 ctx.run_child로 실행
>>> child = b.graph([b.node("A", outputs={"out": "자식 답"})], [b.reply("A")], "child", entries=["A"])
>>> parent = b.graph(
...     [b.node("N", type="t.nest", graph=child.model_dump(mode="json"))],
...     [b.reply("N")],
...     "parent",
...     entries=["N"],
... )
>>> run = asyncio.run(h.make().run(parent))
>>> [(r.graph_id, r.parent_node_id, r.root_run_id == run.id) for r in h.recorder.runs.list() if r.parent_run_id]
[('child', 'N', True)]
>>> [r.text for r in h.probe.children[0].replies]
['자식 답']

```

## 실행 중 상호작용 (live wait, design §R14.5)

```python
outcome = await ctx.request_input(
    InteractionRequest(kind="<등록된 종류 id>", title="…", payload={...})
)
if outcome.status == "answered":
    ...  # expired·cancelled도 예외가 아니라 결과(response = expire_response)

await runtime.respond(run_id, interaction_id, {"answer": "…"})  # 앱(서버·CLI)
runtime.pending(run_id=None)  # 대기 목록(비밀 가린 저장본)
```

- `NodeContext`는 `InteractivePort`를 만족한다. 백엔드는 `isinstance(sink, InteractivePort)`일 때만 요청을 연다.
- 엔진은 종류 이름을 모른다. 종류는 `registries.interaction_kinds`에서 찾고(없으면 `UnknownExtensionError`),
  응답 스키마(요청 값 > 디스크립터 기본)로 응답을 검증한다(`ResponseValidationError.issues`, ac-graph 검사기).
  grant(`start(interaction_grants=)`, `ctx.interaction_grant`)는 시간 제한 기본값으로만 쓰고 종류를 강제하지 않는다.
- 상태: 첫 요청 → NodeRun `waiting`(`node.waiting`, `wait.reason` = 종류, `wait.data.interaction_ids`), 동시 실행 슬롯 반납.
  열린 요청이 모두 닫히면 슬롯 재획득 → `node.resumed{waited_ms}` → 요청자에게 결과. 한 노드가 요청을 여러 개 열 수 있다.
  실행 중·대기열 노드가 없고 대기 노드가 있으면 Run `waiting`(`run.waiting`), 다시 움직이면 `run.resumed`.
- 이벤트: `interaction.requested{interaction}` · `interaction.answered{interaction_id, kind, answered_by, response_preview}` ·
  `interaction.closed{interaction_id, kind, status, reason}`. `interaction.*`는 엔진 예약 접두다.
- 응답 경합: 메모리에서 먼저 닫기 시작한 하나 + 저장소 조건부 갱신. 진 쪽은 `InteractionClosedError(interaction)`.
  끝난 Run·다른 프로세스의 요청은 저장소를 보고 `InteractionClosedError`/`UnknownInteractionError`.
- 시간 제한: 요청 `timeout_seconds`·`on_timeout` > grant > `interaction_settings`(`start(...)` > 생성자) > 무기한·`expire`.
  `expire` → `expired(timeout)`, `cancel_run` → `cancelled(timeout)` 후 Run 취소(사유 `interaction_timeout`).
  타이머는 주입된 `clock`·`sleep`을 쓴다(`testing.ManualClock`).
- 닫힘: Run 취소 → `cancelled(cancelled)`(노드가 결과를 받고 정리할 수 있게 유예 전에 닫는다),
  노드가 대기 중에 끝남 → `cancelled(node_finished)`, 재시작 → `recover_unfinished_runs`가 `expired(interrupted)`.
- 비밀: 저장·이벤트·`respond`/`pending`의 반환값은 가린 사본, 요청자(`InteractionOutcome.response`)는 원문.

## 끊긴 실행 이어 가기 (design §2R.10)

- `GraphRuntime.start(graph, input, seed={노드: 입력}, resumed_from=원래_run_id, origin="resume")`:
  입구 주입 없이 seed 노드를 그 입력으로 시작한다. seed 노드의 상류(흐름 엣지를 거슬러 닿는 노드)는
  실행하지 않고 `node.skipped`(payload `reason = "resumed"`, `SkipReasons.RESUMED`)로 남기며, 하류는 평소처럼
  이어진다. seed 노드가 스케줄 대상이 아니면 `GraphValidationError`(`seed_not_scheduled`). 엔진은 노드
  이름을 모르고, 다시 실행해도 되는지(디스크립터 `rerunnable`)는 호출자가 검사한다.
- 순수 함수: `resume_options(run, node_runs, events, graph=, node_types=)`(끊긴 노드 + 끊기기 직전 상태 +
  `rerunnable`), `resume_issues(options, node_ids)`, `resume_seed(node_runs, node_ids)`, `interrupted_status`.
- `ResumeService(runs, events, graph_of=, node_types=, starter=)`: `options(run_id)`, `await resume(run_id,
  node_ids)`. 끊긴 Run이 아님·자식 Run(`root_run_id`가 있음 — 루트를 이어 가면 부른 노드가 자식을 새로
  만든다, design §5R.11)·이미 이어 감(`runs.list(resumed_from=)`)·당시 팀 구성 없음은
  `RunNotResumableError`(409 `run_not_resumable`), 고를 수 없는 노드는 `GraphValidationError`(노드별 이슈).
  새 Run을 어떻게 시작할지(대화 턴인지 등)는 주입한 `starter`가 정한다.
- 한계: 저장된 입력은 `NodeRun.inputs`(포트마다 첫 값)라 엣지별 값(`ctx.incoming`)은 비어 있다.

## 비밀 값 처리

- 노드는 `ctx.secrets.resolve(...)`로 비밀을 해석한다. 해석기는 해석한 값을 기억한다.
- **저장되는 모든 기록**(Run, NodeRun의 inputs·outputs·error, 상호작용, RunEvent)은 저장 경로 한 곳
  (`RunJournal.save`/`event`)에서 해석한 값을 `[REDACTED]`로 가린 사본으로 저장·발행된다.
  `wait()`가 돌려주는 최종 Run도 가린 사본이다.
- `SecretResolver(providers, *, min_redact_chars=4, extra_redact=None)`: `extra_redact(text) -> text`를 주면 해석한
  비밀을 가린 뒤 모든 문자열에 한 번 더 건다(해석하지 않은 평문 토큰 가림, 2R.4). 엔진은 의심 규칙을 모른다 —
  서버가 `ac-secret-rules`의 `redact_suspected`를 넣고, 워크스페이스 설정 `secrets.redact_suspected_in_logs`로 끈다.
- `min_redact_chars`(기본 4)보다 짧은 비밀 값은 정상 텍스트를 훼손하므로 가리지 않는다. 대신 해석 시 그 **이름**으로
  경고 로그를 한 번 남긴다(값은 남기지 않는다).
- `Run.input`도 가린 사본으로 저장된다. 입력에 비밀과 같은 문자열이 있으면 저장본(과 `wait()`의 Run)은 원문과 다르다.
- 하류 노드로 넘어가는 값(엣지 전달 값)은 엔진 메모리 안에만 있으므로 가리지 않는다(노드가 원래 값을 써야 한다).
- 한계: 가리기는 **이 해석기로 해석한 값**에만 적용된다. 해석 전(또는 다른 경로로 얻은) 비밀, 해석 전에 이미 기록된 값,
  변형된 값(인코딩·일부 잘림)은 가릴 수 없다. 백엔드는 공급자 원시 메시지(`raw`)에서 자체 마스킹도 해야 한다.
- **해석 전 입력은 가려지지 않는다**: 사용자가 Run 입력(콘솔 입력·`POST /runs`의 `input`)에 비밀 값을 직접 쓰면,
  그 값을 해석기가 아직 `secret://`로 해석한 적이 없으면 모르는 값이므로 그대로 저장·표시된다.
  (`GraphRuntime(secrets=…)`로 해석기를 공유하고 같은 값이 이미 해석된 뒤라면 가려진다.)
- **`secret://`는 문자열 전체가 참조일 때만 해석된다**: `"secret://API_KEY"`는 값으로 바뀌지만
  `"Bearer secret://API_KEY"`처럼 다른 글자와 섞인 문자열은 해석하지 않고 그대로 둔다.

## 저장소 실패 시 동작

- 기록이 실패하면 그 Run의 이후 기록은 버려지고(저장되지 않은 이벤트는 발행하지도 않는다) 실행이 끝난다.
- `handle.wait()`/`runtime.run()`은 `RecorderError`(원인은 `__cause__`)를 던진다. `start()` 중 실패하면 `start()`가 던진다.
- 저장소의 Run은 마지막으로 저장된 상태(보통 `running`)로 남는다. 다음 서버 시작 때 `recover_unfinished_runs`가 `interrupted`로 정리한다.
- 아무도 `wait()`하지 않아도 엔진이 태스크 예외를 회수해 로그로 남긴다("Task exception was never retrieved" 없음).

## 프로세스 그룹 유틸

`process_group_kwargs()`로 시작한 하위 프로세스를 `terminate_process_group(popen)` / `await aterminate_process_group(proc)`로
그룹째 종료한다(POSIX: SIGTERM → 유예 → SIGKILL, Windows: CTRL_BREAK → 유예 → `taskkill /T /F`). agent_bench `terminate` 이식.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-runtime`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-runtime/tests
```

테스트는 `agent_console_runtime.testing`의 테스트 전용 `t.*` 노드·엣지 타입만 등록해 엔진이 특정 타입을 모름을 확인한다.
입구·답변·위임 타입(`t.user`·`t.res`·`t.lead`, `t.entry`·`t.exit`·`t.tie`·`t.call`, 위임 방식 `t.inline`)은
`register_scheduling_types(registries)`로 아무 레지스트리 묶음(실제 플러그인으로 조립한 스택 포함)에 넣을 수 있고,
호출 NodeRun 타입(연결 `t.invoke`, 위임 방식 `t.invoker` — `ctx.invoke_node`로 대상 실행, 위임자 config `calls`·`parallel`·`max_depth`)은
`register_invocation_types(registries)`로, 자식 Run 노드 `t.nest`(config `graph`·`version`·`input_key`)는
`register_child_types(registries)`로 넣는다(`make_registries`는 모두 넣는다).
`graph(..., entries=[...])`·`with_entries(graph, entry(dst, key=...))`로 입구를 명시한 테스트 그래프를 만든다.
`agent_console_runtime.testing`(메모리 recorder, `StepClock`, `SequentialIds`)은 플러그인 테스트에서도 쓸 수 있다.
백엔드 어댑터(X3) 테스트용 sink는 `agent_console_runtime.testing_sink` 한 곳에 있다: `ValidatingSink`(계약 검증·하위 경로 검사),
`ListeningSink`(+ `SubagentResultListener` 기록), `InteractiveSink`(+ `InteractivePort`, 응답 함수). fake·claude-sdk의 `testing`은 이것을 다시 내보낸다.

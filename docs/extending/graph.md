# 그래프·실행

팀 구성(그래프)을 이루는 부품과 실행 중의 판단을 바꾸는 지점이다. 노드 종류, 연결 종류, 위임 방식, 조건 연산자,
실행 중 사용자에게 받는 요청(상호작용 종류)이 모두 플러그인이다. 실행 엔진은 이 이름들을 모르고 레지스트리에서
찾으므로, 기본 구현도 같은 그룹에 등록된 첫 번째 구현일 뿐이다.

공통 규칙(entry point 이름, 로드 시점, 켜고 끄기)은 [플러그인 공통](plugins.md)에 있다. 이 페이지는 지점마다 다른
것만 적는다.

| 하고 싶은 일 | 지점 |
| --- | --- |
| 팀 구성 화면에 새 상자(일 하나)를 둔다 | [node-type](#node-type) |
| 두 상자 사이를 새 방식으로 잇는다 | [edge-type](#edge-type) |
| 위임자가 대상에게 일을 맡기는 방식을 바꾼다 | [delegation-strategy](#delegation-strategy) |
| 조건 연결·조건 칸에 새 비교를 더한다 | [condition-operator](#condition-operator) |
| 실행 중 사용자에게 새 모양의 요청(승인·서명 등)을 연다 | [interaction-kind](#interaction-kind) |

## condition-operator

**언제 쓰나**: 조건 연결(`when`)이나 조건을 읽는 다른 확장에서 기본 연산자(같음·포함·크기 비교·정규식 등)로
표현할 수 없는 판단이 필요할 때. 의존이 계약 패키지 하나뿐이라 가장 작은 플러그인이다. 처음이면
[시작하기](getting-started.md)가 이 지점으로 한 바퀴를 돈다.

**최소 모양**: `descriptor`(`ConditionOperatorDescriptor` — `id`·`title`, 선택 `value_schema`·`applies_to`)와
`evaluate(actual, expected) -> bool` 하나.

**규칙**

- `evaluate`는 순수 함수다. 파일·네트워크·시계를 읽지 않는다. 같은 입력이면 같은 답이다.
- 타입이 맞지 않거나 값이 없으면 예외 대신 `False`를 돌려준다. 예외를 던져도 실행은 멈추지 않지만 그 조건 항목이
  거짓(근거 `error`)이 되어 원인을 찾기 어렵다.
- 기대 값의 모양은 `value_schema`(JSON Schema)로 알린다. 저장 전 검사가 이 스키마로 값을 확인하고(틀리면
  `condition.invalid_value` 오류), 화면은 이 스키마로 입력 칸을 그린다. 스키마로 못 하는 값 검사는 선택 메서드
  `check_value(value)`로 더한다. `applies_to`는 화면 안내일 뿐 검사하지 않는다.

**흔한 실수**: id에 접두사를 붙이지 않아 기본 연산자 이름(`eq`·`in` 등)과 겹친다. 기본 구현을 덮어쓸 수는 없고
내 연산자가 `failed`로 빠진다.

**지운 뒤 남는 데이터**: 그 연산자를 쓰는 조건은 그대로 남는다. 저장 전 검사가 `condition.unknown_operator`
**경고**로 알리고, 실행 때 그 항목만 거짓(근거 `unknown_operator`)이며 경고 이벤트가 하나 난다. 팀 구성 실행은
막히지 않는다.

<!-- extdocs:facts condition-operator -->
- 등록: entry point 그룹 `agent_console.condition_operators`(상수 `agent_console_conditions:CONDITION_OPERATORS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_conditions:ConditionOperator` — 조건 연산자 하나. 등록 key = `descriptor.id`.
- 기본 구현: `any_item (agent-console-conditions)`, `contains (agent-console-conditions)`, `eq (agent-console-conditions)`, `exists (agent-console-conditions)`, `gt (agent-console-conditions)`, `gte (agent-console-conditions)`, `in (agent-console-conditions)`, `lt (agent-console-conditions)`, `lte (agent-console-conditions)`, `matches (agent-console-conditions)`, `ne (agent-console-conditions)`
- 예제:
  - package: [examples/extensions/agent-console-example-condition](../../examples/extensions/agent-console-example-condition/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## delegation-strategy

**언제 쓰나**: 위임 연결로 이어진 대상에게 일을 맡기는 방법을 바꾸고 싶을 때. 기본 구현은 백엔드의 하위 에이전트
기능에 맡기는 방식(`sdk-subagents`)과 대상마다 별도 실행으로 부르는 방식(`host`)이다. 차례로 맡기기, 투표,
경매처럼 맡기는 순서·합치는 방법이 다르면 새 방식이다.

**최소 모양**: `descriptor`(`DelegationStrategyDescriptor`), `validate(plan) -> list[Issue]`,
`async run(plan, ctx) -> AgentResult`. `plan`(`DelegationPlan`)은 위임자 요청과 대상 목록이다. 대상을 실제로
부를 때는 `ctx.invoke_node`를 쓴다(대상마다 자기 실행 기록이 생긴다).

**규칙**

- 서술자 값이 팀 구성 검사를 정한다. `member_fields`(대상 노드에서 읽는 설정 칸), `max_depth`(위임 깊이 한도),
  `composable`(같은 위임자에서 다른 방식과 함께 쓸 수 있나), `requires_backend_capability`(위임자 백엔드가 갖춰야
  할 능력). `composable = false`인 방식을 다른 방식과 섞으면 `team.mixed_strategies` 오류, 위임자 백엔드에 필요한
  능력이 없으면 `team.backend_capability_missing` 오류다.
- 섞어 쓸 수 있게 하려면 선택 프로토콜 `ComposableDelegation`을 함께 구현한다.
- 대상 하나가 실패했을 때 위임자를 실패로 볼지는 방식이 정한다. 실패 코드는 자기 접두사로 쓴다.

**흔한 실수**: `run` 안에서 백엔드를 직접 만들어 부른다. 대상 실행은 엔진(`ctx.invoke_node`)을 거쳐야 실행
기록·취소·되묻기가 이어진다.

**지운 뒤 남는 데이터**: 그 방식을 고른 위임 연결은 남는다. 저장 전 검사가 `team.unknown_strategy` **경고**로
알리고, 실행하면 위임자 노드가 `agent.unknown_strategy`로 실패한다.

<!-- extdocs:facts delegation-strategy -->
- 등록: entry point 그룹 `agent_console.delegation_strategies`(상수 `agent_console_runtime:DELEGATION_STRATEGIES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_runtime:DelegationStrategy` — 위임 방식. 구현은 플러그인이 `agent_console.delegation_strategies`로 등록한다.
  - `agent_console_runtime:ComposableDelegation` — 선택 프로토콜: 다른 방식과 한 위임자에서 합쳐 실행할 수 있는 위임 방식.
  - `agent_console_runtime:DelegationPlan` — 위임 실행 계획: 위임자 요청 + 대상 목록.
- 기본 구현: `host (agent-console-delegation-host)`, `sdk-subagents (agent-console-nodes-core)`
- 예제:
  - package: [examples/extensions/agent-console-example-delegation](../../examples/extensions/agent-console-example-delegation/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## edge-type

**언제 쓰나**: 두 노드 사이의 관계가 기본 연결 종류(흐름·데이터·조건·반복·위임·답변 등)와 다를 때. 값을 바꿔
넘기는 흐름, 특정 상호작용을 허용하는 연결, 실패를 받아 처리하는 연결이 예다.

**최소 모양**: `descriptor`(`EdgeTypeDescriptor`)와 `activates(source, edge)` 하나. 위 노드 실행이 끝나면 엔진이
부르고, 돌려준 값으로 아래 노드를 깨울지(`Activation`), 그 경로를 막을지(`Blocked`), 아무것도 하지 않을지(`None`)를
정한다.

**규칙**

- `scheduling`이 엔진의 동작을 정한다. `flow`는 위 노드가 끝나면, `entry`는 실행 시작 때(실행 입력을 받아 입구
  노드로), `exit`는 위 노드가 끝나면(통과한 값이 답변이 된다) `activates`를 부른다. `none`은 부르지 않는다(위임·
  리소스·상호작용 허용처럼 노드가 해석하는 연결). 사이클 검사는 `flow` 연결만 센다.
- `connects`는 이을 수 있는 노드 역할 쌍이다. 맞지 않는 연결은 팀 구성 검사가 `team.connects_mismatch` 오류로
  막는다. 역할 이름은 노드 종류 서술자의 `role` 문자열이다.
- 상호작용을 허용하는 연결이면 `interaction.kinds`에 상호작용 종류 id를 적는다. 이 연결이 나가는 노드만 그 요청을
  열 수 있다.
- 설정의 의미 검사(스키마로 못 하는 것)는 선택 프로토콜 `EdgeValidator`로 더한다.

**흔한 실수**: `activates`에서 값을 바꾸며 외부를 호출한다. 이 함수는 동기·결정적이어야 한다. 시간이 걸리는 일은
노드에서 한다.

**지운 뒤 남는 데이터**: 그 연결을 쓰는 팀 구성은 남는다. 검사가 `unknown_edge_type` **오류**로 알리고, 그 팀
구성은 실행 전 검사에서 막힌다. 다른 팀 구성은 그대로 실행된다.

<!-- extdocs:facts edge-type -->
- 등록: entry point 그룹 `agent_console.edge_types`(상수 `agent_console_runtime:EDGE_TYPES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_runtime:EdgeType` — 엣지 타입. 엔진은 디스크립터 `scheduling`에 따라 `activates`를 부른다.
  - `agent_console_runtime:EdgeValidator` — 엣지 타입의 선택 능력: 엣지 config의 의미 검증(스키마 검사 뒤, 저장 전 검사).
- 기본 구현: `ask_user (agent-console-nodes-core)`, `data (agent-console-nodes-core)`, `delegate (agent-console-nodes-core)`, `handoff (agent-console-nodes-core)`, `loop (agent-console-nodes-core)`, `message (agent-console-nodes-core)`, `on_error (agent-console-nodes-core)`, `reply (agent-console-nodes-core)`, `subagent (agent-console-nodes-core)`, `uses (agent-console-nodes-core)`, `when (agent-console-nodes-core)`
- 예제:
  - package: [examples/extensions/agent-console-example-edges](../../examples/extensions/agent-console-example-edges/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## interaction-kind

**언제 쓰나**: 실행 중에 사용자에게 받아야 하는 것이 기본 종류(질문·검토·도구 사용 허락)와 모양이 다를 때.
서명, 여러 항목 중 고르기, 수치 입력처럼 요청과 응답의 모양이 정해진 대화다.

**최소 모양**: 서술자(`InteractionKindDescriptor`)만 있으면 된다. `request_schema`·`response_schema`(JSON
Schema)와 화면 힌트(`ui_hints`). entry point가 서술자 객체를 가리키면 서버가 `StaticInteractionKind`로 감싼다.

**규칙**

- 응답은 서버와 엔진이 `response_schema`로 검증한다. 틀리면 422 `validation_failed`다.
- 화면은 웹이 아는 renderer 이름이면 그 화면을, 모르는 이름이면 응답 스키마로 만든 폼을 보인다. 그래서 웹 코드
  없이도 동작한다. 전용 화면이 필요하면 [웹](web.md).
- 요청을 열 수 있는 노드는 그 종류를 허용하는 연결([edge-type](#edge-type)의 `interaction.kinds`)이 나가는 노드뿐이다.
  허용 연결이 없으면 요청은 열리지 않고 백엔드에는 `unavailable`로 돌아간다.

**흔한 실수**: 종류만 만들고 허용 연결을 만들지 않는다. 종류는 목록에 보이지만 어떤 에이전트도 요청을 열 수 없다.
[예제](../../examples/extensions/agent-console-example-interactions/README.md)는 종류와 허용 연결을 한 패키지에
함께 둔다.

**지운 뒤 남는 데이터**: 사용자 노드의 검토 설정이 그 종류를 고르고 있으면 저장 전 검사가 `review.unknown_kind`
**오류**로 알린다. 허용 연결도 함께 지웠다면 그 연결은 `unknown_edge_type` 오류다. 백엔드가 그 종류를 요청하면
열리지 않는다.

<!-- extdocs:facts interaction-kind -->
- 등록: entry point 그룹 `agent_console.interaction_kinds`(상수 `agent_console_runtime:INTERACTION_KINDS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_runtime:InteractionKind` — 상호작용 종류. 엔진·서버·웹은 `descriptor`(요청·응답 스키마, 화면 힌트)만 본다.
  - `agent_console_runtime:StaticInteractionKind` — 디스크립터만으로 된 종류(entry point가 디스크립터 객체를 가리킬 때 감싼다).
- 기본 구현: `question (agent-console-nodes-core)`, `review (agent-console-nodes-core)`, `tool_permission (agent-console-nodes-core)`
- 예제:
  - package: [examples/extensions/agent-console-example-interactions](../../examples/extensions/agent-console-example-interactions/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## node-type

**언제 쓰나**: 팀 구성에 에이전트·사용자·리소스·하위 팀 말고 다른 일을 하는 상자가 필요할 때. 텍스트 변환,
외부 시스템 호출, 사람이 할 일 대기처럼 입력 포트에서 값을 받아 출력 포트로 내는 일이다.

**최소 모양**: `descriptor`(`NodeTypeDescriptor` — `id`·`title`·`config_schema`·포트), `resolve_ports(config)`,
`validate(config, ctx)`, `async execute(ctx, inputs) -> NodeResult`.

**규칙**

- `execute`는 전역·환경변수·파일 시스템 대신 `NodeContext`만 쓴다. 이벤트를 내고, 취소를 확인하고, 다른 노드를
  부르는 것도 모두 맥락을 거친다. 그래야 가짜 맥락으로 시험할 수 있다.
- 포트가 설정에 따라 바뀌면 서술자에 `dynamic_ports`를 켜고 `resolve_ports`에서 계산한다. 아니면
  `static_ports`로 충분하다.
- 서술자 `role`은 연결 종류의 `connects`가 맞추는 역할 이름이다. 새 역할 이름을 쓰면 기존 연결 종류로는 이을 수
  없으므로 연결 종류도 함께 만든다.
- 동작을 바꾼 새 버전은 `version`을 올려 같은 id로 함께 둘 수 있다. 팀 구성의 노드가 `type_version`을 정하지
  않으면 가장 높은 버전을 쓴다.
- 설정 필드에는 `title`·`description`·`x-ui`를 단다([설정 스키마](plugins.md#설정-스키마)).

**흔한 실수**: 실패를 예외로 던진다. 예상한 실패는 `NodeResult`의 오류(자기 접두사 코드)로 돌려준다. 예외는
엔진이 일반 실패로 바꾸므로 원인이 흐려진다.

**지운 뒤 남는 데이터**: 그 종류의 노드가 있는 팀 구성은 남는다. 검사가 `unknown_node_type` **오류**로 알리고,
그 팀 구성은 실행 전 검사에서 막힌다.

<!-- extdocs:facts node-type -->
- 등록: entry point 그룹 `agent_console.node_types`(상수 `agent_console_runtime:NODE_TYPES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_runtime:NodeType` — 노드 타입. 엔진은 이 인터페이스만 알고 구체 타입은 레지스트리에서 찾는다.
  - `agent_console_runtime:NodeContext` — 노드 1회 실행 맥락. 노드는 전역·환경변수·파일 시스템 대신 이것만 쓴다.
  - `agent_console_runtime:NodeResult` — 노드 1회 실행 결과.
- 기본 구현: `agent (agent-console-nodes-core)`, `resource (agent-console-nodes-core)`, `team (agent-console-nodes-core)`, `user (agent-console-nodes-core)`, `wiki-update (agent-console-link-wiki-runs)`
- 예제:
  - package: [examples/extensions/agent-console-example-nodes](../../examples/extensions/agent-console-example-nodes/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

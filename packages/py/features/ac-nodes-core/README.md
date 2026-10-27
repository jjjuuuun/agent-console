# agent-console-nodes-core

기본 노드 타입(`agent`, `user`, `resource`), 연결 종류(`subagent`, `handoff`(+이전 이름 `data`), `uses`,
`message`, `reply`), 위임 방식 `sdk-subagents`(X12) 플러그인. 엔진(`agent-console-runtime`)과
팀 구성 의미(`agent-console-teams`)는 이 이름들을 모른다. 이 패키지가 entry point로 등록할 뿐이고
판단은 디스크립터 속성(`role`·`executable`·`binds`·`scheduling`·`invocation`·`connects`)으로 한다.

## 설치

```bash
uv sync --all-packages                        # 워크스페이스 안
uv pip install ./packages/py/features/ac-nodes-core    # 단독
```

의존: `agent-console-contracts`, `-registry`, `-runtime`, `-resources`, `-teams`, `pydantic`.
저장소·라우팅·백엔드 패키지는 모른다. 테스트만 `agent-console-backend-fake-agent`·`-resources-core`를 쓴다.

## 등록 (entry point, 이름 = 레지스트리 key = 디스크립터 id)

| 그룹 | 이름 | 객체 |
| --- | --- | --- |
| `agent_console.node_types` | `agent`, `user`, `resource` | `agent:AgentNode`, `user:UserNode`, `places:ResourceNode` |
| `agent_console.node_types` | `team` | `team:TeamNode`(중첩 팀, design §5R.7) |
| `agent_console.edge_types` | `subagent`, `delegate`, `handoff`, `data`, `uses`, `message`, `reply`, `ask_user` | `edges:*Edge` |
| `agent_console.edge_types` | `loop` | `loops:LoopEdge` |
| `agent_console.edge_types` | `when`, `on_error` | `conditional:WhenEdge`, `conditional:OnErrorEdge` |
| `agent_console.interaction_kinds` | `question`, `tool_permission`, `review` | `interactions:QUESTION` 등(디스크립터 객체) |
| `agent_console.delegation_strategies` | `sdk-subagents` | `delegation:SdkSubagentsStrategy` |

## 노드 타입

| id | role | 포트 | config | 동작 |
| --- | --- | --- | --- | --- |
| `agent` | agent, `binds{agent, agent_ref}` | 입력 `in`·`delegated`·`resources`, 출력 `out`·`delegates` | `agent_ref`, `role?`, `delegate_when?`, `settings?`(노드 층 `AgentSettings`), `delegation?`(위임 방식 id → 그 방식 config, 예 `{host: {tool_name: hand_off}}`) | 아래 "agent 실행". `actor_of(config)` = `agent_ref` |
| `user` | user | 입력 `hears`·`asks`·`review`, 출력 `says` + 결정 포트(`review.decisions[].id`, 동적) | `review?{title, message, decisions[{id, label, edit, feedback, ui_hints}], output_template?, kind(기본 review), timeout_seconds?, on_timeout?}` | `executable=true`지만 `entry`·`flow`로 들어오는 연결이 없으면 엔진이 스케줄하지 않는다. 흐름으로 실행되면 아래 "사용자 중간 검토". `review`가 없으면 `user.not_reviewable`. 선언형 배지 `검토`(`review` 설정 + 흐름 입력) |
| `resource` | resource, `binds{resource, resource_ref}` | 출력 `provides` | `resource_ref` | `executable=false`. 연결된 에이전트의 노드 층 첨부(`ac-teams`) |
| `team` | team, `binds{graph, team_ref}`, `ui_hints.shape = stacked` | 입력 `in`, 출력 `out` | `team_ref`, `version?`(정의 저장소 버전 해시, 생략 = 최신), `input_key?`, `reply?`(답변 label 목록), `reply_separator`(기본 빈 줄), `settings?`(자식 팀 층 덮어쓰기, `GraphSettings`) | 아래 "중첩 팀 실행" |

### 중첩 팀 실행 (`team`, design §5R.7)

1. 서비스 `TEAM_LOOKUP`(`(id, 버전|None) -> Graph|None`)으로 팀 구성을 찾는다. 서비스가 없으면
   `team.lookup_unavailable`(메시지 `TEAM_LOOKUP_UNAVAILABLE_MESSAGE`), 없는 팀 구성·버전은 `team.team_not_found`.
2. `settings`가 있으면 `ac-teams.with_team_settings`로 자식 팀 층을 덮어쓴다(지정한 값만, 틀리면 `team.invalid_settings`).
3. `ctx.run_child(graph, {"text": 값}, services={SESSIONS: …})`. 값 = 입력 `in`(객체이고 `input_key`가 있으면 그 키).
   세션은 부모 `SESSIONS`의 경로 키 `"<이 노드>/<자식 노드>"`만 접두를 떼어 넘긴다(`child_sessions`, 손자도 같은 규칙).
   자식 Run을 다 돌고 대화에 세션을 저장할 때도 같은 키(`session_path_key`)를 쓴다(대화 쪽 몫).
4. 결과: 자식 `completed` → `out` = `pick_replies`로 고른 답변 텍스트를 `reply_separator`로 이은 것(`reply` 목록이면
   그 label들을 목록 순서로, 없으면 `final` 답변 전부를 `order` → 낸 순서로). `waiting`(parked) → 이 노드도 `waiting`
   (`wait.reason = TEAM_CHILD_WAITING`, `data.child_run_id`). 그 밖 → `failed`(자식 오류 그대로 + `details.child_run_id`,
   오류가 없으면 `team.child_failed`). 거절(중첩 한도 `team.nesting_exceeded`·순환 `team.recursive`·검증 `validation_failed`)은
   엔진이 자식 Run 없이 실패 결과로 준다. 사용량 `usage` = 자식 `totals`(부모 합계에 들어감).
5. 자식 Run 안 상호작용(되묻기 등)은 엔진이 부모 Run을 `waiting`으로 만들고 `respond(자식 Run id, …)`로 이어진다.
   자식 Run의 허용 상호작용은 자식 Run 준비자(`GraphRuntime(child_preparer=)`)가 정한다(없으면 없음).

`team` 역할은 흐름(`handoff`·`loop`·`when`·`on_error`)의 양끝, `message`의 도착, `reply`의 출발에 들어 있다(연결 규칙 데이터).
위임 연결(`subagent`·`delegate`)의 대상은 아니다.

### agent 실행
1. `team_plan(ctx.graph, 등록된 디스크립터)` → 2. `node_settings`(공통 → 팀 구성 → 에이전트 → 노드 + 리소스
연결) → 3. 백엔드 = 유효 `backend` → `DEFAULT_BACKEND` → 4. 묶음 = `node_bundle(..., accepted_slots=
capabilities.resource_slots)`, 파일 칸은 `<RUN_FILES_ROOT>/<run>/<node>/`에 쓰고 `{path, root, name}`로 바꿈
(`write_files`: base64 디코드, 폴더 밖·심볼릭 링크 거부, 부모 폴더는 칸마다 검사 후 생성. 이미 `{path, root?}`만
있는 항목은 `path`·`root`가 그 실행 폴더 안일 때만 넘긴다 — 백엔드가 이 경로를 에이전트 접근 폴더(`add_dirs`)로
열기 때문에 다른 플러그인이 임의 경로를 열지 못하게 한다. 첫 경로 칸 `_bundle`은 예약), 파일 칸이 아닌 칸의 항목이
`files: [{name, content, …}]`를 가지면(skill·규칙 파일, 2R.12) `write_item_trees`가
`<RUN_FILES_ROOT>/<run>/<node>/_bundle/<node>/<칸>/<항목 name>/`에 같은 규칙으로 쓰고 항목을
`{…, root, tree_root, files: [{name, path, media_type?}]}`로 바꾼다(칸 이름은 모르고 모양만 본다. 트리 폴더 이름이
노드 id라 백엔드가 이 폴더를 플러그인 폴더로 넘겨도 노드마다 이름이 다르다) → 5. 정의(식별) + 유효 설정, 비밀 참조 해석,
프롬프트 = `assemble_prompt(in 값, prompt_template)`(변수 `{inputs}`·`{message}`·`{node}`). 요청을 만든 뒤 백엔드를 부르기 전에
`agent.context_prepared`(`context_prepared_payload`: 묶음 출처의 리소스 id·종류·바이트 수·sha256과 조각 수 = 프롬프트
입력 수, **본문 없음**, design §5.5R.1 C1)를 낸다, 세션 = `SESSIONS[node]`
(유효 `session`이 `fresh`면 없음, 백엔드가 다르면 없음), `interactions` = `session_grant(plan, node, 위임 방식)`
→ 6. 위임 대상(`invocation` 연결)이 있으면 대상을 위임 방식별로 묶고, 묶음마다 유효 설정·묶음·`describe_member`·
방식 config(`delegation[방식 id]`)로 `DelegationPlan`을 만들어 `validate` → 방식이 하나면
`registries.delegation_strategies.get(id).run(plan, ctx)`, 여럿이면 아래 "혼합 위임", 없으면 `backend.run` →
7. `out` = 응답 텍스트.
묶음·리소스 문제는 `log.warning`(details `code`, 값 없음).

합류: 프롬프트 입력은 엔진이 주는 엣지별 값 `ctx.incoming("in")`으로 만든다(design §4.3·§R3.2-4). 형식은 유효 설정(데이터)이다.

| 설정 | 기본값(계약 `AgentSettings`) | 쓰임 |
| --- | --- | --- |
| `prompt_input_template` | `"{source}: {value}"` | 값이 여러 개일 때(합류) 값 하나의 형식 |
| `prompt_single_input_template` | `"{value}"` | 값이 하나일 때의 형식 |
| `prompt_input_separator` | `"\n\n"` | 값 사이 구분자 |

변수: `source`(보낸 노드 label, 없으면 id), `source_id`, `port`, `edge`, `value`, `index`(1부터). 이렇게 만든 결과가
`prompt_template`의 `{inputs}`다. 코드에서는 `PromptFormat.of(settings)`·`assemble_prompt(items, template, fmt=)`.

## 연결 종류

| id | scheduling | connects(source → target) | 기본 포트 | config |
| --- | --- | --- | --- | --- |
| `subagent` | none, invocation `sdk-subagents` | agent → agent | `delegates` → `delegated` | `strategy?` |
| `handoff` / `data`(숨김) | flow | agent·user → agent·user | `out` → `in` | 없음 |
| `uses` | none | resource → agent | `provides` → `resources` | `mode?`, `config_override?` |
| `message` | entry | user → agent | `says` → `in` | `input_key?`(생략 = `"text"` = `DEFAULT_MESSAGE_KEY`, ac-chat과 같음), `template?`(`{message}` + Run 입력 키) |
| `reply` | exit | agent·user → user | `out` → `hears` | `label?`, `order?`, `final`(기본 true), `stream`(기본 true, 화면용). 선언형 칩 `중간 결과`(`final == false`) |
| `ask_user` | none, interaction `question`·`tool_permission` | agent → user | `out` → `asks` | `kinds?`(좁히기), `timeout_seconds?`, `on_timeout?`(`expire`·`cancel_run`), `label?` |

| `delegate` | none, invocation `host` | agent → agent | `delegates` → `delegated` | `strategy?`, `result?`(`text` 기본 \| `reply`) |

`delegate`: 위 에이전트가 위임 도구로 아래 에이전트를 **자기 세션·백엔드·설정**으로 부른다(design §5R.6). 위임 방식
`host` 구현은 별도 패키지 `agent-console-delegation-host`다(이 패키지는 id 문자열만 디스크립터 데이터로 안다 —
설치하지 않으면 팀 검증이 "등록되지 않은 위임 방식" 경고를 낸다). `result`는 대상이 돌려줄 결과 모양(그 방식이 읽는다).

`message`: Run 입력에 키가 없으면 통과하지 않는다. `reply`: 출발 노드가 성공했을 때만 `Reply(text, label, order, final)`.

### 반복 연결 `loop` (design §5R.4)

| id | scheduling | connects | 기본 포트 | config |
| --- | --- | --- | --- | --- |
| `loop` | flow, `cycle{max_iterations: 3}` | agent·user → agent·user | `out` → `in` | `max_iterations?`(≥1, 비우면 설정 `flow.max_iterations` → 기본 3) |

흐름 사이클을 닫을 수 있는 연결(엔진은 이름이 아니라 디스크립터 `cycle`로 판단). 출발 노드가 성공해 포트에 값을 냈을 때만
지나가고, 엔진이 그 사이 노드를 새 회차로 다시 실행한다. 예: 사용자 검토 노드 결정 포트 `rejected` → 작성자 `in`.
agent 노드의 다음 회차는 직전 회차 세션을 이어 쓰고(설정 `session: fresh`면 새 세션), 이어 쓸 때 프롬프트는 이번 회차에
새로 들어온 값(예: 반려 사유)만 담는다(`Incoming.carried` 값은 뺀다). 새 세션이면 남아 있던 값도 다시 넣는다.

### 조건·실패 연결 `when`·`on_error` (design §5R.5)

| id | scheduling | connects | 기본 포트 | config |
| --- | --- | --- | --- | --- |
| `when` | flow | agent·user → agent·user | `out` → `in` | `conditions?`(`ConditionSpec{all?, any?, negate?}`, 비우면 항상 통과) |
| `on_error` | flow, `handles_failure` | agent·user → agent·user | `out` → `in` | 없음 |

`when`: 출발 노드가 성공해 포트에 값을 냈을 때만 조건을 평가한다(실패 처리는 `on_error`의 몫). 판단 대상은
`condition_subject` = `{output?, structured?, status, iteration, error?}`(`path`는 JSON Pointer, 예 `/output`·
`/structured/verdict`·`/iteration`). 참이면 포트 값을 넘기고 근거를 `edge.traversed.condition`에, 거짓이면
`Blocked(reason="condition_false")`로 `edge.skipped{reason, condition}`을 남긴다. 연산자는 `ac-conditions`
레지스트리(X22)에서 오고(생략하면 설치된 entry point, `WhenEdge(operators=...)`로 주입), 모르는 연산자 항목은
거짓 + `log.warning`(`details.code = condition.unknown_operator`)이다. 저장 전 검사(`EdgeValidator.validate_edge`)는
`condition_issues`를 config 경로 `/conditions/...`로 낸다. 편집 화면용으로 경로 필드에 스키마 `examples`, `ui_schema`
`conditions`에 `ui:widget: condition-list`·`ui:options.path_titles`(경로 → 제목)를 싣는다(데이터).
근거의 실제 값(`actual`)은 가림 함수(`WhenEdge(redact=...)` 또는 `use_redactor`, `ac-conditions.RedactorConsumer`
— 실행 모듈이 엔진 `secrets.redact`를 준다)를 건 **뒤에** 200자에서 자른다. 잘린 비밀 조각은 기록 단계의 가림이
알아보지 못하기 때문이다(5.2R.43).

`on_error`: 출발 노드가 `failed`일 때만 `{error: {code, message}, node_id}`를 넘긴다. 지나가면 엔진은 그 실패를
처리됨으로 보고 Run을 `completed`로 끝낼 수 있다.

## 사용자 중간 검토 (A → 사용자 → B, design §R14.6)

`review` 포트(보통 `handoff`)로 들어온 값을 내용으로 상호작용(`review.kind`, 기본 `review`)을 연다.
payload `{content, decisions, title?, source_node?}`, 응답 스키마는 요청마다 `review_response_schema(결정 id)`
(`decision` enum). 응답한 결정의 포트에만 값을 낸다(나머지는 dead-path로 하류 skipped). `edit`가 허용된 결정은
`edited`가 내용을 대신하고, `feedback`이 허용된 결정만 의견을 쓴다. 값 = `output_template`(변수 `content`(고쳤으면
고친 내용)·`original`(고치기 전)·`edited`·`feedback`·`decision`·`source_node`·`title`) 또는 내용. 만료 = `review.expired`, 취소 = `review.cancelled`로 실패.
결정 id가 고정 출력 포트(`says`)와 겹치면 검증 오류이고 포트가 되지 않는다. 입력 포트(`hears`·`asks`·`review`)와는
이름 공간이 달라 결정 id로 써도 된다.

## 상호작용 종류 (X15, design §R14.3)

| id | 요청 | 응답 | `free_text_path` | `expire_response` | renderer |
| --- | --- | --- | --- | --- | --- |
| `question` | `{questions[{question, header?, options[{label, description?}], multi_select}], text?}` | `{answers{질문: 라벨 \| 라벨[] \| 문자열}, response?}`(둘 중 하나 필수) | `/response` | 없음(어댑터가 거부) | `choices` |
| `tool_permission` | `{tool_name, input_preview?, title?, display_name?, description?, blocked_path?, decision_reason?, tool_use_id?, agent_id?}` | `{decision: allow \| allow_for_run \| deny, message?, updated_input?}` | 없음 | `{decision: deny, message: 사용자 응답 없음}` | `permission` |
| `review` | `{content, decisions[...], source_node?, title?}` | `{decision, edited?, feedback?}`(요청마다 enum) | 없음 | 없음(노드가 실패) | `review` |

agent 노드는 `session_grant(plan, node, 위임 방식)`(자신의 `ask_user` 연결 + 위임 대상 grant를
`member_interaction_kinds`로 거른 것)을 `AgentRequest.interactions`로 넘긴다. 연결이 없으면 `None`이고, 백엔드는
요청을 열지 않는다. 위임 방식 sink는 `request_input`을 ctx로 넘긴다(백엔드의 `InteractivePort` 검사 통과).

## 위임 방식 `sdk-subagents`

`member_fields = [model, system_prompt, tools, disallowed_tools, resources]`, `max_depth=1`,
`allows_outgoing_flow=false`, `requires_backend_capability="subagents"`, `member_interaction_kinds=["tool_permission"]`.
`resources`를 넣은 이유: SDK `AgentDefinition`이 skills·mcpServers·prompt(지침)를 서브에이전트별로 받는다.
files·hooks 칸은 세션 공유라 백엔드가 위임자 쪽으로 합치고 경고한다(design §R12.5).

`run`: 위임자 요청에 `subagents = subagent_specs(members)`를 싣고 위임자 백엔드로 실행한다. 백엔드에 넘기는 sink는
`ctx`를 감싸 `SubagentResultListener`(ac-runtime, `on_subagent_result(name, *, text, status, actor, tool_use_id)`)를 만족한다. 백엔드(claude-sdk·fake)가
위임 하나가 끝날 때마다 결과 전문으로 부르면 `ctx.emit_replies(대상, {결과 포트: text})`로 대상의 답변 연결을
평가한다(결과 포트 = 대상 노드 타입의 첫 출력 포트). 그 밖의 속성(예: `request_input`)은 `ctx`로 넘긴다.

`composable=true`: `contribute(plan, ctx)`가 `DelegationContribution(subagents=…, wrap_sink=…)`(위 sink 감싸기)를
돌려준다.

저장 시점 정적 검사(design §5.2R.7): `declared_names`는 `{"subagent": [대상 노드 id]}`, `static_issues`는 빈 목록이다.
`agent` 노드의 `validate`는 이 노드가 위임자이면 등록된 위임 방식의 두 선택 메서드를 `ac-teams.delegation_static_issues`로
부른다(엔진 검증 = 서버 저장 전 검사 경로). 합쳐 실행할 방식들의 이름 겹침은 실행 전에 `delegation.duplicate_<묶음>_names`로 나온다.

## 혼합 위임 (design §5R.6)

한 위임자의 대상이 여러 위임 방식(예: `subagent` 연결 + `delegate` 연결)에 걸치면, 모든 방식이 디스크립터
`composable`이고 `contribute`가 있을 때만(`ComposableDelegation`) 합쳐 실행한다. 방식마다 필요한 백엔드 능력
(`requires_backend_capability`)을 확인하고(`delegation.backend_unsupported`), `merge_contributions`로 하위 에이전트·
플랫폼 도구·옵션을 이어 붙인 뒤(도구·하위 에이전트 이름 겹침, 옵션 값 충돌은 실패 —
`delegation.duplicate_host_tool_names` 등) 위임자 백엔드를 **한 번** 부른다. sink는 각 방식의 `wrap_sink`로 감싼다.
합칠 수 없는 방식이 섞이면 `agent.mixed_strategies`(details `strategies`·`not_composable`)로 실패한다(팀 검증
`team.mixed_strategies`가 먼저 막는다).

**주의:** 서브에이전트(대상 노드)의 답변은 `on_subagent_result` 알림을 주는 백엔드(claude-sdk·fake)에서만 나온다.
알림을 주지 않는 백엔드에서는 대상 노드에서 나가는 `reply` 연결이 있어도 답변이 없다(위임자 답변은 정상).

## 에이전트 도구 공급자 (X30, design §5.7R.3)

다른 기능이 agent 노드의 모델에게 도구를 주는 일반 확장 지점이다. agent 노드는 도구의 뜻을 모른다.
공급자(`ToolProvider`: `id` + `provide(ctx) -> ToolProvision`)를 서비스 `TOOL_PROVIDERS`(목록)로 넣는다.
Run마다 `start(services=...)`로 넣으며(통합 서버에서는 실행 범위 포트 X26 `runs.scopes` 항목이 넣는다),
자식 Run(중첩 팀)은 부모 서비스를 물려받는다. 서비스가 없거나 비면 지금 실행과 같다.

agent 노드 순서: 묶음 계산 → 공급자마다 `provide`(맥락 `ToolProvisionContext`: run·루트 run·팀 구성·노드·
`node_path`·에이전트·회차·유효 묶음·백엔드 능력·`emit`·취소 토큰) → 공급 도구를 위임 도구 뒤에 붙임 →
소비한 칸(`consumed_slots`)을 백엔드 요청 묶음에서 뺌(그 칸의 `resource.slot_unsupported` 경고도 뺌).
경고(`log.warning`, details `code`)는 `ToolProviderCodes`다.

| 코드 | 언제 | 결과 |
| --- | --- | --- |
| `tools.provider_failed` | `provide` 예외(형식 이름만 싣는다)·잘못된 결과 | 그 공급자만 건너뜀 |
| `tools.duplicate_name` | 위임 도구·앞선 공급 도구와 이름이 겹침 | 공급 도구를 뺌 |
| `tools.backend_capability_missing` | 백엔드 `capabilities.host_tools`가 거짓 | 공급 도구를 모두 뺌, 실행은 계속 |

위임 대상 중 `sdk-subagents`는 위임자 세션 안이라 따로 공급받지 않고, `host` 대상은 자기 NodeRun이라 자기
묶음으로 공급받는다. 방식 하나로 위임하면 공급 도구가 위임 방식의 `run`이 붙이는 위임 도구보다 앞에 놓인다
(이름 충돌 검사는 방식의 `declared_names`, 없으면 `contribute`로 위임 도구 이름을 미리 읽어 한다).

테스트·본보기 공급자 `agent_console_nodes_core.testing.EchoToolProvider`(입력 `text`를 돌려주는 도구 하나,
호출마다 이벤트 하나, `slot`을 주면 그 칸이 있을 때만 도구를 주고 칸을 소비):

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_nodes_core import ToolProvisionContext, provide_tools
>>> from agent_console_nodes_core.testing import EchoToolProvider
>>> from agent_console_runtime import CancelToken

>>> async def emit(type, payload):
...     print(type, payload["chars"])
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="pl", node_path=("pl",),
...     agent_id="pl", call=0, iteration=0, bundle=ResourceBundle(),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken(),
... )
>>> provision = provide_tools([EchoToolProvider("echo", tool_name="echo", prefix="> ")], ctx)
>>> [tool.name for tool in provision.host_tools]
['echo']
>>> result = asyncio.run(provision.host_tools[0].handler({"text": "hi"}))
echo.called 2
>>> result.text
'> hi'

```

## 최소 사용 예 (앱 조립)

```python
>>> import asyncio
>>> from agent_console_contracts import Agent, Graph, WorkspaceSettings
>>> from agent_console_nodes_core import AGENT_LOOKUP, RESOURCE_TYPES_EXTENSION, WORKSPACE_SETTINGS
>>> from agent_console_resources import load_resource_types
>>> from agent_console_runtime import (
...     GraphRuntime,
...     InMemoryEventBus,
...     Registries,
...     Services,
...     load_registries,
... )
>>> from agent_console_runtime.testing import InMemoryRecorder

>>> registries = Registries()
>>> _ = load_registries(registries)  # 노드·연결·위임 방식·백엔드(entry point, 여기서는 fake 백엔드 포함)
>>> _ = load_resource_types(registries.extension(RESOURCE_TYPES_EXTENSION))  # 리소스 종류
>>> {"agent", "user", "resource"} <= {e.key for e in registries.node_types.list()}
True

>>> agents = {  # 보통은 정의 저장소에서 찾는다
...     "pl": Agent(id="pl", name="PL", backend="fake-agent", backend_options={"default": {"response": "PL: $prompt"}})
... }
>>> services = Services(
...     {
...         AGENT_LOOKUP: agents.get,  # id → Agent | None
...         WORKSPACE_SETTINGS: WorkspaceSettings(),  # 공통 층
...         # RESOURCE_LOOKUP: FunctionResources(find_resource, read_body),
...         # RUN_FILES_ROOT·WORKING_DIRECTORY: 실행 파일·작업 폴더 경로(문자열)
...     }
... )
>>> graph = Graph.model_validate(
...     {
...         "id": "team",
...         "name": "팀",
...         "nodes": [
...             {"id": "you", "type": "user"},
...             {"id": "pl", "type": "agent", "config": {"agent_ref": "pl"}},
...         ],
...         "edges": [
...             {
...                 "id": "m1",
...                 "source": {"node": "you", "port": "says"},
...                 "target": {"node": "pl", "port": "in"},
...                 "kind": "message",
...             },
...             {
...                 "id": "a1",
...                 "source": {"node": "pl", "port": "out"},
...                 "target": {"node": "you", "port": "hears"},
...                 "kind": "reply",
...             },
...         ],
...     }
... )
>>> recorder = InMemoryRecorder()  # 운영에서는 ac-store SqliteStorage
>>> runtime = GraphRuntime(registries, recorder, InMemoryEventBus(), services=services)
>>> run = asyncio.run(runtime.run(graph, {"text": "안녕"}))  # 대화 턴은 services=에 SESSIONS를 Run마다
>>> run.status
'completed'
>>> [e.payload["text"] for e in recorder.events.list(run.id) if e.type == "run.reply"]
['PL: 안녕']

```

## 앱이 주입하는 것

| 이름 | 종류 | 없으면 |
| --- | --- | --- |
| `AGENT_LOOKUP` | `ServiceKey[Callable[[str], Agent \| None]]` | agent 노드 실패(`agent.lookup_unavailable`), 검증 생략 |
| `WORKSPACE_SETTINGS` | `ServiceKey[WorkspaceSettings]` | 공통 층 비어 있음 |
| `DEFAULT_BACKEND` | `ServiceKey[str]` | 모든 층이 비면 실패(`agent.no_backend`) |
| `WORKING_DIRECTORY` | `ServiceKey[str]` | 유효 `working_directory`도 없으면 `cwd=None` |
| `RESOURCE_LOOKUP` | `ServiceKey[ResourceLookup]` | 붙은 리소스 미전달 + 경고(`agent.resources_unavailable`) |
| `RUN_FILES_ROOT` | `ServiceKey[str]` | 파일 칸 미전달 + 경고(`files.unavailable`) |
| `SESSIONS` | `ServiceKey[Mapping[str, SessionRef]]` | 새 세션 |
| `TEAM_LOOKUP` | `ServiceKey[TeamLookup]` (`(id, 버전 \| None) -> Graph \| None`) | `team` 노드 실패(`team.lookup_unavailable`) |
| `TOOL_PROVIDERS` | `ServiceKey[Sequence[ToolProvider]]` (Run마다) | 공급 도구 없음(지금 실행과 같다) |
| `RESOURCE_TYPES_EXTENSION` (`"resource_types"`) | `registries.extension(...)` | 첨부가 "모르는 종류"로 빠짐 |

오류 코드: `NodesCoreErrorCodes`(`agent.*`, `files.*`, `delegation.*`, `resource.*`, `user.not_reviewable`, `team.*`).

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-nodes-core`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-nodes-core/tests
```

설치 메타데이터의 entry point만 로드하고 fake 백엔드로 계층·순차·병렬(join all)·혼합·팀원 입구·중간 답변,
설정 층·세션·허용 상호작용·리소스 묶음(파일 기록), 연결 종류를 다른 id로 등록해도 같은 실행(R0)을 확인한다.

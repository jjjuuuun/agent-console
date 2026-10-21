# agent-console-teams

팀 구성 그래프의 **의미**를 계산하는 순수 라이브러리. 입구·답변, 위임 대상, 리소스 첨부, 노드별 허용 상호작용(grant)을
해석하고, 섞인 그래프 규칙을 검증하며, 노드의 유효 설정(4층 + 리소스 첨부, 출처)을 만든다.
설계: `specs/agent-console/design.md` §R1.2·§R1.2a, §R2, §R3.1·§R3.1a·§R3.1b, §R3.2, §R12.1, §R14.2.

- **이름을 모른다.** 연결 종류·노드 타입·위임 방식·상호작용 종류 id는 이 패키지에 없다. 판단 근거는
  - 엣지 디스크립터 `scheduling`(`entry`·`exit`·`flow`·`none`)·`invocation`·`interaction`·`connects`·`default_ports`
  - 노드 타입 디스크립터 `role`·`executable`·`binds{kind, field}`
  - 위임 방식 디스크립터 `max_depth`·`allows_outgoing_flow`·`member_fields`·`member_interaction_kinds`·`requires_backend_capability`
  - 설정 `delegation.max_depth`·`settings_merge`, 백엔드 `capabilities.interactions`와 선택 훅 `validate_settings`
- **입구와 답변은 명시된 연결뿐**이다(`scheduling=entry/exit`). 그래프 모양으로 추론하지 않는다.
  자동 추론은 검증 이슈의 **제안 데이터**(`Issue.suggestions[].patch`)에서만 쓴다.
- 노드·엣지 config 키(예: 노드 층 설정 `settings`, 상호작용 연결 `kinds`)는 `TeamConventions` 데이터다.
  기본값은 기본 플러그인(`ac-nodes-core`) 스키마와 맞췄고, 다른 키를 쓰는 플러그인은 바꿔 넘긴다.
- 파일·DB·네트워크를 쓰지 않는다. 에이전트 정의·공통 설정·리소스 조회·백엔드 능력·훅은 인자로 받는다.

## 설치

```bash
uv sync --all-packages                    # 워크스페이스 안
uv pip install ./packages/py/features/ac-teams     # 단독(의존: contracts, graph, registry, resources, settings)
```

## 최소 사용 예

```python
>>> from agent_console_contracts import Agent, WorkspaceSettings
>>> from agent_console_teams import effective_settings, team_plan, validate_team
>>> from agent_console_teams.testing import Kit

```

실제로는 레지스트리의 디스크립터(노드·연결 종류, 위임 방식)를 넘긴다. 여기서는 기본 플러그인 이름과 무관한
테스트 디스크립터 묶음 `Kit`(사람 `human-x`, 일꾼 `actor-x`, 입구 `hello`, 답변 `bye`, 위임 `boss` 등)을 쓴다.

```python
>>> k = Kit()
>>> graph = k.graph(
...     [k.person("me"), k.worker("lead", who="pl", settings={"model": "m-team"}), k.worker("be", who="backend")],
...     [
...         k.edge("m1", "entry", "me", "lead"),
...         k.edge("d1", "invoke", "lead", "be"),
...         k.edge("a1", "exit", "lead", "me"),
...     ],
... )
>>> plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
>>> plan.entry_nodes, plan.answer_nodes  # 입구 노드(entry 엣지가 들어옴), 답변 노드(exit 엣지가 나감)
(('lead',), ('lead',))
>>> [(link.member, link.strategy) for link in plan.delegates_of["lead"]]  # DelegationLink
[('be', 'inner')]
>>> plan.agent_refs  # 노드 → 에이전트 정의 id
{'lead': 'pl', 'be': 'backend'}

>>> workspace = WorkspaceSettings.model_validate(  # 공통 층·delegation·settings_merge
...     {"agent_defaults": {"model": "m-common", "tools": ["Read"]}}
... )
>>> agents = {"pl": Agent(id="pl", name="PL"), "backend": Agent(id="backend", name="BE")}
>>> validate_team(
...     graph,
...     node_types=k.node_types,
...     edge_types=k.edge_types,
...     strategies=k.strategies,  # X12 디스크립터
...     agents=agents,
...     workspace=workspace,
...     resolve_ports=Kit.resolve_ports,  # 동적 포트 해석(앱은 레지스트리 구현으로)
...     plan=plan,
... )
[]

>>> eff = effective_settings(plan, "lead", agents=agents, workspace=workspace, strategies=k.strategy_map)
>>> eff.value.model, eff.provenance["/model"], eff.value.tools, eff.provenance["/tools/0"]
('m-team', 'node', ['Read'], 'common')
>>> [layer.id for layer in eff.layers], eff.warnings, eff.inapplicable
(['common', 'team', 'agent', 'node'], [], [])

```

### 실행 묶음까지(1R.6 연결 순서)

```python
from agent_console_teams import node_bundle, node_settings

ns = node_settings(plan, "pl", agents=agents, workspace=ws, resource_types=types, resources=lookup)
# 내부: resource_strategies(slot_key_of=attachment_slot_key(...)) → resolve_layers(schema, rules, 표)
#       → placed_from_resolved
composed = node_bundle(
    ns, resource_types=types, resources=lookup, accepted_slots=caps.resource_slots
)
composed.bundle.slots, composed.bundle.sources, composed.issues
```

### 층을 직접 다루기

```python
from agent_console_settings import Layer
from agent_console_teams import layers_for, merge_rules, resolve_settings

layers = layers_for(plan, "pl", agent=agent, workspace=ws)  # 공통 → 팀 구성 → 에이전트 → 노드
layers.insert(2, Layer("project", "프로젝트", {"model": "m"}))  # 층 추가는 목록에 하나 넣기
ns = resolve_settings(layers, rules=merge_rules(ws, graph))
```

- 공통 바로 아래 층은 `scope_layers=[Layer(...)]`로 넣는다(`layers_for`·`agent_layers`·`node_settings`·
  `effective_settings`, 예: 프로젝트 층의 작업 폴더). 이 패키지는 층의 뜻을 모르고, 생략하면 지금과 같다.
- 층 값은 **지정한 필드만** 읽는다(`model_dump(exclude_unset=True)`). 생략 = 상속, `null`·빈 목록 = 그 층에서 지정.
- `settings_merge`는 공통 → 팀 구성 순서로 합친 뒤 `rules`로 넘긴다(`merge_rules`).
- 공통 층의 이전 형식 `default_backend`는 `agent_defaults.backend`가 없을 때 backend로 읽는다.
- 병합 문제(`Resolved.issues`)·넓힘(`find_widenings`)·형식 오류는 `EffectiveSettings.warnings`로, 위임받는 노드에서
  적용되지 않는 필드(위임 방식 `member_fields` 밖)는 `EffectiveSettings.inapplicable`로 나간다.
- 채팅·편집기·위임·상호작용 같은 사용자 설정 묶음은 `user_settings(workspace, graph)`(기본값 → 공통 → 팀 구성).

### 백엔드 훅

```python
from agent_console_contracts import AgentSettings, InteractionGrant, Issue


class MyHook:  # SettingsValidator 프로토콜
    def validate_settings(self, effective: AgentSettings, grant: InteractionGrant) -> list[Issue]:
        if asks_user(effective) and "approve" not in grant.kinds:
            return [
                Issue(
                    severity="warning",
                    code="interaction.no_path",
                    message="...",
                    details={"kinds": ["approve"]},
                )
            ]
        return []
```

훅은 자기 세션을 여는 에이전트 노드마다(위임받지 않는 노드 + `shares_session` false 방식으로 불리는 대상) 그
세션 grant(`session_grant`: 자신 + 같은 세션 방식 위임 대상 grant를 `member_interaction_kinds`로 거른 것)와 함께
불린다. `interaction.no_path` 이슈에 제안이 없으면 `details.kinds`를
허용하는 상호작용 연결을 사용자 쪽 노드로 잇는 제안을 붙인다. 훅 예외는 `team.validator_failed` 경고가 된다.

### 실행 경로(엔진 결과는 인자로, design §2R.1)

엔진을 import하지 않는다. 앱(서버·CLI·테스트)은 아래 순서로 조립만 한다.

```python
from agent_console_teams import (
    merge_validation,
    prepare_run,
    run_blockers,
    team_plan,
    team_rules_apply,
    validate_team,
)

engine = runtime.validate(graph, services=services)  # 엔진 검증(앱이 부름)
team = []
if team_rules_apply(engine):  # 모르는 타입 error가 있으면 건너뜀
    team = validate_team(graph, ..., graph_checks=False, plan=plan)
issues = merge_validation(engine, team)  # 화면용: 같은 뜻 중복 제거
blockers = run_blockers(engine, team)  # 실행 차단 이슈만
if not blockers:
    prep = prepare_run(
        graph, plan, workspace
    )  # RunPreparation{grants, interaction_settings, flow_settings}
    await runtime.start(
        graph,
        ...,
        interaction_grants=prep.grants,
        interaction_settings=prep.interaction_settings,
        flow_settings=prep.flow_settings,  # 반복·실행 한도(유효 설정 `flow`)
    )
```

- `blocks_run(issue)`: `issue.blocks_run`, 없으면 severity error.
- `merge_validation(..., equivalents=DEFAULT_EQUIVALENTS)`: 같은 노드에 같은 뜻의 엔진 error가 있으면 팀 이슈를 뺀다.
  같은 뜻 표는 데이터 `{팀 코드: 엔진 코드 접두}`(기본 `team.agent_not_found` → `agent.not_found`). 다른 플러그인 조합이면 표를 넘긴다.
- `team_rules_apply(engine, skip_prefixes=DEFAULT_TEAM_SKIP_PREFIXES)`: 엔진 error 코드가 `unknown`으로 시작하면 거짓.

### 실행 백엔드 사전 점검(5.2R.4)

해결 순서는 설정 층 그대로다(노드 → 에이전트 → 팀 구성 → 공통 `agent_defaults.backend`·옛 `default_backend`
→ 인자 `default_backend`). 백엔드를 쓰는 노드는 디스크립터로 판단한다(에이전트 정의에 묶인 실행 가능 노드, 또는
`capabilities`에 `TeamConventions.backend_capability`가 있는 노드). 위임받는 노드는 위임자 세션에서 돌므로
막을 대상은 세션 주인 노드뿐이다. 백엔드를 자동으로 고르지 않는다.

```python
from agent_console_teams import resolve_backends, unresolved_backends

resolved = resolve_backends(plan, agents=agents, workspace=ws)  # {node_id: backend_id | None}
blocked = unresolved_backends(plan, resolved, agents=agents)  # [UnresolvedBackend(node_id, label)]
```

### 화면 요약(design §2R.6, 2R.7)

```python
from agent_console_teams import bundle_preview, plan_summary, validation_summary

summary = plan_summary(plan)  # TeamPlanSummary{entries, answers, grants}
# 답변 자리의 label·order·final·stream은 엣지 타입 디스크립터 reply_fields(JSON Pointer)로 config에서 읽는다.
# 값이 없으면 그 위치의 config_schema 기본값, 그것도 없으면 label=엣지 label, final=true, stream=false.
# 이 패키지에는 답변 연결 config 키 이름이 없다(H1).

validation_summary(
    merge_validation(engine, team)
)  # GraphValidationSummary{blocks_run, error_count, ...}

preview = bundle_preview(
    plan,
    "lead",
    resource_types=types,
    resources=lookup,
    backends={"b": caps},
    workspace=ws,
    strategies=strategies,
)
# BundlePreview{bundle, warnings}: 받지 않는 칸(resource.slot_unsupported) + 위임받는 노드의 세션 공유 칸
# (resource.slot_session_shared, 세션 주인 백엔드의 capabilities.subagent_slots에 없는 칸). x-secret 평문은 ***.
```

- 백엔드 선택 훅 `PreviewNotes.preview_notes(effective, bundle) -> list[Issue]`(4R.9): `bundle_preview(..., notes={백엔드
  id: 훅})`를 주면 세션 주인 백엔드의 훅을 세션 주인 유효 설정·이 노드 묶음으로 불러 이슈를 뒤에 붙인다(예: claude-sdk
  `observe.hook_probe_wrapped` "hook 감싸기 켜짐"). `catalog_from_registries`가 훅을 가진 백엔드를
  `TeamCatalog.preview_notes`로 모은다. 훅 예외는 `team.validator_failed` 경고.

- 강제되지 않는 실행 범위: `node_settings(..., backends={id: BackendCapabilities})`(또는 `resolve_settings`)는 유효
  `limits`에 값이 있는데 유효 `backend`의 `capabilities.enforce`에서 **같은 이름** 항목이 true가 아니면 경고
  `limits.not_enforced`(path `/limits/<필드>`)를 더한다. 이 자리에 `limits`가 적용되지 않으면(위임 방식
  `member_fields`) 건너뛴다. 단독 함수 `limits_warnings(value, enforce)`. 필드 목록은 코드에 없다.

### 규칙 모듈

`validate_team`은 규칙 함수를 순서대로 돌린다(`_validate.TEAM_RULES`): `_rules_structure`(연결 규칙·참조) →
`_rules_entry`(입구·답변·도달) → `_rules_delegation`(위임) → `_rules_loops`(반복) → `_rules_teams`(중첩 팀) →
`_rules_interactions`(상호작용·백엔드 훅·검토) → `_rules_resources`(받지 않는 칸).
규칙은 `TeamCheckContext`(`_check_context`)를 읽고 `add`로 이슈를 쌓는다. 엣지 허용 종류(디스크립터 ∩ config) 계산은
`_plan.edge_kinds` 하나를 grant 계산과 검증이 같이 쓴다.

### 사용처 찾기

```python
from agent_console_teams import definition_references

refs = definition_references(
    "resource", "team-guide", graphs=graphs, agents=agents, workspace=ws, node_types=node_descs
)
# DefinitionReference[]: 리소스 노드(binds) → 팀 구성 층·노드 층·에이전트 층·공통 층 첨부
```

노드 타입 이름을 모른다(`binds{kind, field}`·`TeamConventions` 키). `kind`가 리소스 종류면 설정 층 첨부도 찾는다.

### 첨부 덮어쓰기 검사와 `x-secret` 가리기

```python
from agent_console_teams import agent_attachments, attachment_issues, graph_attachments

placed = graph_attachments(graph, plan=team_plan(graph, node_types=nt, edge_types=et))
issues = attachment_issues(placed, types=resource_types, resources=lookup)
# 리소스가 없는 첨부는 비밀 의심 규칙으로 본다: secret_rules=SecretRules().with_extra(...)(기본 = 기본 규칙)
# path = 문서 기준: /settings/resources/0/config_override/env/API_KEY,
#   /nodes/1/config/settings/resources/0/config_override/..., /edges/3/config/config_override/...
```

- 위치: 에이전트 `/resources/<i>`, 공통 설정 `/agent_defaults/resources/<i>`, 팀 층 `/settings/resources/<i>`,
  노드 층 `/nodes/<n>/config/<node_settings_key>/resources/<i>`, 리소스 연결 `/edges/<e>/config/<edge_override_key>`
  (`plan`이 있을 때만, 리소스 연결 여부는 디스크립터로 정해진다).
- 검사는 `ac-resources.validate_attachment`(덮어쓰기를 리소스 config에 얕게 덮어 종류 검사). 덮어쓰기가 없는 첨부는
  검사하지 않고, `ref` 리소스가 없으면 warning만 낸다. 저장을 막을지는 호출자가 정한다(서버: error면 422).
- 표시용 안전망: `mask_effective_secrets(effective, *, types, resources)`(유효 설정 `value.resources[].config_override`),
  `mask_node_settings(settings, *, types, resources) -> (NodeSettings, ResourceLookup)`(묶음 미리보기 — 덮어쓰기와
  리소스 config 모두)는 config 스키마의 `x-secret` 위치에서 `secret://` 참조가 아닌 값을 `***`로 바꾼다.

## 검증 규칙(`TeamIssueCodes`)

| 코드 | 심각도 | 근거 |
| --- | --- | --- |
| `team.no_entry` | error(`blocks_run`) | `entry` 엣지가 실행 가능 노드로 가지 않음. 제안: 들어오는 연결 없는 노드를 입구로 |
| `team.no_reply` | warning | `exit` 엣지 없음. 제안: 나가는 흐름 없는 노드를 답변으로 |
| `team.unreachable` | warning | 실행 가능 노드인데 `entry`·`flow`·위임으로 들어오는 연결이 없음(사용자 쪽 노드 제외). 반복을 닫는 사이클 연결만 들어와도 같다(첫 회차에 지나가지 않음). 제안: 입구로 |
| `team.entry_not_executable` | warning | 입구 엣지가 `executable=false` 노드로 감 |
| `team.connects_mismatch` | error | 엣지 디스크립터 `connects` 역할이 맞지 않음 |
| `team.agent_not_found` / `team.resource_not_found` | error / warning | `binds`로 묶인 정의가 없음(`agents`·`resources`를 줬을 때만) |
| `team.mixed_invocation` | error | 흐름·입구로 받으면서 위임으로도 불림(반복을 닫는 사이클 연결은 세지 않음 — `flow.loop_invoked_only`) |
| `team.mixed_strategies` | error | 한 노드의 위임 대상이 서로 다른 위임 방식이고 그중 디스크립터 `composable`이 거짓인(또는 모르는) 방식이 있음. 모두 `composable`이면 허용(혼합 위임, design §5R.6). `details.not_composable`. 제안: 그 연결을 합칠 수 있는 방식의 위임 연결 종류로 바꾸기(이미 쓰는 방식 우선, 엣지 config의 방식 덮어쓰기 키는 옮기지 않음) |
| `team.unknown_strategy` | warning | 등록되지 않은 위임 방식 |
| `delegation.depth_exceeded` | error | 위임 깊이 > min(디스크립터 `max_depth`, 설정 `delegation.max_depth`). 방식 `max_depth: null`이면 설정만. `details.path` = 위임 경로. 상수 `DELEGATION_DEPTH_EXCEEDED`(옛 이름 `DELEGATION_TOO_DEEP`, 4R까지 값 `team.delegation_too_deep`) |
| `team.delegation_cycle` | error | 위임 연결 순환 |
| `team.flow_from_delegate` | error | 위임받는 노드의 흐름 엣지(디스크립터 `allows_outgoing_flow=false`). `exit`(답변)은 허용 |
| `team.backend_capability_missing` | error | 위임자 백엔드에 `requires_backend_capability` 능력이 없음 |
| `team.member_field_ignored` | warning | 위임받는 노드가 `member_fields` 밖 필드를 위임자와 다르게 지정(예: backend) |
| `interaction.no_path` | warning | 백엔드 훅이 냄. 제안: 상호작용 연결 추가 |
| `interaction.unsupported_in_delegate` | warning | 위임받는 노드의 grant가 `member_interaction_kinds` 밖. 제안: 연결의 `kinds` 좁히기 |
| `interaction.unsupported_by_backend` | warning | 세션 백엔드 `capabilities.interactions` 밖. 제안: 좁히기 |
| `interaction.kinds_not_allowed` | warning | 엣지 config `kinds`에 디스크립터가 허용하지 않는 종류 |
| `review.dead_end` | warning | 스케줄되는 노드의 검토 결정(config `review.decisions`)의 포트가 아무 데도 안 이어짐. 제안: 답변으로 |
| `team.validator_failed` | warning | 훅 예외(위임 방식 정적 검사 예외 포함, `details{strategy, method}`) |
| `delegation.invalid_config` | error | 위임자 노드 config `delegation[방식 id]`(`TeamConventions.node_delegation_key`)가 방식 디스크립터 `config_schema`에 맞지 않음. path `/delegation/<방식 id>/…`. 모르는 방식·위임자가 아닌 노드는 보지 않음 |
| `delegation.invalid_config_schema` | warning | 방식 디스크립터 `config_schema` 자체가 잘못됨 |
| `delegation.duplicate_member` | error | 한 위임자가 같은 대상을 같은(유효) 방식으로 두 번 넘게 이음. 뒤 연결의 엣지 이슈, `details{delegator, member, strategy, edges}` |
| `delegation.duplicate_<묶음>_names` | error | `delegation_checks`를 줄 때만: 한 위임자가 쓰는 방식이 둘 이상이고 그 방식들이 `declared_names`로 알린 이름이 묶음 안에서 겹침(예: `delegation.duplicate_host_tool_names`). `composable`이 거짓인 방식은 뺀다 |
| `flow.max_iterations_invalid` | error | 사이클 연결(디스크립터 `cycle`)의 유효 최대 반복(엣지 config `max_iterations` → 설정 `flow.max_iterations` → 디스크립터 `cycle.max_iterations`, `ac-graph.effective_max_iterations`)이 없거나 1 미만. 엣지 이슈, path `/max_iterations` |
| `flow.loop_invoked_only` | error | 반복 영역(`ac-graph.loop_regions`) 안 노드가 위임으로만 불리고 사이클 연결 말고는 들어오는 흐름이 없음(스케줄되지 않음) |
| `team.recursive` | error | 중첩 팀 노드(디스크립터 `binds.kind == TeamConventions.team_kind`)가 이 팀 구성 자신 또는 자식·손자를 따라가다 경로에 있는 팀 구성을 다시 넣음. `details.path` = 팀 구성 id 경로. 자기 참조는 조회 없이도 낸다 |
| `team.nesting_exceeded` | error | 중첩 깊이(이 팀 구성 = 0) > 유효 `delegation.max_nesting`(기본 데이터 3, null = 제한 없음). `details{depth, limit, path}` |
| `team.team_not_found` | error | `teams=` 조회가 팀 구성(고정 버전 `TeamConventions.node_version_key`)을 못 찾음. `details{team, version}` |
| `team.child_no_entry` | error | 자식 팀 구성에 입구가 없음(자식 검증 요약 `details.issues`) |

중첩 팀 이슈는 `node_id` = 중첩 팀 노드, `path` = 문서 기준 `/nodes/<i>/config/<binds.field>`. 자식 팀 구성은
`validate_team(..., teams=lookup)`(`TeamLookup = (id, 버전|None) -> Graph|None`, `LookupError`도 "없음")로 읽는다.
`teams`가 없으면 자기 참조만 본다. 실행 중에도 엔진이 같은 코드(`team.recursive`·`team.nesting_exceeded`)로 막는다.
중첩 팀 노드의 팀 층 덮어쓰기는 `with_team_settings(graph, override)`(지정한 값만, 객체는 재귀 병합).

흐름 사이클은 `graph_checks=True`(기본)일 때 함께 도는 `ac-graph.validate_graph(cycle_edge=descriptor_cycle_edge)`가
본다. 사이클마다 사이클 연결(디스크립터 `cycle`)이 있으면 허용(검토 반려를 앞 노드로 되돌리기 포함)이고, 없으면
`cycle` 이슈이며 되돌아가는 연결을 사이클 연결 종류로 바꾸는 제안이 붙는다. `none`·`entry`·`exit` 엣지는 순환 계산에서
빠지므로 `사용자 → A → 사용자`는 순환이 아니다.

연결 의미 검사(예: 조건 연결의 조건)는 엔진 쪽 선택 능력이라 이 패키지가 직접 부르지 않는다. 단독으로 쓸 때는
`validate_team(..., edge_checks=lambda g: validate_edges(g, registries, services))`처럼 주입한다. 서버(실행 모듈의
저장 전 검사)는 엔진 검증(`validate_graph_with` → `validate_edges`)과 팀 규칙(`graph_checks=False`)을 합치므로
넘기지 않는다.

위임 방식 고유 정적 검사(design §5.2R.7)도 같은 방식이다. 방식 객체의 선택 메서드 `static_issues(config, members)`·
`declared_names(config, members)`(ac-runtime `StaticDelegationChecks`·`DelegationNameDeclarer`, `members` =
`DelegationTarget`)를 메서드 유무로만 부른다. 단독으로 쓸 때는 `validate_team(..., delegation_checks={방식 id: 방식 객체})`
또는 `delegation_static_issues(plan, checks, delegators=, agents=)`, 서버는 엔진 검증(노드 타입 `validate`가 등록된
위임 방식을 부름)으로 얻으므로 넘기지 않는다. 방식 이슈는 `node_id`가 비면 위임자로, 엣지 이슈가 아니면 `path` 앞에
`/delegation/<방식 id>`를 붙인다. 실행 시점 `validate(plan)`은 그대로 실행 때 돈다.

### 제안 데이터

`Issue.suggestions[{id, label, patch: GraphPatch}]`. 연결 종류는 디스크립터 속성(`scheduling`·`interaction`)과 `connects`로
고르고, 사용자 쪽 노드(입구의 출발·답변의 도착 노드)가 있으면 그 노드에, 없으면 `connects` 반대편 역할의 노드 타입
(정의에 묶이지 않고 숨기지 않은 첫 타입)으로 새 노드를 만들어 잇는다. 포트는 `default_ports` → 노드 포트 목록의 첫 포트.
연결 종류만 바꾸는 제안(`SuggestionBuilder.replace_kind`)은 `remove_edge_ids` + `add_edges`(같은 id·같은 포트, 새 종류,
새 종류 스키마가 선언한 config 키만 옮김)다. `SuggestionBuilder`로 다른 검사기에서도 같은 방식의 제안을 만들 수 있다.

## grant 규칙

- 노드에서 나가는, 디스크립터 `interaction`이 있는 엣지마다 허용 종류 = `interaction.kinds` ∩ 엣지 config `kinds`(목록일 때).
- 노드 grant = 그 합(처음 나온 순서). 대기 한도 = 엣지 config `timeout_seconds` 중 가장 짧은 값,
  초과 시 동작 = 그 엣지의 `on_timeout`(없으면 처음 지정된 값). 둘 다 없으면 null(설정 `interaction.*`을 따름).
- `session_grant(plan, 위임자, strategies)`: 위임자 grant + 위임 대상 grant(위임 방식 `member_interaction_kinds`로 거름).
  디스크립터 `shares_session`이 false인 방식(대상이 자기 세션에서 돈다, 예: `host`)의 대상은 종류도 대기 한도도
  더하지 않는다(5.2R.43). `shares_session(link, strategies)`·`runs_in_own_session(plan, node_id, strategies)`가 같은
  판단을 주고, `prepare_run(..., strategies=)`를 주면 엔진 대기 grant도 이 세션 단위다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-teams`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
UV_LINK_MODE=copy uv run pytest packages/py/features/ac-teams
```

테스트는 기본 플러그인 없이 **임의 이름**의 노드·엣지 타입과 위임 방식 디스크립터로 모든 규칙을 확인한다.
그 디스크립터 묶음은 공개 하위 모듈 `agent_console_teams.testing`(`KITS`, `Kit(names)`)이라 다른 프로젝트의 테스트에서도 쓸 수 있다.

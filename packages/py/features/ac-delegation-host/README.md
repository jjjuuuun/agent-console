# agent-console-delegation-host

독립 위임 방식 `host`(X12 위임 방식 플러그인, design §5R.6). 위임자 모델에게 **위임 도구** 하나(플랫폼
도구 `HostTool`)를 주고, 모델이 도구를 부르면 대상 노드를 엔진의 `ctx.invoke_node`로 **자기 NodeRun·세션·
백엔드·모델·리소스**에서 실행해 그 결과를 도구 결과로 돌려준다. 대상은 다시 위임하거나(중첩) 자기
`ask_user` 연결로 사용자에게 되물을 수 있다. 서버·웹·노드 플러그인 없이 엔진(`agent-console-runtime`)과
계약만으로 쓴다.

- 규칙은 디스크립터 값이다(`host_descriptor()`): 깊이 = 사용자 설정 `delegation.max_depth`만
  (`max_depth: null`), 대상의 나가는 흐름 연결 금지(`allows_outgoing_flow: false`), 대상의 모든 설정 필드
  적용(`member_fields` = `AgentSettings` 전체), 대상 되묻기 제한 없음, 위임자 백엔드 능력 `host_tools` 필요,
  `composable: true`(다른 composable 방식과 한 위임자에서 합쳐 실행), `shares_session: false`(대상은 자기
  세션에서 돈다 — 대상의 상호작용 종류·대기 한도는 위임자 세션 grant에 더해지지 않는다, 5.2R.43).
- 도구 이름·파라미터 이름·모델에게 보이는 문구는 방식 config(`HostDelegationConfig`)의 **스키마 기본값**이다.
  위임자 노드의 방식별 config(예: 에이전트 노드 `delegation.host`)로 바꾼다. 코드에 이름별 분기는 없다.
- 도구 입력 = `{<target_param>: 대상 노드 id(enum), <task_param>: 할 일}`. 할 일은 대상 노드 타입의 첫 입력
  포트로 넣는다(`input_port=`로 바꿈).
- 결과: 위임 연결 config `result`가 `text`(기본)면 대상의 첫 출력 포트 값, `reply`면 대상의 답변 연결
  (`scheduling = exit`)이 낼 답변 텍스트. 대상 실패·깊이 초과(`delegation.depth_exceeded`)·순환·모르는 대상·
  빈 할 일은 예외가 아니라 `is_error` 도구 결과다(위임자 모델이 판단한다). 실패 문구(`failure_text`)의
  `{code}`·`{message}`에는 엔진 가림(`ctx.secrets.redact`)을 건 값만 들어간다.
- 같은 대상 직렬·동시 실행 슬롯·취소 정리·대상 답변 내기·기록은 엔진이 한다. 이 방식은 대상을 직접
  실행하지 않는다.
- 혼합 위임: `contribute(plan, ctx)`는 백엔드를 부르지 않고 `DelegationContribution(host_tools=[도구])`만
  돌려준다. 노드는 방식마다 받은 것을 `merge_contributions`(ac-runtime)로 합친다(도구 이름 겹침 =
  `delegation.duplicate_host_tool_names`).
- 저장 시점 정적 검사(design §5.2R.7): `static_issues(config, members)`는 연결 결과 모양
  (`delegation.invalid_result_mode`, 엣지 이슈)과 스키마로 표현할 수 없는 config 규칙(대상·할 일 파라미터 이름이
  같음, `delegation.invalid_config`)을, `declared_names(config, members)`는 `{"host_tool": [도구 이름]}`을 돌려준다.
  config 스키마 위반·같은 대상 중복은 `ac-teams` 일반 규칙이 낸다.

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-contracts`(디스크립터·이슈 모델), `agent-console-runtime`(X12 프로토콜·`HostTool`·
  `invoke_node`). 노드 플러그인(`ac-nodes-core`)·팀(`ac-teams`)·백엔드는 모른다(import-linter 계약).
- **pydantic**: 방식 config 검증과 JSON Schema(디스크립터 `config_schema`). 이미 계약 패키지가 쓴다.
- 대안으로 위임 방식이 백엔드를 직접 불러 대상을 실행할 수 있지만, 노드 실행 규칙(설정·리소스·되묻기·
  기록)을 두 벌 만들게 되어 택하지 않았다(design §5R.6 결정).

## 설치

```bash
pip install agent-console-delegation-host
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-delegation-host
```

설치하면 entry point `agent_console.delegation_strategies`의 `host`로 등록된다
(`load_registries`가 찾는다). 지우면 `host` 연결은 팀 검증의 "등록되지 않은 위임 방식" 경고가 된다.

## 최소 사용

```python
>>> from agent_console_contracts import Agent
>>> from agent_console_delegation_host import HostDelegation
>>> from agent_console_runtime import AgentRequest, DelegationMember, DelegationPlan

>>> host = HostDelegation()
>>> d = host.descriptor
>>> d.id, d.composable, d.max_depth, d.requires_backend_capability, d.shares_session
('host', True, None, 'host_tools', False)

>>> plan = DelegationPlan(
...     strategy="host",
...     delegator_node_id="lead",
...     backend="fake-agent",
...     request=AgentRequest(agent=Agent(id="lead", name="Lead"), prompt="로그인 구현"),
...     members=[
...         DelegationMember(node_id="be", edge_id="lead->be", role="백엔드", delegate_when="서버 작업"),
...         DelegationMember(node_id="qa", edge_id="lead->qa", role="검증"),
...     ],
...     config={"tool_name": "hand_off"},
... )
>>> host.validate(plan)
[]
>>> (tool,) = host.contribute(plan, ctx=None).host_tools  # 핸들러를 부를 때만 엔진 맥락이 필요하다
>>> tool.name, tool.input_schema["properties"]["target"]["enum"], tool.input_schema["required"]
('hand_off', ['be', 'qa'], ['target', 'task'])
>>> print(tool.description.splitlines()[-2])
- be: 백엔드 — 서버 작업

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

엔진 안에서 쓰려면 레지스트리에 등록하고(`registries.delegation_strategies.register("host", HostDelegation())`
또는 entry point), 위임자 노드가 `strategy.run(plan, ctx)`(단독) 또는 `contribute`(혼합)를 부른다.
`tests/test_agent_console_delegation_host.py`에 엔진·fake 백엔드·claude-sdk(SDK 목)로 끝까지 돌리는 예가 있다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

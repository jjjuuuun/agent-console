# agent-console-example-delegation

새 **위임 방식**(확장 지점 X12)을 플러그인 패키지 하나로 추가하는 예제(R0·R10.4, design §5R.14).
엔진·서버·웹 코드를 고치지 않고, 설치하면 위임 방식 목록(`GET /api/v1/delegation-strategies`)과 편집기의
위임 연결 "위임 방식" 선택지에 나타나고 제거하면 사라진다.

위임 방식 `example.round_robin`(차례로 맡기기)
- 위임 대상을 **연결 순서대로 한 번씩** 엔진의 `ctx.invoke_node`로 불러(대상마다 자기 NodeRun) 위임자의 입력을
  그대로 맡기고, 결과를 이어 붙여 위임자의 결과로 낸다. 모델을 부르지 않는 결정적 위임이다.
- 설정(위임자 노드 config `delegation.example.round_robin`): `item_template`(기본 `[{target}] {result}`,
  변수 `target`·`role`·`result`·`status`), `separator`(기본 빈 줄), `failure_text`(기본 `(실패: {code})`),
  `stop_on_failure`(기본 false — 켜면 대상 하나가 실패하는 즉시 위임자도 `example.round_robin.member_failed`로 실패).
- 규칙은 디스크립터 값이다: **`composable = false`** — 같은 위임자에 다른 방식(예: 서브에이전트 `subagent`,
  독립 위임 `host`)의 대상을 함께 두면 팀 검증이 `team.mixed_strategies`(error)로 막는다. 섞어 쓸 수 있는 방식과의
  차이를 보여 주려고 일부러 끈 값이다. `requires_backend_capability = null`(위임자 백엔드를 부르지 않음),
  `allows_outgoing_flow = false`, `max_depth = null`(설정 `delegation.max_depth`만).

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

```python
from agent_console_contracts import AgentSettings, DelegationStrategyDescriptor, Issue
from agent_console_runtime import AgentResult, DelegationPlan, NodeContext


class RoundRobinDelegation:
    descriptor = DelegationStrategyDescriptor(
        id="example.round_robin",
        title="차례로 맡기기",
        member_fields=list(AgentSettings.model_fields),
        max_depth=None,
        allows_outgoing_flow=False,
        requires_backend_capability=None,
        member_interaction_kinds=None,
        composable=False,
    )

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        return []

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult:
        parts = []
        for m in plan.members:  # 최소 예는 기본 에이전트 노드 포트(in·out)를 가정한다
            view = await ctx.invoke_node(m.node_id, {"in": plan.request.prompt}, by_edge=m.edge_id)
            parts.append(f"[{m.node_id}] {view.outputs.get('out', '')}")
        return AgentResult(status="succeeded", text="\n\n".join(parts))
```

실제 구현은 `src/agent_console_example_delegation/round_robin.py`(설정을 pydantic 모델로 검증·스키마 생성, 포트 이름을
대상 노드 타입에서 읽음, 실패 처리, 안전 치환 `fill`).

## 등록

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console_runtime.DELEGATION_STRATEGIES_GROUP`
(`agent_console.delegation_strategies`), 이름 = 디스크립터 `id`.

```toml
[project.entry-points."agent_console.delegation_strategies"]
"example.round_robin" = "agent_console_example_delegation:RoundRobinDelegation"
```

entry point 없이 엔진만 쓸 때는 레지스트리에 직접 등록한다(테스트가 그렇게 한다):
`registries.delegation_strategies.register("example.round_robin", RoundRobinDelegation())`.

팀 구성에서 쓰기: 위임 연결(`delegate`)의 config `strategy`로 방식을 고른다(연결 종류의 기본 방식을 덮어쓴다).

```yaml
edges:
  - id: d1
    source: {node: lead, port: delegates}
    target: {node: writer, port: delegated}
    kind: delegate
    config: {strategy: example.round_robin}
nodes:
  - id: lead
    type: agent
    config:
      agent_ref: lead
      delegation:                      # 방식별 설정(생략 = 스키마 기본값)
        example.round_robin: {separator: " | "}
```

## 설치·제거

저장소 루트에서 실행한다. WSL(`/mnt/c`)에서는 환경변수를 붙인다(CLAUDE.md "고정·환경 메모").

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-delegation   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-delegation                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/delegation-strategies`에 `example.round_robin`이 나온다.
- 제거: 목록에서 사라진다. 이 방식을 고른 팀 구성은 지워지지 않고, 저장 전 검증이 `team.unknown_strategy`(warning)로
  알리며, 실행하면 위임자 노드가 `agent.unknown_strategy`로 실패한다.
- 설치한 채로 끄기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example.round_robin`을 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로
mypy·pytest를 돌린다(`uv run poe examples`). 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`
(저장소에서 `uv run poe wheels`) 뒤 `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-delegation
uv run --project ../../.. python -m pytest
```

테스트는 기본 노드(에이전트 노드·위임 연결, `agent-console-nodes-core`)와 fake 백엔드로 끝까지 돈다: 차례 실행·
설정·실패 처리, 다른 방식과 섞으면 `team.mixed_strategies`, 제거하면 경고·실행 실패.
E2E: `apps/web/e2e/08-extension.spec.ts`(`ext` flavor)가 이 패키지를 임시 폴더에 설치해 목록·실행을 확인한다.

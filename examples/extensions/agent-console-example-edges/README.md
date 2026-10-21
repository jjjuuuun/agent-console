# agent-console-example-edges

새 **연결 종류**(엣지 타입, 확장 지점 X2)를 플러그인 패키지 하나로 추가하는 예제(R0·R10.4).
엔진·서버·웹 코드를 고치지 않고, 설치하면 편집기의 "연결 종류 선택"·설정 화면 "새 연결 기본 종류"에 나타나고 제거하면 사라진다.

연결 종류 `example.relay`(접두어 붙여 넘기기)
- `scheduling = flow`: 위 노드가 성공해 `out`에 값을 냈으면 아래 노드 `in`으로 넘긴다. 실패·값 없음이면 그 경로는 막힌다.
- 설정: `prefix`(문자열, 기본 `[중계] `). 값이 문자열이면 앞에 붙이고, 아니면 그대로 넘긴다.
- 연결 규칙 `connects`: 역할 `agent` → `agent`(노드 타입 디스크립터 `role` 문자열). 팀 구성 검증이 다른 역할 사이 연결을 `team.connects_mismatch`로 막는다.
- 외부 호출 없이 결정적으로 동작한다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

```python
from agent_console_contracts import EdgeConnects, EdgePortPair, EdgeSpec, EdgeTypeDescriptor
from agent_console_runtime import Activation, NodeRunView


class RelayEdge:
    descriptor = EdgeTypeDescriptor(
        id="example.relay",
        title="접두어 붙여 넘기기",
        scheduling="flow",
        connects=EdgeConnects(source=["agent"], target=["agent"]),
        default_ports=EdgePortPair(source="out", target="in"),
        config_schema={"type": "object", "properties": {"prefix": {"type": "string"}}},
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None  # dead-path
        return Activation(f"{edge.config.get('prefix', '')}{source.outputs[edge.source.port]}")
```

실제 구현은 `src/agent_console_example_edges/relay.py`(설정을 pydantic 모델로 검증·스키마 생성).
`scheduling`은 엔진 어휘(`flow`·`none`·`entry`·`exit`)이고, 엔진·편집기는 연결 종류 이름이 아니라 이 속성으로 동작한다.

## 등록

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console_runtime.EDGE_TYPES_GROUP`(`agent_console.edge_types`),
이름 = 디스크립터 `id` = 그래프 엣지의 `kind`.

```toml
[project.entry-points."agent_console.edge_types"]
"example.relay" = "agent_console_example_edges:RelayEdge"
```

설치하지 않은 모듈이면 서버 설정 `plugins.modules`에 `"example.relay=agent_console_example_edges:RelayEdge"` 형식으로 적어도 된다
(같은 검사기·`plugins.enabled` 필터를 거친다).

## 설치·제거

저장소 루트에서 실행한다. WSL(`/mnt/c`)에서는 환경변수를 붙인다(CLAUDE.md "고정·환경 메모").

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-edges   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-edges                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/edge-types`에 `example.relay`가 나오고, 편집기에서 에이전트 둘을 이으면 선택지에 "접두어 붙여 넘기기"가 보인다.
- 제거: 선택지에서 사라진다. 이 연결을 쓰는 팀 구성은 지워지지 않고 검증이 `unknown_edge_type`으로 알린다(실행은 막힌다).
- 설치한 채로 끄기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example.relay`를 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).

```bash
cd examples/extensions/agent-console-example-edges
uv run --project ../../.. python -m pytest
```

E2E: `apps/web/e2e/08-extension.spec.ts`의 "연결 종류" 시나리오가 이 패키지를 임시 폴더에 설치해 쓴다.

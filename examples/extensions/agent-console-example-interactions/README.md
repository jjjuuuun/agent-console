# agent-console-example-interactions

새 **상호작용 종류**(실행 중 사용자에게 받는 요청, 확장 지점 X15)와 그 종류를 허용하는 **연결 종류**(X2)를
플러그인 패키지 하나로 추가하는 예제(R0·R10.4). 엔진·서버·웹 코드를 고치지 않는다.

- 상호작용 종류 `example.sign_off`(서명 받기): 요청 `{text}`, 응답 `{approved: boolean (필수), note?: string}`.
  화면 힌트 `renderer = "example-sign-off"`는 웹이 모르는 이름이라, 웹은 **응답 스키마로 만든 폼**(승인함 체크박스 + 메모)으로 받는다.
  응답은 서버·엔진이 `response_schema`로 검증한다(틀리면 422 `validation_failed`).
- 연결 종류 `example.ask_sign_off`(서명 받기 허용): `scheduling = none`(엔진이 평가하지 않음), `interaction.kinds = ["example.sign_off"]`,
  역할 `agent` → `user`, 기본 포트 `out` → `asks`. 이 연결이 나가는 에이전트만 서명 요청을 열 수 있다. 없으면 요청은 열리지 않고
  백엔드에는 `unavailable`로 돌아간다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

상호작용 종류는 **디스크립터 데이터 하나**다(클래스 불필요).

```python
from agent_console_contracts import (
    EdgeInteraction,
    EdgeTypeDescriptor,
    InteractionKindDescriptor,
    UiHints,
)

SIGN_OFF = InteractionKindDescriptor(
    id="example.sign_off",
    title="서명 받기",
    response_schema={
        "type": "object",
        "properties": {"approved": {"type": "boolean"}},
        "required": ["approved"],
    },
    ui_hints=UiHints(renderer="example-sign-off"),
)


class AskSignOffEdge:
    descriptor = EdgeTypeDescriptor(
        id="example.ask_sign_off",
        title="서명 받기 허용",
        scheduling="none",
        interaction=EdgeInteraction(kinds=["example.sign_off"]),
    )

    def activates(self, source, edge):
        return None  # none 연결은 엔진이 평가하지 않는다
```

요청을 여는 쪽은 노드(`ctx.request_input(InteractionRequest(kind="example.sign_off", ...))`)나 그 노드가 넘긴 실행 백엔드다.
fake 백엔드로는 에이전트 `backend_options.default.ask: [{kind: "example.sign_off", ...}]` 규칙으로 열 수 있다.

## 등록

```toml
[project.entry-points."agent_console.interaction_kinds"]   # agent_console_runtime.INTERACTION_KINDS_GROUP
"example.sign_off" = "agent_console_example_interactions:SIGN_OFF"

[project.entry-points."agent_console.edge_types"]          # agent_console_runtime.EDGE_TYPES_GROUP
"example.ask_sign_off" = "agent_console_example_interactions:AskSignOffEdge"
```

entry point가 디스크립터 객체를 가리키면 로더(`as_interaction_kind`)가 감싸 등록한다.

## 설치·제거

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-interactions   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-interactions                        # 제거
```

설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/interaction-kinds`에 `example.sign_off`, `GET /api/v1/edge-types`에 `example.ask_sign_off`가 나온다.
- 제거: 둘 다 사라진다. 이 연결을 쓰는 팀 구성은 검증이 `unknown_edge_type`으로 알리고, 백엔드가 이 종류를 요청하면 열리지 않는다.
- 설치한 채로 끄기: 서버 설정 `plugins.enabled`(허용 목록)에서 두 이름을 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

```bash
cd examples/extensions/agent-console-example-interactions
uv run --project ../../.. python -m pytest
```

설치 없이 돈다(`pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).
E2E: `apps/web/e2e/08-extension.spec.ts`의 "상호작용 종류" 시나리오가 이 패키지를 임시 폴더에 설치해 쓴다.

# agent-console-example-nodes

새 노드 타입을 **플러그인 패키지 하나**로 추가하는 예제(확장 지점 X1, R0·R10.4).
엔진·서버·웹 코드를 고치지 않고, 설치하면 편집기 팔레트와 설정 폼에 나타나고 제거하면 사라진다.

노드 타입 `example.text_transform`(텍스트 변환)
- 입력 `in`의 값을 텍스트로 바꾼다(문자열은 그대로, 그 밖은 JSON).
- 설정: `mode`(enum: `upper`·`lower`·`title`·`keep`), `prefix`(문자열), `strip`(불리언).
- 출력 `out` = `prefix + 대소문자변환(strip 적용 텍스트)`. 외부 호출 없이 결정적으로 동작한다.
- 팔레트 묶음 `예제`, 아바타 `Aa`, 색 `#0ea5e9`.

### 팀 구성에서의 의미

| 디스크립터 속성 | 값 | 뜻 |
| --- | --- | --- |
| `role` | `agent` (`TEAM_ROLE`) | 연결 규칙(연결 종류의 `connects`)이 보는 역할 문자열. 기본 연결 종류(사용자 메시지 `message`·넘기기 `handoff`·답변 `reply`)가 받는 값이라 에이전트 자리에 그대로 놓인다. 역할은 고정 목록이 아니다 — 새 역할 이름을 쓰면 그 이름을 `connects`에 적은 연결 종류로만 이을 수 있다 |
| `binds` | 없음 | 에이전트·리소스 정의 하나에서 만들어지는 노드가 아니다. 그래서 설정 층(공통·팀·에이전트)·리소스 첨부·사용처 목록의 대상이 아니고 설정은 노드 config뿐이다 |
| `rerunnable` | `true` | 결정적이라 끊긴 실행을 이어 갈 때 저장된 입력으로 이 노드부터 다시 실행해도 안전하다 |

예: 사용자 → (입구) → 텍스트 변환 → (답변) → 사용자. 편집기에서 노드를 놓고 패널의 "입구"·"답변" 토글을 켜면 된다
(E2E `08-extension`의 "노드 타입" 시나리오).

이 패키지는 uv workspace 멤버가 아니다. 따로 설치하고 제거한다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 설치·제거

저장소 루트에서 실행한다. WSL(`/mnt/c`)에서는 아래 환경변수를 붙인다(CLAUDE.md "고정·환경 메모").

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만

# 설치(편집 모드). 의존(agent-console-contracts·runtime)은 workspace 설치본을 그대로 쓴다.
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-nodes

# 제거 — 서버를 재시작하면 팔레트·설정 폼에서 사라진다. 이 타입을 쓰는 팀 구성은 지워지지 않고
# 검증이 `unknown_node_type`으로 알린다(실행은 막힌다).
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-nodes
```

설치한 채로 끄려면 서버 설정 `plugins.enabled`(허용 목록, 지정하면 목록에 없는 entry point는 모두 건너뜀)를 쓰고 그 목록에서 `example.text_transform`을 뺀다.

WSL이 아니면 `--python` 없이 `uv pip install -e ...`가 프로젝트 `.venv`에 설치한다.

주의: `uv sync`는 기본적으로 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면
`uv sync --all-packages --inexact`를 쓴다(`uv run`은 지우지 않는다).

## 서버에서 확인

entry point는 서버 시작 시 한 번 읽는다. 설치·제거 후에는 **서버를 재시작**한다.

```bash
uv run agent-console serve
curl -s http://127.0.0.1:<port>/api/v1/node-types | grep example.text_transform   # 설치 시 나타남
```

웹 편집기 팔레트의 `예제` 묶음에 "텍스트 변환"이 보이고, 노드를 놓으면 설정 폼이 `config_schema`·`ui_schema`로 그려진다.
서버 설정 `plugins.enabled`를 지정했다면 그 목록에 `example.text_transform`도 넣어야 로드된다.

## 새 노드 타입 만들기 — 최소 코드

1. **entry point 하나**를 선언한다(`pyproject.toml`). 그룹 이름은 `agent_console_runtime.NODE_TYPES_GROUP`
   값(`agent_console.node_types`), 이름은 디스크립터 `id`와 같아야 한다(레지스트리 key = 디스크립터 id = `NodeSpec.type`).

   ```toml
   [project.entry-points."agent_console.node_types"]
   "example.text_transform" = "agent_console_example_nodes:TextTransformNode"
   ```

2. **`NodeType` 프로토콜**을 구현한다(`src/agent_console_example_nodes/text_transform.py`).
   공개 계약(`agent_console_contracts`)과 엔진 인터페이스(`agent_console_runtime`)만 import한다.

   | 멤버 | 이 예제에서 |
   | --- | --- |
   | `descriptor: NodeTypeDescriptor` | id·title·category, `config_schema`(pydantic 모델의 `model_json_schema()`), `ui_schema`(rjsf 힌트), `static_ports`, `ui_hints`(icon·color) |
   | `resolve_ports(config) -> PortSpec` | 고정 포트 `in` → `out` |
   | `validate(config, ctx) -> list[Issue]` | 스키마 밖 의미 검증: 아무것도 바꾸지 않는 설정이면 경고 |
   | `async execute(ctx, inputs) -> NodeResult` | `inputs["in"]`을 변환해 `NodeResult(status="succeeded", outputs={"out": ...})` |

   클래스를 entry point로 걸면 엔진이 인자 없이 인스턴스화한다. 외부 값(설정·서비스)이 필요하면
   `ctx.services`(`ServiceKey`)나 `ctx.secrets`로 받고, 전역·환경변수를 직접 읽지 않는다.

3. **테스트**는 `agent_console_runtime.testing.make_harness()`로 엔진을 띄우고 노드를 레지스트리에 직접 등록해 돌린다.

   ```python
   h = make_harness()
   h.registries.node_types.register("example.text_transform", as_node_type(TextTransformNode))
   run = await h.make().run(graph, {"in": " hi "})
   ```

변환 로직만 쓰고 싶으면 노드 없이 `transform_text(value, TextTransformConfig(...))`를 import해 쓴다.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).

```bash
cd examples/extensions/agent-console-example-nodes
uv run --project ../../.. python -m pytest
```

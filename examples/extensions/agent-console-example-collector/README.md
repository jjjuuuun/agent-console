# agent-console-example-collector

새 **관측 수집기(X7)** 를 플러그인 패키지 하나로 추가하는 예제(R0.3·R10.4).
엔진·서버·웹·백엔드 코드를 고치지 않고, 설치하면 claude-sdk 백엔드의 수집기 목록
(`GET /api/v1/backends`의 `collectors`)에 나타나고 제거하면 사라진다.

수집기 `example.tool_count`(도구 호출 수)
- 실행 하나 동안 모델 응답의 도구 호출 블록을 도구 이름별로 센다(실행별 상태 `ctx.state`).
- 실행 결과 메시지에서 이벤트 `example.tool_count{total, by_tool}`를 한 번 낸다. 백엔드가 RunEvent 일반형으로
  내보내므로 실행 화면·로그 화면(`platform-runs` 출처)에 그대로 보인다.
- 설정 `only`(셀 도구 이름 목록, 비우면 전부)는 pydantic 모델 `ToolCountConfig`다. 디스크립터 `config_schema`가
  이 스키마이고, 틀린 설정은 검증 경고 `observe.collector_config_invalid`로 보인다.
- 실행에 개입하지 않는다. 예외는 백엔드가 삼키고 실행마다 경고 이벤트 하나로 남긴다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

`BaseClaudeSdkCollector`를 상속하고 필요한 메서드만 고친다. 아래는 실행 부품 `CollectorRun`에
SDK 메시지를 직접 넣어 본 예다(실제로는 백엔드가 넣는다).

```python
>>> import asyncio
>>> from typing import ClassVar
>>> from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock
>>> from agent_console_backend_claude_sdk.collectors import (
...     BaseClaudeSdkCollector, CollectorContext, CollectorRun, resolve_collector_settings,
... )

>>> class ToolCount(BaseClaudeSdkCollector):
...     id: ClassVar[str] = "tool-count"
...     title: ClassVar[str] = "도구 호출 수"
...     emits: ClassVar[tuple[str, ...]] = ("tool.count",)
...     default_backend: ClassVar[str] = "claude-agent-sdk"
...     def on_message(self, message: object, ctx: CollectorContext) -> None:
...         if isinstance(message, AssistantMessage):
...             n = sum(isinstance(b, ToolUseBlock) for b in message.content)
...             ctx.state["n"] = ctx.state.get("n", 0) + n
...         elif isinstance(message, ResultMessage):
...             ctx.emit("tool.count", {"count": ctx.state.get("n", 0)})

>>> sent = []
>>> async def out(event):
...     sent.append((event.type, dict(event.payload)))
>>> async def warn(warning):
...     sent.append(("log.warning", warning.details))
>>> run = CollectorRun(
...     [ToolCount()],
...     resolve_collector_settings({"collectors": {"tool-count": {"enabled": True}}}),
...     clock=lambda: 0.0, redact=lambda v: v, out=out, warn=warn,
... )
>>> calls = AssistantMessage(content=[ToolUseBlock(id="t1", name="Read", input={})], model="m")
>>> done = ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
...                      num_turns=1, session_id="s")
>>> for message in (calls, done):
...     asyncio.run(run.on_message(message))
>>> sent
[('tool.count', {'count': 1})]

```

실제 구현은 `src/agent_console_example_collector/tool_count.py`(설정 모델, 이름별 집계, 순수 함수
`count_tool_uses`·`merge_counts`). 아래는 그 구현을 entry point로 등록한 것처럼 찾는 예다.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_backend_claude_sdk.collectors import COLLECTORS_GROUP, discover_collectors
>>> ep = EntryPoint(
...     "example.tool_count", "agent_console_example_collector:ToolCountCollector", COLLECTORS_GROUP
... )
>>> found, reports = discover_collectors("claude-agent-sdk", entry_points=[ep])
>>> [c.descriptor.id for c in found]          # 설치했으면 entry_points 인자 없이 부른다
['example.tool_count', 'sdk-hooks', 'mcp-calls']
>>> found[0].descriptor.config_schema["properties"]["only"]["title"]
'셀 도구'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 등록과 설정

```toml
[project.entry-points."agent_console.collectors"]   # agent_console_backend_claude_sdk.collectors.COLLECTORS_GROUP
"example.tool_count" = "agent_console_example_collector:ToolCountCollector"
```

백엔드는 `descriptor.backend`(기본 `claude-agent-sdk`)가 자기 id인 수집기만 쓴다. 다른 id의 claude-sdk
백엔드 인스턴스에 쓰려면 `ToolCountCollector(backend="<id>")`를 `ClaudeSdkBackend(collectors=[...])`로 넘긴다.

에이전트·팀·공통 설정(`observe`, 생략하면 상위 설정을 물려받는다). 정하지 않은 수집기는 꺼져 있다.

```yaml
observe:
  collectors:
    example.tool_count:
      enabled: true
      config:
        only: [Bash, Edit]     # 비우면 전부
```

## 설치·제거

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-collector   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-collector                        # 제거
```

설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/backends`의 claude-sdk 항목 `collectors`에 `example.tool_count`가 나온다. 위 설정으로 실행하면
  실행이 끝날 때 `example.tool_count` 이벤트가 하나 나온다.
- 제거: 수집기 목록에서 사라진다. 설정의 `observe.collectors.example.tool_count`는 남지만 검증 경고
  `observe.unknown_collector`만 나고 실행은 그대로 된다(테스트로 확인).
- 설치한 채로 끄기: 설정에 `enabled: false`(또는 항목을 지움).

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

```bash
cd examples/extensions/agent-console-example-collector
uv run --project ../../.. python -m pytest
```

설치 없이 돈다(`pythonpath = ["src"]`). SDK는 가짜 클라이언트(`agent_console_backend_claude_sdk.testing.FakeSdkClient`)를
주입하므로 모델 호출이 없다. 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).

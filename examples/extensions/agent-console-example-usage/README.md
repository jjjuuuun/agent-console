# agent-console-example-usage

새 **사용량 출처**(확장 지점 X13)를 플러그인 패키지 하나로 추가하는 예제(R0·R10.4).
엔진·서버·웹 코드를 고치지 않고, 설치하면 사용량 화면의 출처 목록과 창 카드에 나타나고 제거하면 사라진다.

사용량 출처 `example.manual_count`(직접 적은 사용량)
- 공식 사용량 값이 없는 도구(사내 게이트웨이, 팀 공용 할당량 등)를 사용자가 설정에 직접 적는다.
- 설정: `windows: [{window, used, limit, status?}]` → 창마다 `used_ratio = used / limit`. 적지 않은 값(`status`·`resets_at`)은 `None`(지어내지 않는다).
- 신뢰 등급 `trust = "manual"`: 알려진 등급(`official`·`observed`·`estimated`·`unofficial`) 밖의 값도 된다는 예. 화면은 기본 배지로 보인다.
- 관측 시각은 주입된 시계(`ctx.now`). 외부 호출이 없다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

```python
from agent_console_contracts import UsageSourceDescriptor, UsageWindowSnapshot
from agent_console_usage import UsageSourceContext


class ManualCountSource:
    descriptor = UsageSourceDescriptor(
        id="example.manual_count",
        title="직접 적은 사용량",
        trust="manual",
        config_schema={"type": "object", "properties": {"windows": {"type": "array"}}},
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        return [
            UsageWindowSnapshot(
                source=ctx.source_id,
                window=w["window"],
                used_ratio=w["used"] / w["limit"],
                observed_at=ctx.now,
            )
            for w in ctx.config.get("windows", [])
        ]
```

실제 구현은 `src/agent_console_example_usage/manual_count.py`(순수 함수 `windows_from_config`로 분리, 틀린 항목 건너뜀).
서버는 `usage.sources[].config`를 `config_schema`로 검증한 뒤 넘긴다(틀리면 그 출처만 오류로 보인다).

## 등록과 설정

```toml
[project.entry-points."agent_console.usage_sources"]   # agent_console_usage.USAGE_SOURCES_GROUP
"example.manual_count" = "agent_console_example_usage:ManualCountSource"
```

워크스페이스 설정(설정 화면 또는 `settings.yaml`):

```yaml
usage:
  sources:
    - id: example.manual_count
      config:
        windows:
          - {window: team_weekly, used: 120, limit: 500}
  window_labels: {team_weekly: "팀 주간 할당량"}
```

## 설치·제거

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-usage   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-usage                        # 제거
```

설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/usage/sources`에 나오고, 위 설정을 넣으면 `GET /api/v1/usage`와 사용량 화면 창 카드에 사용률이 보인다.
- 제거: 출처 목록·창 카드에서 사라진다. 설정의 `usage.sources` 항목은 남지만 등록된 출처가 없으므로 무시된다.
- 설치한 채로 끄기: 설정 항목에 `enabled: false`, 또는 서버 설정 `plugins.enabled`(허용 목록)에서 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

```bash
cd examples/extensions/agent-console-example-usage
uv run --project ../../.. python -m pytest
```

설치 없이 돈다(`pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).
E2E: `apps/web/e2e/08-extension.spec.ts`의 "사용량 출처" 시나리오가 이 패키지를 임시 폴더에 설치해 쓴다.

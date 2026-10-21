"""`hook` 종류: 명령형 hook 하나(이벤트·매처·명령, design §2R.8).

칸 `hooks` = `{name, event, matcher?, command, timeout_seconds?}` 목록.

- `event`는 **자유 문자열**이다. 이 종류는 이벤트 이름 목록을 갖지 않는다. 스키마의 `examples`는
  화면 제안일 뿐이며 생성 인자(`event_examples`)로 바꾼다(기본 `DEFAULT_EVENT_EXAMPLES`).
- 명령을 실제로 실행하는지·어떻게 실행하는지는 실행 백엔드가 정한다(실행 범위 검사, 설치자
  허용 여부). 이 종류는 실행하지 않는다.
- 명령 문자열에 평문 비밀로 의심되는 값(`ac-secret-rules` 기본 규칙)이 있으면 저장하지 않는다
  (`resource.plain_secret`, 위치만 알림).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agent_console_contracts import (
    Issue,
    KnownResourceSlots,
    Resource,
    ResourceTypeDescriptor,
    UiHints,
    x_ui,
)
from agent_console_resources import (
    PLAIN_SECRET,
    Content,
    ContributeContext,
    Contribution,
    SchemaResourceType,
)
from agent_console_secret_rules import SecretRules, default_rules

__all__ = ["DEFAULT_EVENT_EXAMPLES", "HookType", "hook_config_schema"]

DEFAULT_EVENT_EXAMPLES: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "Notification",
    "PreCompact",
)
"""이벤트 이름 제안(화면 콤보박스용 데이터). 목록에 없는 이름도 쓸 수 있다."""


def hook_config_schema(event_examples: Iterable[str] = DEFAULT_EVENT_EXAMPLES) -> dict[str, Any]:
    """hook config 스키마(이벤트 제안만 바꿔 만들 수 있다)."""
    return {
        "type": "object",
        "properties": {
            "event": {
                "type": "string",
                "minLength": 1,
                "title": "이벤트",
                "description": "hook을 걸 이벤트 이름입니다. 목록에 없는 이름도 쓸 수 있습니다.",
                "examples": list(event_examples),
                **x_ui(
                    tier="basic",
                    when="hook(도구 실행 전후에 도는 명령)을 다른 시점에 걸고 싶을 때 바꾸세요.",
                ),
            },
            "matcher": {
                "type": "string",
                "title": "매처",
                "description": (
                    "hook을 걸 대상입니다(예: 도구 이름 Bash, Write|Edit). 비우면 전부입니다."
                ),
                "examples": ["Bash", "Write|Edit"],
                **x_ui(tier="basic", when="특정 도구에만 hook을 걸고 싶을 때 적으세요."),
            },
            "command": {
                "type": "string",
                "minLength": 1,
                "title": "명령",
                "description": "실행할 명령입니다. 이벤트 내용을 JSON으로 받습니다.",
                **x_ui(
                    tier="basic",
                    when="hook이 할 일(검사 스크립트 등)을 바꾸고 싶을 때 바꾸세요.",
                    example="python scripts/check.py",
                ),
            },
            "timeout_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
                "title": "시간 제한(초)",
                "description": "명령을 기다리는 최대 시간입니다. 비우면 실행 백엔드 기본값입니다.",
                **x_ui(
                    tier="advanced",
                    when="명령이 오래 걸려 중간에 끊길 때 늘리세요.",
                    example=30,
                    unit="초",
                ),
            },
        },
        "required": ["event", "command"],
        "additionalProperties": False,
    }


class HookType(SchemaResourceType):
    """명령형 hook. `hooks` 칸에 한 항목을 낸다.

    Args:
        event_examples: 이벤트 이름 제안(스키마 `examples`).
        secret_rules: 명령 평문 비밀 검사 규칙(기본 `ac-secret-rules` 기본 규칙).
    """

    descriptor: ResourceTypeDescriptor

    def __init__(
        self,
        *,
        event_examples: Iterable[str] = DEFAULT_EVENT_EXAMPLES,
        secret_rules: SecretRules | None = None,
    ) -> None:
        self._rules = secret_rules
        self.descriptor = ResourceTypeDescriptor(
            id="hook",
            version=1,
            title="Hook(명령)",
            description="이벤트가 일어날 때 실행할 명령. 실행 여부는 실행 백엔드·설치자 설정이 "
            "정한다.",
            config_schema=hook_config_schema(event_examples),
            content=None,
            slot_key=None,
            combine="append",
            contributes=[KnownResourceSlots.HOOKS],
            ui_hints=UiHints(icon="훅"),
        )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """명령에 평문 비밀로 의심되는 값이 있으면 오류(값은 넣지 않는다)."""
        command = resource.config.get("command")
        if not isinstance(command, str) or not command:
            return []
        rules = self._rules or default_rules()
        if not rules.find_suspected(command, path="/command"):
            return []
        return [
            Issue(
                severity="error",
                code=PLAIN_SECRET,
                message="명령에 평문 비밀로 보이는 값이 있습니다. 비밀은 환경 변수로 전달하세요",
                path="/command",
                details={"resource": resource.id, "resource_type": resource.type},
            )
        ]

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """`hooks` 칸에 `[{name, event, matcher?, command, timeout_seconds?}]`."""
        config = resource.config
        event, command = config.get("event"), config.get("command")
        if not isinstance(event, str) or not event or not isinstance(command, str) or not command:
            return []
        item: dict[str, Any] = {"name": resource.id, "event": event, "command": command}
        matcher = config.get("matcher")
        if isinstance(matcher, str) and matcher:
            item["matcher"] = matcher
        timeout = config.get("timeout_seconds")
        if isinstance(timeout, int | float) and not isinstance(timeout, bool) and timeout > 0:
            item["timeout_seconds"] = timeout
        return [Contribution(KnownResourceSlots.HOOKS, [item])]

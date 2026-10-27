"""`mcp-server` 종류: MCP 서버 설정(stdio·http·sse).

칸 `mcp_servers` = `{name, type, command?, args?, env?, url?, headers?}` 목록
(SDK `McpServerConfig`와 같은 필드 이름 + `name`).
`env`·`headers` 값은 **`secret://이름` 참조만** 허용한다(평문 비밀 금지).
참조는 그대로 묶음에 들어가고 실제 값은 실행 백엔드가 비밀 공급자로 푼다.
"""

from __future__ import annotations

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
    SECRET_SCHEMA_KEY,
    Content,
    ContributeContext,
    Contribution,
    SchemaResourceType,
    find_plain_secrets,
)

__all__ = ["SECRET_FIELDS", "McpServerType"]

SECRET_FIELDS = ("env", "headers")
"""값이 `secret://` 참조여야 하는 config 객체 필드."""

# 값 형식(`secret://`)은 `extra_issues`(`resource.plain_secret`)에서 검사한다(위치만 알림).
# 값 스키마의 `x-secret: true`는 화면이 비밀 입력 칸을 그리는 구조화 힌트다.
_SECRET_MAP: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {"type": "string", SECRET_SCHEMA_KEY: True},
}

_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
            "title": "서버 이름",
            "description": (
                "에이전트가 보는 MCP 서버(외부 도구 서버) 이름입니다. 도구 이름 앞에 붙습니다."
            ),
            **x_ui(
                tier="basic",
                when="같은 이름의 서버가 겹치거나 도구 이름을 알아보기 쉽게 하고 싶을 때 바꾸세요.",
                example="github",
            ),
        },
        "transport": {
            "type": "string",
            "enum": ["stdio", "http", "sse"],
            "default": "stdio",
            "title": "연결 방식",
            "description": "명령을 실행해 잇는지(stdio) 주소로 잇는지(http·sse) 고릅니다.",
            **x_ui(
                enum_labels={"stdio": "명령 실행", "http": "HTTP 주소", "sse": "SSE 주소"},
                tier="basic",
                when="서버가 주소(URL)로 열려 있으면 http나 sse로 바꾸세요.",
            ),
        },
        "command": {
            "type": "string",
            "minLength": 1,
            "title": "명령(stdio)",
            "description": "서버를 띄울 명령입니다. 연결 방식이 stdio일 때 씁니다.",
            **x_ui(tier="basic", when="서버를 띄우는 방법이 바뀌었을 때 바꾸세요.", example="npx"),
        },
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "title": "인자(stdio)",
            "description": "명령에 넘길 인자입니다.",
            **x_ui(
                tier="basic",
                when="서버에 옵션을 넘겨야 할 때 바꾸세요.",
                example=["-y", "@modelcontextprotocol/server-github"],
            ),
        },
        "env": {
            **_SECRET_MAP,
            "title": "환경 변수(stdio)",
            "description": "서버에 넘길 환경 변수입니다. 비밀 값은 secret://이름으로만 적습니다.",
            **x_ui(tier="advanced", when="서버가 키·토큰 같은 값을 환경 변수로 받을 때 적으세요."),
        },
        "url": {
            "type": "string",
            "minLength": 1,
            "title": "URL(http·sse)",
            "description": "서버 주소입니다. 연결 방식이 http·sse일 때 씁니다.",
            **x_ui(
                tier="basic",
                when="서버 주소가 바뀌었을 때 바꾸세요.",
                example="https://example.com/mcp",
            ),
        },
        "headers": {
            **_SECRET_MAP,
            "title": "헤더(http·sse)",
            "description": "요청에 붙일 헤더입니다. 비밀 값은 secret://이름으로만 적습니다.",
            **x_ui(tier="advanced", when="서버가 인증 헤더를 요구할 때 적으세요."),
        },
    },
    "required": ["name"],
    "additionalProperties": False,
    "allOf": [
        {
            "if": {
                "anyOf": [
                    {"not": {"required": ["transport"]}},
                    {"properties": {"transport": {"const": "stdio"}}},
                ]
            },
            "then": {"required": ["command"]},
            "else": {"required": ["url"]},
        }
    ],
}


class McpServerType(SchemaResourceType):
    """MCP 서버 하나를 `mcp_servers` 칸에 낸다."""

    descriptor = ResourceTypeDescriptor(
        id="mcp-server",
        version=1,
        title="MCP 서버",
        description="에이전트가 쓸 MCP 서버(stdio·http·sse). 비밀은 secret:// 참조만.",
        config_schema=_CONFIG_SCHEMA,
        slot_key="name",
        combine="append",
        contributes=[KnownResourceSlots.MCP_SERVERS],
        ui_hints=UiHints(icon="M"),
    )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """`env`·`headers`에 평문 값이 있으면 오류(값은 메시지에 넣지 않는다)."""
        return [
            Issue(
                severity="error",
                code="resource.plain_secret",
                message="비밀 값은 secret://이름 참조로만 넣을 수 있습니다",
                path=pointer,
                details={"resource": resource.id, "resource_type": resource.type},
            )
            for pointer in find_plain_secrets(resource.config, SECRET_FIELDS)
        ]

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """`mcp_servers` 칸에 서버 한 항목."""
        config = resource.config
        entry: dict[str, Any] = {
            "name": config["name"],
            "type": config.get("transport", "stdio"),
        }
        for key in ("command", "args", "env", "url", "headers"):
            if config.get(key) is not None:
                entry[key] = config[key]
        return [Contribution(KnownResourceSlots.MCP_SERVERS, [entry])]

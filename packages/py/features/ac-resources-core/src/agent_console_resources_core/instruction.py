"""`instruction` 종류: 지침 문서(공용 CLAUDE.md, 에이전트별 지침, 프롬프트 조각).

칸 `instructions` = 문자열 목록. 백엔드가 순서대로 이어 붙인다(예: 빈 줄 두 개로).
"""

from __future__ import annotations

from typing import Any

from agent_console_contracts import (
    Issue,
    KnownResourceSlots,
    Resource,
    ResourceContentSpec,
    ResourceTypeDescriptor,
    UiHints,
    x_ui,
)
from agent_console_resources import (
    PREPEND_STRATEGY,
    Content,
    ContributeContext,
    Contribution,
    SchemaResourceType,
    content_text,
)

__all__ = ["InstructionType"]

_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "title": "제목",
            "description": (
                "지침의 제목입니다. 먼저 붙은 같은 제목 지침을 '바꾸기'로 대체할 때 씁니다."
            ),
            **x_ui(
                tier="basic",
                when="공통·팀 설정에서 붙은 같은 제목 지침을 대체하고 싶을 때 맞춰 적으세요.",
                example="코드 스타일",
            ),
        },
        "position": {
            "type": "string",
            "enum": ["append", "prepend"],
            "default": "append",
            "title": "위치",
            "description": "먼저 붙은 지침의 뒤(append)에 붙일지 앞(prepend)에 붙일지 정합니다.",
            **x_ui(
                tier="advanced",
                when="이 지침을 다른 지침보다 먼저 읽히게 하고 싶을 때 prepend로 바꾸세요.",
            ),
        },
        "heading": {
            "type": "boolean",
            "default": False,
            "title": "제목 머리 붙이기",
            "description": "켜면 본문 앞에 '## 제목' 줄을 붙입니다.",
            **x_ui(tier="advanced"),
        },
        "text": {
            "type": "string",
            "title": "짧은 본문",
            "description": (
                "본문 파일 대신 쓰는 짧은 지침입니다. 둘 다 있으면 본문 파일이 우선입니다."
            ),
            **x_ui(
                tier="basic",
                when="짧은 지침을 파일 없이 바로 적고 싶을 때 쓰세요.",
                example="함수는 짧게 유지하세요.",
            ),
        },
    },
    "additionalProperties": False,
}


class InstructionType(SchemaResourceType):
    """지침 문서. 본문(markdown) 또는 config `text`를 `instructions` 칸에 한 항목으로 낸다."""

    descriptor = ResourceTypeDescriptor(
        id="instruction",
        version=1,
        title="지침",
        description="에이전트에 주는 지침 문서(공용 CLAUDE.md, 에이전트별 지침, 프롬프트 조각).",
        config_schema=_CONFIG_SCHEMA,
        content=ResourceContentSpec(media_types=["text/markdown", "text/plain"], editor="markdown"),
        slot_key="title",
        combine="append",
        contributes=[KnownResourceSlots.INSTRUCTIONS],
        ui_hints=UiHints(icon="지"),
    )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """본문 파일도 `text`도 없으면 경고."""
        if resource.content is None and not resource.config.get("text"):
            return [
                Issue(
                    severity="warning",
                    code="resource.content_missing",
                    message="지침 본문이 없습니다(본문 파일 또는 text)",
                    details={"resource": resource.id, "resource_type": resource.type},
                )
            ]
        return []

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """`instructions` 칸에 `[텍스트]`. position=prepend면 앞에 붙이기 전략."""
        config = resource.config
        text = content_text(content)
        if text is None:
            text = str(config.get("text") or "")
        if not text.strip():
            return []
        if config.get("heading"):
            title = str(config.get("title") or resource.name)
            text = f"## {title}\n\n{text}"
        combine = PREPEND_STRATEGY if config.get("position") == "prepend" else None
        return [Contribution(KnownResourceSlots.INSTRUCTIONS, [text], combine)]

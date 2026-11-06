"""설치자 설정(``modules.options.link-example-notes-runs``)과 패키지 기본 데이터
(``data/defaults.json``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

DEFAULTS_RESOURCE: Final = "data/defaults.json"
"""기본 데이터 위치(패키지 안 상대 경로)."""


def load_defaults() -> dict[str, Any]:
    """패키지 기본 데이터(도구 이름·문구·이벤트 type·한도)."""
    text = files(__package__ or __name__).joinpath(DEFAULTS_RESOURCE).read_text("utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


_DEFAULTS = load_defaults()


@dataclass(frozen=True)
class NotesToolText:
    """도구 이름·설명·결과 문구·지침·이벤트 type(전부 데이터).

    Attributes:
        name: 도구 이름(모델에게 보인다).
        description: 도구 설명.
        empty: 노트가 없을 때 결과 글.
        line: 노트 한 줄 틀(``{id}``·``{text}``·``{tags}``).
        instructions: 지침 틀(``{tool}`` = 도구 이름).
        event_type: 도구 호출마다 내는 RunEvent type.
    """

    name: str
    description: str
    empty: str
    line: str
    instructions: str
    event_type: str

    @classmethod
    def from_data(cls, data: dict[str, Any], *, name: str | None = None) -> NotesToolText:
        """기본 데이터 모양 → 문구(``name``을 주면 도구 이름만 바꾼다)."""
        tool = data["tool"]
        return cls(
            name=name or tool["name"],
            description=tool["description"],
            empty=tool["empty"],
            line=tool["line"],
            instructions=data["instructions"],
            event_type=data["event_type"],
        )


class NotesRunsSettings(BaseModel):
    """실행 중 에이전트가 쓰는 노트 읽기 도구의 이름과 한도를 정하는 설치자 설정입니다."""

    model_config = ConfigDict(extra="forbid")

    max_notes_per_call: int | None = Field(
        default=_DEFAULTS["max_notes_per_call"],
        ge=1,
        title="한 번에 읽는 노트 수 상한",
        description=(
            "에이전트가 도구를 한 번 부를 때 받을 수 있는 노트의 최대 개수입니다. "
            "리소스나 도구 입력이 더 많이 달라고 해도 이 수까지만 줍니다. "
            "비우면 노트 모듈의 목록 한도를 따릅니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="노트가 많아 에이전트 입력이 길어질 때 줄이세요.",
            unit="개",
        ),
    )
    tool_name: str | None = Field(
        default=None,
        min_length=1,
        pattern=r"^[A-Za-z0-9_-]+$",
        title="도구 이름",
        description=(
            "에이전트에게 보이는 노트 읽기 도구의 이름입니다. 비우면 기본 이름을 씁니다. "
            "다른 도구와 이름이 겹치면 이 도구가 빠집니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="다른 도구와 이름이 겹치거나 팀이 정한 도구 이름 규칙이 있을 때 바꾸세요.",
            example="team_notes",
        ),
    )

    def text(self) -> NotesToolText:
        """이 설정을 반영한 도구 문구."""
        return NotesToolText.from_data(_DEFAULTS, name=self.tool_name)


__all__ = [
    "DEFAULTS_RESOURCE",
    "NotesRunsSettings",
    "NotesToolText",
    "load_defaults",
]

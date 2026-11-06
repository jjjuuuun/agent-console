"""테스트 대역: 노트 모듈 없이 ``example_notes.reader``를 주는 작은 기능 모듈.

연동은 포트 이름으로만 잇기 때문에, 진짜 노트 모듈 대신 같은 이름의 포트를 주는 모듈로 조립해 시험할
수 있다(공간 → 노트 표, 파일·DB 없음).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .ports import NOTES_READER

__all__ = [
    "STATIC_NOTES_MODULE_ID",
    "SpaceUnavailableError",
    "StaticNote",
    "StaticNotesModule",
    "StaticNotesReader",
]

STATIC_NOTES_MODULE_ID: Final = "test-static-notes"


@dataclass(frozen=True)
class StaticNote:
    """노트 하나(``NoteLike`` 모양)."""

    id: str
    text: str
    tags: Sequence[str] = ()


class SpaceUnavailableError(Exception):
    """표에 없는 공간(``code`` = ``feature_unavailable``, 진짜 모듈의 409와 같은 사유)."""

    code = "feature_unavailable"


@dataclass
class StaticNotesReader:
    """공간 이름(None = 앱 공간) → 노트(최근 것부터). 표에 없는 공간은 ``SpaceUnavailableError``.

    Attributes:
        calls: 받은 ``(project, limit)``(확인용).
    """

    spaces: Mapping[str | None, Sequence[StaticNote]]
    calls: list[tuple[str | None, int | None]] = field(default_factory=list)

    def list_notes(
        self, project: str | None = None, *, limit: int | None = None
    ) -> list[StaticNote]:
        self.calls.append((project, limit))
        if project not in self.spaces:
            raise SpaceUnavailableError(project)
        notes = list(self.spaces[project])
        return notes if limit is None else notes[:limit]


class StaticNotesModule:
    """``example_notes.reader``를 주는 기능 모듈(테스트 호스트 조립용).

    Args:
        reader: 줄 읽기 구현.
        module_id: 모듈 id.
    """

    def __init__(
        self, reader: StaticNotesReader, *, module_id: str = STATIC_NOTES_MODULE_ID
    ) -> None:
        self.reader = reader
        self.descriptor = ModuleDescriptor(
            id=module_id,
            version="0.0.0",
            kind="feature",
            title="노트(대역)",
            provides=(NOTES_READER,),
        )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        ctx.provide(NOTES_READER, self.reader)
        return ModuleParts()

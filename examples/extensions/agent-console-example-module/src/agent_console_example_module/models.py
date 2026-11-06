"""노트·노트 틀·요청 본문 모델(이 모듈의 공개 API 모양).

바깥 모듈은 계약 패키지(``agent_console_contracts``)를 고치지 않는다. 자기 API 모양은 자기 패키지에
두고, 이벤트·이슈 코드는 자기 접두(``example_notes.``)를 쓴다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Note(BaseModel):
    """저장된 노트 하나."""

    id: str = Field(description="노트 id(서버가 만든다).")
    text: str = Field(description="본문.")
    tags: list[str] = Field(default_factory=list, description="태그.")
    template: str | None = Field(default=None, description="만들 때 쓴 노트 틀 id.")
    created_at: datetime = Field(description="적은 시각(UTC).")


class NoteCreate(BaseModel):
    """``POST <route>`` 본문. ``text``와 ``template`` 중 하나는 있어야 한다."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", description="본문. 비우면 노트 틀의 본문을 쓴다.")
    tags: list[str] = Field(default_factory=list, description="더할 태그.")
    template: str | None = Field(default=None, description="노트 틀 id(정의 종류 기여).")


class NoteTemplate(BaseModel):
    """노트 틀 정의 문서(워크스페이스 YAML, 기여한 정의 종류의 검증 모델).

    모르는 필드는 보존한다(손으로 고친 파일 왕복).
    """

    model_config = ConfigDict(extra="allow")

    kind: str
    id: str
    name: str = ""
    category: str = ""
    text: str = ""
    tags: list[str] = Field(default_factory=list)


__all__ = ["Note", "NoteCreate", "NoteTemplate"]

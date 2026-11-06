"""노트 서비스: 도메인 로직(HTTP·조립과 분리 — 서버 없이 단독으로 쓸 수 있다).

바깥 의존은 모두 ``NotesDeps``의 함수로 받는다(앱 엔진, 프로젝트 기록 공간, 정의 읽기, 사용자 설정,
시계, id 생성). 선택 의존이 없으면 그 동작에서만 ``FeatureUnavailableError``(호스트가 409)를 낸다.

>>> from agent_console_example_module import NotesModuleSettings, NotesService, memory_engine
>>> service = NotesService(NotesModuleSettings(max_notes=2), NotesDeps(app_engine=memory_engine))
>>> for word in ("하나", "둘", "셋"):
...     _ = service.add(NoteCreate(text=word))
>>> [n.text for n in service.list_notes()]
['셋', '둘']
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from typing import Any

from sqlalchemy import Engine

from agent_console_contracts import Issue
from agent_console_modkit import FeatureUnavailableError, utc_now
from agent_console_store import DefinitionStore, NotFound, RecordsSpaces

from .models import Note, NoteCreate, NoteTemplate
from .ports import DEFINITIONS_LOOKUP, RECORDS_SPACES
from .settings import (
    NotesModuleSettings,
    NotesUserSettings,
    parse_user_settings,
    section_of,
)
from .storage import NotesTable

MODULE_ID = "mod-example-notes"
"""모듈 id(설정 ``modules.options.<id>``·``modules.disabled``의 키)."""


class NoteNotFoundError(LookupError):
    """없는 노트(→ 404 ``not_found``)."""


class TemplateNotFoundError(LookupError):
    """없는 노트 틀(→ 404 ``not_found``)."""


class NoteRejectedError(ValueError):
    """노트를 받을 수 없다 — 너무 길거나 비었다(→ 422 ``validation_failed``)."""


@dataclass
class NotesDeps:
    """노트 서비스의 바깥 의존(모두 함수 — 부를 때 읽어 늦게 켜진 포트도 보인다).

    Attributes:
        app_engine: 앱 공간 엔진(계보가 올라간 것). 처음 쓸 때 한 번 부른다.
        records: 프로젝트 기록 공간(``records.spaces``). None을 돌려주면 프로젝트 노트가 꺼진다.
        templates: 정의 읽기(``definitions.lookup``). None을 돌려주면 노트 틀이 꺼진다.
        workspace_settings: 지금 워크스페이스 설정(사용자 설정 섹션). None이면 기본값.
        clock: 현재 시각.
        new_id: 노트 id 생성.
    """

    app_engine: Callable[[], Engine]
    records: Callable[[], RecordsSpaces | None] = lambda: None
    templates: Callable[[], DefinitionStore | None] = lambda: None
    workspace_settings: Callable[[], Any] = lambda: None
    clock: Callable[[], datetime] = utc_now
    new_id: Callable[[], str] = field(default=lambda: uuid.uuid4().hex)


class NotesService:
    """노트 적기·읽기(포트 ``example_notes.reader`` 구현).

    Args:
        options: 설치자 옵션.
        deps: 바깥 의존.
    """

    def __init__(self, options: NotesModuleSettings, deps: NotesDeps) -> None:
        self.options = options
        self.deps = deps
        self._app = cache(lambda: NotesTable(deps.app_engine()))

    # ------------------------------------------------------------ 설정
    def user_settings(self) -> tuple[NotesUserSettings, list[Issue]]:
        """지금 사용자 설정(형식이 틀리면 기본값)과 형식 문제."""
        section = self.options.user_section
        try:
            raw = section_of(self.deps.workspace_settings(), section)
        except Exception:  # 설정을 못 읽어도 노트는 동작한다
            raw = None
        return parse_user_settings(raw, section=section)

    def warnings(self) -> list[Issue]:
        """``server.warnings``: 사용자 설정 섹션 형식 문제."""
        return self.user_settings()[1]

    # ------------------------------------------------------------ 공간
    def _table(self, project: str | None, *, write: bool) -> NotesTable | None:
        if project is None:
            return self._app()
        spaces = self.deps.records()
        if spaces is None:
            raise FeatureUnavailableError(
                MODULE_ID,
                RECORDS_SPACES.name,
                "프로젝트 기록 연동이 꺼져 있어 프로젝트 노트를 쓸 수 없습니다",
            )
        handle = spaces.open(self.options.records_space_prefix + project)
        if write:
            return NotesTable(handle.writable_engine())
        engine = handle.read_engine()
        return None if engine is None else NotesTable(engine)

    # ------------------------------------------------------------ 읽기·쓰기
    def list_notes(self, project: str | None = None, *, limit: int | None = None) -> list[Note]:
        """노트 목록(사용자 설정 ``newest_first``·``list_limit``)."""
        prefs = self.user_settings()[0]
        table = self._table(project, write=False)
        if table is None:  # 프로젝트 기록 DB가 아직 없다 = 노트 없음
            return []
        count = prefs.list_limit if limit is None else max(1, min(limit, prefs.list_limit))
        return table.list(newest_first=prefs.newest_first, limit=count)

    def get(self, note_id: str, project: str | None = None) -> Note:
        """노트 하나.

        Raises:
            NoteNotFoundError: 없는 id.
        """
        table = self._table(project, write=False)
        found = table.get(note_id) if table is not None else None
        if found is None:
            raise NoteNotFoundError(f"노트가 없습니다: {note_id}")
        return found

    def _template(self, template_id: str) -> NoteTemplate:
        store = self.deps.templates()
        if store is None:
            raise FeatureUnavailableError(
                MODULE_ID, DEFINITIONS_LOOKUP.name, "정의 기능이 꺼져 있어 노트 틀을 쓸 수 없습니다"
            )
        try:
            stored = store.get(self.options.template_kind, template_id)
        except NotFound as exc:
            raise TemplateNotFoundError(f"노트 틀이 없습니다: {template_id}") from exc
        return stored.model(NoteTemplate)

    def add(self, body: NoteCreate, project: str | None = None) -> Note:
        """노트를 적는다. 틀을 주면 틀의 본문(본문이 비었을 때)과 태그를 쓴다.

        Raises:
            NoteRejectedError: 본문이 비었거나 ``max_text_chars``를 넘는다.
            TemplateNotFoundError: 없는 틀.
            FeatureUnavailableError: 틀·프로젝트를 줬는데 그 포트가 없다.
        """
        text, tags = body.text, list(body.tags)
        if body.template is not None:
            template = self._template(body.template)
            text = text or template.text
            tags = [*template.tags, *(t for t in tags if t not in template.tags)]
        if not text.strip():
            raise NoteRejectedError("노트 본문이 비었습니다")
        if len(text) > self.options.max_text_chars:
            raise NoteRejectedError(
                f"노트가 너무 깁니다({len(text)}자, 상한 {self.options.max_text_chars}자)"
            )
        note = Note(
            id=self.deps.new_id(),
            text=text,
            tags=tags,
            template=body.template,
            created_at=self.deps.clock(),
        )
        table = self._table(project, write=True)
        assert table is not None  # 쓰기 공간은 늘 있다(없으면 예외)
        table.add(note, keep=self.options.max_notes)
        return note


__all__ = [
    "MODULE_ID",
    "NoteNotFoundError",
    "NoteRejectedError",
    "NotesDeps",
    "NotesService",
    "TemplateNotFoundError",
]

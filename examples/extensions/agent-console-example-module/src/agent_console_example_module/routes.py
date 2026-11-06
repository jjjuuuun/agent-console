"""REST(경로는 설치자 옵션 ``route``, 기본 ``/example-notes``).

호스트가 API 접두(``/api/v1``)를 붙인다.

- ``GET <route>?project=&limit=`` → 노트 목록
- ``POST <route>?project=`` (본문 ``NoteCreate``) → 201 노트
- ``GET <route>/{note_id}?project=`` → 노트 하나(없으면 404 ``not_found``)

``project``가 있으면 그 프로젝트의 기록 DB, 없으면 앱 DB. 변경 요청의 토큰 검사·Host 검사는 호스트가
한다(모듈은 보안 코드를 두지 않는다).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from .models import Note, NoteCreate
from .service import NotesService

ProjectQuery = Annotated[
    str | None, Query(description="프로젝트 id. 비우면 앱 공간.", pattern=r"^[A-Za-z0-9_.\-]+$")
]


def build_router(service: NotesService, route: str) -> APIRouter:
    """노트 라우터를 만든다(서비스·경로 주입)."""
    router = APIRouter(prefix=route, tags=["example-notes"])

    @router.get("", response_model=list[Note])
    def list_notes(
        project: ProjectQuery = None,
        limit: Annotated[int | None, Query(ge=1)] = None,
    ) -> list[Note]:
        return service.list_notes(project, limit=limit)

    @router.post("", response_model=Note, status_code=201)
    def add_note(body: NoteCreate, project: ProjectQuery = None) -> Note:
        return service.add(body, project)

    @router.get("/{note_id}", response_model=Note)
    def get_note(note_id: str, project: ProjectQuery = None) -> Note:
        return service.get(note_id, project)

    return router


__all__ = ["build_router"]

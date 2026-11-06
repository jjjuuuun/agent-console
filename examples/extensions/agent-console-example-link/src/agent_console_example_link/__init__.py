"""agent-console-example-link: 연동 모듈 예제 ``link-example-notes-runs``.

실행 범위(X26 ``runs.scopes``) 항목이 Run마다 에이전트 도구 공급자(X30)를 넣어, 노트 리소스를 붙인
에이전트에게 노트 읽기 도구와 지침을 준다.

공개 API:
    - ``module`` / ``NotesRunsLink`` / ``MODULE_ID``: 연동 모듈.
    - ``NotesRunScope``(X26 항목) / ``NotesToolProvider``(X30 공급자) / ``merge_access`` /
      ``render_notes``.
    - ``NotesResourceType`` / ``NotesAccess`` / ``load_resource_type`` / ``notes_slot`` /
      ``register``: 리소스 종류 ``example-notes``.
    - ``NotesRunsSettings`` / ``NotesToolText`` / ``load_defaults``: 설치자 설정·문구 데이터.
    - ``NOTES_READER`` / ``RUNS_READER`` / ``RUN_SCOPES`` / ``NotesReaderLike`` / ``NoteLike``:
      포트.
    - 테스트 대역은 ``agent_console_example_link.testing``.
"""

from .module import MODULE_ID, NotesRunsLink, module
from .ports import NOTES_READER, RUN_SCOPES, RUNS_READER, NoteLike, NotesReaderLike
from .provider import ACCESS_INVALID, NotesToolProvider, merge_access, render_notes
from .resource_type import (
    NotesAccess,
    NotesResourceType,
    load_resource_type,
    notes_slot,
    register,
)
from .scope import NotesRunScope, RunScopeResult
from .settings import NotesRunsSettings, NotesToolText, load_defaults

__all__ = [
    "ACCESS_INVALID",
    "MODULE_ID",
    "NOTES_READER",
    "RUNS_READER",
    "RUN_SCOPES",
    "NoteLike",
    "NotesAccess",
    "NotesReaderLike",
    "NotesResourceType",
    "NotesRunScope",
    "NotesRunsLink",
    "NotesRunsSettings",
    "NotesToolProvider",
    "NotesToolText",
    "RunScopeResult",
    "load_defaults",
    "load_resource_type",
    "merge_access",
    "module",
    "notes_slot",
    "register",
    "render_notes",
]

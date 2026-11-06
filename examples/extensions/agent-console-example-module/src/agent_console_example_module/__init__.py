"""agent-console-example-module: 서버 모듈 예제 ``mod-example-notes``(짧은 노트 적기·읽기).

공개 API:
    - ``module`` / ``NotesModule``: 서버 모듈(entry point ``agent_console.server_modules``).
    - ``NotesService`` / ``NotesDeps``: 도메인 로직(서버 없이 단독으로 쓴다).
    - ``NotesModuleSettings``(설치자 옵션) / ``NotesUserSettings``(사용자 설정 섹션) /
      ``SETTINGS_COMPAT``(명령행 옵션 ``--example-notes-max``).
    - ``Note`` / ``NoteCreate`` / ``NoteTemplate``: API·정의 문서 모양.
    - ``BRANCH``: 마이그레이션 계보(``scopes=("app", "project")``).
    - ``memory_engine``: 계보를 올린 메모리 DB.
    - ``NOTES_READER`` / ``NotesReader``: 이 모듈이 제공하는 포트와 모양.
    - ``main``: 단독 실행(``python -m agent_console_example_module``).
"""

from .models import Note, NoteCreate, NoteTemplate
from .module import STORAGE_MEMORY, NotesModule, module, template_kind
from .ports import NOTES_READER, NotesReader
from .service import (
    MODULE_ID,
    NoteNotFoundError,
    NoteRejectedError,
    NotesDeps,
    NotesService,
    TemplateNotFoundError,
)
from .settings import (
    SETTINGS_COMPAT,
    SETTINGS_INVALID,
    NotesModuleSettings,
    NotesUserSettings,
    parse_user_settings,
)
from .standalone import local_settings_module, main
from .storage import BRANCH, NotesTable, memory_engine

__all__ = [
    "BRANCH",
    "MODULE_ID",
    "NOTES_READER",
    "SETTINGS_COMPAT",
    "SETTINGS_INVALID",
    "STORAGE_MEMORY",
    "Note",
    "NoteCreate",
    "NoteNotFoundError",
    "NoteRejectedError",
    "NoteTemplate",
    "NotesDeps",
    "NotesModule",
    "NotesModuleSettings",
    "NotesReader",
    "NotesService",
    "NotesTable",
    "NotesUserSettings",
    "TemplateNotFoundError",
    "local_settings_module",
    "main",
    "memory_engine",
    "module",
    "parse_user_settings",
    "template_kind",
]

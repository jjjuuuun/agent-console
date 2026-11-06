"""agent-console-link-projects-memory: 프로젝트 폴더 메모리 DB 연동 모듈(design §PI.4.3, R15.12).

프로젝트 폴더의 ``<구성 폴더>/memory.sqlite3``를 열어 메모리 모듈의 공간(``memory.spaces``)으로
준다. 프로젝트와 메모리 모듈은 서로를 모르고, 이 연동이 둘을 잇는다. 저장소 구현은
``ac-memory`` SQLite 그대로이고 계보는 켜진 모듈이 선언한 것
(``ModuleContext.active_migrations``)을 올린다.

공개 API:
    - ``module``(``ProjectsMemoryLink``): entry point ``agent_console.server_modules``의
      ``link-projects-memory``. 설정 ``ProjectsMemorySettings``.
    - ``ProjectMemoryPool``: HTTP 없이 쓰는 부품 - ``open(space) -> ProjectMemorySpace``
      (``store``·``context``·``path``)·``close``·``close_all``. 열린 저장소 캐시(상한·유휴 닫기).
    - ``migrate_memory_db(path, branches)``·``folder_id(space)``·``MemoryDbUnavailable``.
    - 포트(``ports``): 받음 ``PROJECTS_SPACES``(필수), 제공 ``MEMORY_SPACES``.
    - ``testing``: ``FolderSpaces``·``folder_spaces_module``(단독 실행·테스트).
"""

from __future__ import annotations

from .module import MODULE_ID, ProjectsMemoryLink, module, options_of
from .pool import (
    MemoryDbUnavailable,
    PoolOptions,
    ProjectMemoryPool,
    ProjectMemorySpace,
    folder_id,
    migrate_memory_db,
)
from .ports import MEMORY_SPACES, PROJECTS_SPACES, ProjectSpaces, SpaceLike
from .settings import ProjectsMemorySettings

__all__ = [
    "MEMORY_SPACES",
    "MODULE_ID",
    "PROJECTS_SPACES",
    "MemoryDbUnavailable",
    "PoolOptions",
    "ProjectMemoryPool",
    "ProjectMemorySpace",
    "ProjectSpaces",
    "ProjectsMemoryLink",
    "ProjectsMemorySettings",
    "SpaceLike",
    "folder_id",
    "migrate_memory_db",
    "module",
    "options_of",
]

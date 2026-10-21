"""agent-console-link-projects-runs: 프로젝트·실행 연동 모듈(design §UX-P.5·§5.2R.6, R15.4).

실행의 ``project_id``(불투명 문자열)로 프로젝트를 찾아 설정 층(작업 폴더·설정)을 넣는다. 실행·
프로젝트 모듈은 서로를 모르고, 이 연동이 둘을 잇는다.

공개 API:
    - ``module``(``ProjectsRunsLink``): entry point ``agent_console.server_modules``의
      ``link-projects-runs``. 설정 ``ProjectsRunsSettings``(층 id·이름, 없는 프로젝트 문구).
    - ``ProjectScope``: HTTP 없이 쓰는 부품 — ``layers(project_id)``·``scope_run``(``runs.scopes``
      모양)·``scope_layers``(``settings.scope_layers`` 모양). 결과 ``ScopeLayers``·
      ``RunScopeResult``.
    - 포트(``ports``): 받음 ``PROJECTS_LOOKUP``(필수), 제공 ``RUN_SCOPES``·``SCOPE_LAYERS``.
    - ``testing``: ``MemoryProjects``·``memory_projects_module``(단독 실행·테스트).
"""

from __future__ import annotations

from .module import MODULE_ID, ProjectsRunsLink, module
from .ports import PROJECTS_LOOKUP, RUN_SCOPES, SCOPE_LAYERS, ProjectLookup
from .scope import (
    DEFAULT_LAYER_ID,
    DEFAULT_LAYER_LABEL,
    DEFAULT_UNKNOWN_MESSAGE,
    ProjectScope,
    RunScopeResult,
    ScopeLayers,
)
from .settings import ProjectsRunsSettings

__all__ = [
    "DEFAULT_LAYER_ID",
    "DEFAULT_LAYER_LABEL",
    "DEFAULT_UNKNOWN_MESSAGE",
    "MODULE_ID",
    "PROJECTS_LOOKUP",
    "RUN_SCOPES",
    "SCOPE_LAYERS",
    "ProjectLookup",
    "ProjectScope",
    "ProjectsRunsLink",
    "ProjectsRunsSettings",
    "RunScopeResult",
    "ScopeLayers",
    "module",
]

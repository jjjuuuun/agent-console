"""agent-console-mod-projects: 프로젝트 기능 모듈(design §UX-P.5, 모듈 id ``mod-projects``).

프로젝트(사용자가 만든 이름 붙은 작업 단위)를 워크스페이스 ``projects/<id>.yaml``에 저장하고,
정의 범위(공용·프로젝트 전용) 검사·옮기기·삭제 계획을 REST와 포트로 낸다. 규칙 계산은 순수
패키지 ``agent-console-projects``가 한다.

공개 API:
    - ``module``(``ProjectsModule``), ``MODULE_ID``, ``WEB_ROLES``
    - 포트: ``PROJECTS_LOOKUP``(제공)·``PROJECT_FOLDERS``(제공, ``projects.folders`` — 등록된
      프로젝트 폴더 현재·전체, 5.7R.30 후속)·``DEFINITION_CHECKS``(제공, multi)·
      ``DEFINITIONS_LOOKUP``·
      ``DEFINITIONS_STORE``·``DEFINITIONS_REFERENCES``(multi)·토픽 ``DEFINITIONS_SAVED``,
      프로토콜 ``ProjectLookup``·``DefinitionReader``·``DefinitionWriter``
    - 서버 없이 쓰는 부품: ``ProjectRepository``·``project_kind``·``ProjectService``·
      ``DefinitionSnapshot``·``combine_references``·``read_definitions``
    - 설정 ``ProjectModuleSettings``(``SETTINGS_COMPAT``: 앱 작업 폴더 기본값 = 실행 모듈
      작업 폴더)
"""

from __future__ import annotations

from .definitions import DefinitionSnapshot, combine_references, read_definitions
from .module import MODULE_ID, WEB_ROLES, ProjectScopeCheck, ProjectsModule, module
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    DEFINITIONS_REFERENCES,
    DEFINITIONS_SAVED,
    DEFINITIONS_STORE,
    PROJECT_FOLDERS,
    PROJECTS_LOOKUP,
    DefinitionCheck,
    DefinitionReader,
    DefinitionWriter,
    ProjectLookup,
)
from .repository import PROJECT_KIND_NAME, ProjectRepository, apply_update, project_kind
from .service import (
    CODE_DEFINITIONS_UNAVAILABLE,
    DefinitionsUnavailableError,
    ProjectService,
)
from .settings import SETTINGS_COMPAT, ProjectModuleSettings

__all__ = [
    "CODE_DEFINITIONS_UNAVAILABLE",
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_REFERENCES",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "MODULE_ID",
    "PROJECTS_LOOKUP",
    "PROJECT_FOLDERS",
    "PROJECT_KIND_NAME",
    "SETTINGS_COMPAT",
    "WEB_ROLES",
    "DefinitionCheck",
    "DefinitionReader",
    "DefinitionSnapshot",
    "DefinitionWriter",
    "DefinitionsUnavailableError",
    "ProjectLookup",
    "ProjectModuleSettings",
    "ProjectRepository",
    "ProjectScopeCheck",
    "ProjectService",
    "ProjectsModule",
    "apply_update",
    "combine_references",
    "module",
    "project_kind",
    "read_definitions",
]

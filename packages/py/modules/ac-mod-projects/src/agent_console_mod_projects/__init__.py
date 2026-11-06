"""agent-console-mod-projects: 프로젝트 기능 모듈(design §PI, 모듈 id ``mod-projects``).

프로젝트 = 로컬 폴더 + 그 폴더 안 구성 사본(``<folder>/.agent-console/``). 앱 등록부
(``<workspace>/projects/<id>.yaml``)에는 폴더·보관만, 이름·설명·프로젝트 층은 폴더
매니페스트에 둔다.
폴더 확인·찾아보기·네이티브 선택 창, 공간 사이 복사, 프로젝트 공간 포트를 낸다. 규칙 계산은 순수
패키지(``ac-projects``·``ac-local-folders``·``ac-project-space``)가 한다.

공개 API:
    - ``module``(``ProjectsModule``), ``MODULE_ID``, ``WEB_ROLES``
    - 포트: 제공 ``PROJECTS_LOOKUP``·``PROJECT_FOLDERS``·``PROJECTS_SPACES``·``DEFINITIONS_SPACES``,
      선택 ``DEFINITIONS_LOOKUP``·``DEFINITIONS_STORE``·``DEFINITIONS_REFERENCES``·
      ``DEFINITIONS_REWRITERS``·``RECORDS_SPACES``·``SECRET_RULES``, 토픽 ``DEFINITIONS_SAVED``
    - 서버 없이 쓰는 부품: ``ProjectRepository``·``project_kind``·``ProjectManager``·
      ``ProjectSpaceCache``·``FolderService``·``FolderPicker``·``CopyService``
    - 확장 지점: 코드 선택 창 제공자 ``FolderDialogProvider``(entry point
      ``agent_console.folder_dialogs``)
    - (deprecated) 옛 범위 정리 ``ScopeService``·``DefinitionSnapshot``
    - 설정 ``ProjectModuleSettings``·``FolderDialogSettings``(``SETTINGS_COMPAT``)
"""

from __future__ import annotations

from .copying import CopyService, space_index
from .definitions import DefinitionSnapshot, combine_references, read_definitions
from .errors import ProjectError
from .folders import (
    FOLDER_DIALOGS_GROUP,
    FolderDialogProvider,
    FolderPicker,
    FolderService,
    load_dialog_providers,
)
from .module import MODULE_ID, WEB_ROLES, ProjectsModule, library_kinds, module
from .ports import (
    DEFINITIONS_LOOKUP,
    DEFINITIONS_REFERENCES,
    DEFINITIONS_REWRITERS,
    DEFINITIONS_SAVED,
    DEFINITIONS_SPACES,
    DEFINITIONS_STORE,
    PROJECT_FOLDERS,
    PROJECTS_LOOKUP,
    PROJECTS_SPACES,
    RECORDS_SPACES,
    SECRET_RULES,
    DefinitionReader,
    DefinitionSpaces,
    DefinitionWriter,
    ProjectLookup,
    ProjectSpaces,
)
from .projects import ProjectManager
from .repository import PROJECT_KIND_NAME, ProjectRepository, project_kind
from .service import CODE_DEFINITIONS_UNAVAILABLE, DefinitionsUnavailableError, ScopeService
from .settings import SETTINGS_COMPAT, FolderDialogSettings, ProjectModuleSettings
from .spaces import DefinitionSpacesView, ProjectSpaceCache

__all__ = [
    "CODE_DEFINITIONS_UNAVAILABLE",
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_REFERENCES",
    "DEFINITIONS_REWRITERS",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_SPACES",
    "DEFINITIONS_STORE",
    "FOLDER_DIALOGS_GROUP",
    "MODULE_ID",
    "PROJECTS_LOOKUP",
    "PROJECTS_SPACES",
    "PROJECT_FOLDERS",
    "PROJECT_KIND_NAME",
    "RECORDS_SPACES",
    "SECRET_RULES",
    "SETTINGS_COMPAT",
    "WEB_ROLES",
    "CopyService",
    "DefinitionReader",
    "DefinitionSnapshot",
    "DefinitionSpaces",
    "DefinitionSpacesView",
    "DefinitionWriter",
    "DefinitionsUnavailableError",
    "FolderDialogProvider",
    "FolderDialogSettings",
    "FolderPicker",
    "FolderService",
    "ProjectError",
    "ProjectLookup",
    "ProjectManager",
    "ProjectModuleSettings",
    "ProjectRepository",
    "ProjectSpaceCache",
    "ProjectSpaces",
    "ProjectsModule",
    "ScopeService",
    "combine_references",
    "library_kinds",
    "load_dialog_providers",
    "module",
    "project_kind",
    "read_definitions",
    "space_index",
]

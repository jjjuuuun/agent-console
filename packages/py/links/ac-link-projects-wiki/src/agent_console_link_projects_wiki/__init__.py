"""agent-console-link-projects-wiki: 프로젝트 폴더 위키 공간 연동 모듈.

설계: design §7R.3·§7R.4·§7R.13(R15.2·R15.4·R15.6·R15.11, R9.1). 프로젝트 폴더의 정의 저장소
(``<구성 폴더>/``)와 페이지 폴더(``<구성 폴더>/<pages_dir>/``)를 위키 모듈의 공간
(``wiki.spaces``)으로 준다. 프로젝트와 위키 모듈은 서로를 모르고, 이 연동이 둘을 잇는다.
페이지 폴더의 경로 지킴은 ``ac-projects`` ``FolderGuard``(§PI.5, ``link-projects-sdd``와 같은
규칙)다.

공개 API:
    - ``module``(``ProjectsWikiLink``): entry point ``agent_console.server_modules``의
      ``link-projects-wiki``. 설정 ``ProjectsWikiSettings``(``pages_dir``는 ``mod-wiki.pages_dir``을
      ``SeedSetting``으로 이어받음).
    - ``ProjectWikiSpaces``: HTTP 없이 쓰는 부품 - ``open(space) -> ProjectWikiSpace``
      (``store``·``folder``·``config_writable``·``config_dir``·``pages_dir``·``pages_root``·
      ``index_dir``).
    - ``UnsafePagesRoot``(422 ``folders.invalid_path``)·``UnsafeSpaceRoot``·``config_dir_of``.
    - 포트(``ports``): 받음 ``PROJECTS_SPACES``(필수), 제공 ``WIKI_SPACES``.
    - ``testing``: ``FolderSpaces``·``folder_spaces_module``(단독 실행·테스트).
"""

from __future__ import annotations

from .module import MODULE_ID, ProjectsWikiLink, module
from .ports import PROJECTS_SPACES, WIKI_SPACES, ProjectSpaces, SpaceLike
from .settings import SETTINGS_COMPAT, ProjectsWikiSettings, check_relative_dir
from .spaces import (
    ProjectWikiSpace,
    ProjectWikiSpaces,
    UnsafePagesRoot,
    UnsafeSpaceRoot,
    config_dir_of,
)

__all__ = [
    "MODULE_ID",
    "PROJECTS_SPACES",
    "SETTINGS_COMPAT",
    "WIKI_SPACES",
    "ProjectSpaces",
    "ProjectWikiSpace",
    "ProjectWikiSpaces",
    "ProjectsWikiLink",
    "ProjectsWikiSettings",
    "SpaceLike",
    "UnsafePagesRoot",
    "UnsafeSpaceRoot",
    "check_relative_dir",
    "config_dir_of",
    "module",
]

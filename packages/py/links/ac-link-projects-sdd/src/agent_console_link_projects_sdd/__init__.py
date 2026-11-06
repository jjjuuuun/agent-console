"""agent-console-link-projects-sdd: 프로젝트 폴더 스펙 공간 연동 모듈.

설계: design §6R.3·§6R.4(R15.2·R15.6). 프로젝트 폴더의 정의 저장소(``<구성 폴더>/``)를 SDD 모듈의
스펙 공간(``sdd.spaces``)으로 준다. 프로젝트와 SDD 모듈은 서로를 모르고, 이 연동이 둘을 잇는다.
가져오기·내보내기용 파일 접근은 그 폴더 안만이고 앱 구성 폴더는 손대지 않는다(§PI.5).

공개 API:
    - ``module``(``ProjectsSddLink``): entry point ``agent_console.server_modules``의
      ``link-projects-sdd``. 설정 ``ProjectsSddSettings``.
    - ``ProjectSddSpaces``: HTTP 없이 쓰는 부품 - ``open(space) -> ProjectSddSpace``
      (``store``·``folder``·``config_writable``·``files``·``config_dir``).
    - ``ProjectSpecFiles``: 폴더 안만 읽고 쓰는 ``SpecFiles``(예약 경로·쓰기 불가·링크 거부).
    - ``config_dir_of``·``normalize_reserved``·``UnsafeSpaceRoot``.
    - 포트(``ports``): 받음 ``PROJECTS_SPACES``(필수), 제공 ``SDD_SPACES``.
    - ``testing``: ``FolderSpaces``·``folder_spaces_module``(단독 실행·테스트).
"""

from __future__ import annotations

from .files import ProjectSpecFiles, normalize_reserved
from .module import MODULE_ID, ProjectsSddLink, module
from .ports import PROJECTS_SPACES, SDD_SPACES, ProjectSpaces, SpaceLike
from .settings import ProjectsSddSettings
from .spaces import ProjectSddSpace, ProjectSddSpaces, UnsafeSpaceRoot, config_dir_of

__all__ = [
    "MODULE_ID",
    "PROJECTS_SPACES",
    "SDD_SPACES",
    "ProjectSddSpace",
    "ProjectSddSpaces",
    "ProjectSpaces",
    "ProjectSpecFiles",
    "ProjectsSddLink",
    "ProjectsSddSettings",
    "SpaceLike",
    "UnsafeSpaceRoot",
    "config_dir_of",
    "module",
    "normalize_reserved",
]

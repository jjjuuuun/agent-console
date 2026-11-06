"""agent-console-link-projects-records: 프로젝트 폴더 기록 DB 연동 모듈(design §PI.4.6, R15.11).

프로젝트 폴더의 ``<구성 폴더>/records.sqlite3``를 열어 실행·대화·사본 버전 모듈에 준다. 프로젝트와
기록 모듈은 서로를 모르고, 이 연동이 둘을 잇는다. DB 열기·계보 적용은 ``agent_console_store``의
``open_records_db``가 한다.

공개 API:
    - ``module``(``ProjectsRecordsLink``): entry point ``agent_console.server_modules``의
      ``link-projects-records``. 설정 ``ProjectsRecordsSettings``.
    - ``RecordsSpacePool``: HTTP 없이 쓰는 부품 - ``open(space)``·``state(space)``·``close(space)``
      (``records.spaces`` 모양). 열린 핸들 캐시(상한·유휴 닫기)와 대기 파일 다시 쓰기.
    - 세션 기록 보관(5.7R.33y3, X38): ``ProjectSessionArchive``(``records.sessions`` — ``state``·
      ``prepare``·``archive``), ``SessionArchiver``(``runs.event`` → 노드가 끝나면 보관),
      설정 ``SessionArchiveSettings``(``session_archive{enabled, dir}``).
    - ``load_host_id``: 앱 id 파일. ``RecordsSpool``: 쓰기 실패 대기 파일.
    - 포트(``ports``): 받음 ``PROJECTS_SPACES``(필수), 제공 ``RECORDS_SPACES``.
    - ``testing``: ``FolderSpaces``·``folder_spaces_module``(단독 실행·테스트).
"""

from __future__ import annotations

from .host_id import HOST_ID_FILE, load_host_id, new_host_id
from .module import MODULE_ID, ProjectsRecordsLink, module
from .pool import PoolOptions, RecordsSpacePool, SpaceRecords, UnknownSpace
from .ports import PROJECTS_SPACES, RECORDS_SPACES, ProjectSpaces, SpaceLike
from .replay import Applier, default_appliers, storage_apply
from .sessions import (
    ARCHIVE_FAILED_CODE,
    ProjectSessionArchive,
    SessionArchiver,
    SessionArchiveSettings,
)
from .settings import ProjectsRecordsSettings
from .spool import DrainResult, RecordsSpool

__all__ = [
    "ARCHIVE_FAILED_CODE",
    "HOST_ID_FILE",
    "MODULE_ID",
    "PROJECTS_SPACES",
    "RECORDS_SPACES",
    "Applier",
    "DrainResult",
    "PoolOptions",
    "ProjectSessionArchive",
    "ProjectSpaces",
    "ProjectsRecordsLink",
    "ProjectsRecordsSettings",
    "RecordsSpacePool",
    "RecordsSpool",
    "SessionArchiveSettings",
    "SessionArchiver",
    "SpaceLike",
    "SpaceRecords",
    "UnknownSpace",
    "default_appliers",
    "load_host_id",
    "module",
    "new_host_id",
    "storage_apply",
]

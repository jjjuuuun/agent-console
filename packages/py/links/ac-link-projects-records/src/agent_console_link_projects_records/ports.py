"""link-projects-records의 포트(이름 = 포트, design §PI.4.6.3).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다. 기록 DB 핸들의
모양(``RecordsHandle``·``RecordsSpaces``)과 포트 이름(``RECORDS_SPACES_PORT``)은
``agent_console_store``에 있다(소비 모듈이 이 연동 모듈에 의존하지 않게).

받음:

- 필수 ``projects.spaces``: 프로젝트 공간 열기(``ProjectSpaces`` — ``open(project_id)``).
  ``mod-projects``가 준다. 없으면 이 연동은 꺼지고, 앱 조립은 기록 쓰기를
  ``link_disabled``로 막는다(앱 DB에 대신 쓰지 않음).

제공:

- ``records.spaces``: 공간 이름(``project:<등록 id>``) → 그 폴더의 기록 DB 핸들(``RecordsSpaces``).
  ``mod-runs``·``mod-chat``·``mod-definitions``가 **선택**으로 받는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from agent_console_modkit import PortKey
from agent_console_store import RECORDS_SPACES_PORT, RecordsSpaces


@runtime_checkable
class SpaceLike(Protocol):
    """프로젝트 공간에서 이 연동이 쓰는 부분(``project_space.ProjectSpace``가 만족한다)."""

    @property
    def folder(self) -> Path:
        """프로젝트 폴더."""
        ...

    @property
    def records_db_path(self) -> Path:
        """기록 DB 파일 경로(파일은 만들지 않았다)."""
        ...

    @property
    def state_dir(self) -> Path:
        """폴더용 캐시·임시 폴더(백업이 여기 ``backups/``에 쌓인다)."""
        ...

    @property
    def config_writable(self) -> bool:
        """구성 폴더에 쓸 수 있나."""
        ...


@runtime_checkable
class ProjectSpaces(Protocol):
    """``projects.spaces`` 모양의 쓰는 부분."""

    def open(self, project_id: str) -> SpaceLike:
        """등록 id의 공간.

        Raises:
            LookupError: 모르는 프로젝트.
            agent_console_project_space.FolderMissing: 폴더가 없다.
            agent_console_project_space.SpaceError: 그 밖에 열 수 없다(링크 구성 폴더 등).
        """
        ...


PROJECTS_SPACES: PortKey[ProjectSpaces] = PortKey("projects.spaces", "프로젝트 공간 열기")
RECORDS_SPACES: PortKey[RecordsSpaces] = PortKey(
    RECORDS_SPACES_PORT, "공간 이름 → 프로젝트 기록 DB 핸들"
)

__all__ = ["PROJECTS_SPACES", "RECORDS_SPACES", "ProjectSpaces", "SpaceLike"]

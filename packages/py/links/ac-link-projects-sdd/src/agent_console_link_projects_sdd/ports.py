"""link-projects-sdd의 포트(이름 = 포트, design §6R.3·§6R.4·§PI.10).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다. 아래 프로토콜은
이 연동이 **받는** 쪽의 모양이다(제공 모듈을 import하지 않는다).

받음:

- 필수 ``projects.spaces``: 프로젝트 공간 열기(``ProjectSpaces.open(project_id)``).
  ``mod-projects``가 준다. 없으면 이 연동은 꺼지고, ``mod-sdd``는 ``?project=`` 요청에 409
  ``sdd.spaces_unavailable``을 낸다(앱 workspace의 단독 루트에 대신 만들지 않는다).

제공:

- ``sdd.spaces``: 공간 이름(프로젝트 등록 id, REST ``?project=``와 같은 값) → 그 폴더의
  ``ProjectSddSpace``(``store``·``folder``·``config_writable``·``files``·``config_dir``).
  ``mod-sdd``가 **선택**으로 받는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agent_console_modkit import PortKey
from agent_console_store import DefinitionStore


@runtime_checkable
class SpaceLike(Protocol):
    """프로젝트 공간에서 이 연동이 쓰는 부분(``project_space.ProjectSpace``가 만족한다)."""

    @property
    def folder(self) -> Path:
        """프로젝트 폴더(절대 경로)."""
        ...

    @property
    def root(self) -> Path:
        """구성 폴더(``<folder>/<config_dir>``) = 정의 저장소 root."""
        ...

    @property
    def definitions(self) -> DefinitionStore:
        """그 공간의 정의 저장소(쓰기는 공간의 읽기 전용·비밀 검사를 지난다)."""
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
            agent_console_project_space.SpaceError: 그 밖에 열 수 없다.
        """
        ...


PROJECTS_SPACES: PortKey[ProjectSpaces] = PortKey("projects.spaces", "프로젝트 공간 열기")
SDD_SPACES: PortKey[Any] = PortKey("sdd.spaces", "공간 이름 → 스펙 저장 공간")

__all__ = ["PROJECTS_SPACES", "SDD_SPACES", "ProjectSpaces", "SpaceLike"]

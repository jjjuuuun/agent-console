# ruff: noqa: N818
"""프로젝트 공간 → SDD 공간(``sdd.spaces`` 구현, design §6R.3·§6R.4).

공간 이름(등록 id)을 ``projects.spaces``로 열고 ``mod-sdd``가 쓰는 모양(``ProjectSddSpace``)으로
바꾼다. 스펙·문서 틀은 그 폴더의 정의 저장소(``<folder>/<config_dir>/``)에 들어가므로 폴더를 다른 앱
(다른 workspace)에 등록해도 스펙·규칙이 그대로다.

- 저장소는 프로젝트 공간의 것 그대로다(읽기 전용·평문 비밀 검사·버전 기록소가 공간 규칙을 따른다).
- ``files``는 그 폴더 안만 읽고 쓰는 ``ProjectSpecFiles``다. 앱 구성 폴더는 예약이다.
- 열 때 폴더 매니페스트를 읽어 깨졌으면 ``ManifestInvalid``(409 ``project.manifest_invalid``)를
  올린다(매니페스트가 없으면 통과 — 아직 등록 전 공간도 열 수 있다). 폴더 없음은 제공자의
  ``FolderMissing``(409 ``project.folder_missing``) 그대로, 모르는 프로젝트는 ``LookupError``.
- 아무것도 만들거나 쓰지 않는다. 캐시는 제공자(``mod-projects`` 공간 캐시)가 맡는다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from agent_console_project_space import ProjectSpace, SpaceError, read_manifest
from agent_console_projects import normalize_reserved, relative_inside
from agent_console_sdd import SpecFiles
from agent_console_store import DefinitionStore

from .files import ProjectSpecFiles
from .ports import ProjectSpaces, SpaceLike

__all__ = ["ProjectSddSpace", "ProjectSddSpaces", "UnsafeSpaceRoot", "config_dir_of"]


class UnsafeSpaceRoot(SpaceError):
    """공간의 구성 폴더가 프로젝트 폴더 안이 아니다(제공자 설정 오류) -> ``internal``.

    ``SpaceError``의 기본 ``code``(``internal``)를 그대로 쓴다. 폴더 밖 저장소로 스펙을 쓰지 않는다.
    """


@dataclass(frozen=True)
class ProjectSddSpace:
    """열린 SDD 공간 하나(``mod-sdd`` ``SddSpace`` 모양).

    Attributes:
        store: 그 폴더의 정의 저장소(프로젝트 공간 것 그대로).
        folder: 프로젝트 폴더(절대 경로 — ``mod-sdd``는 응답·로그에 싣지 않는다).
        config_writable: 구성 폴더에 쓸 수 있나(거짓이면 ``SddInfo.writable=false``).
        files: 그 폴더 안만 읽고 쓰는 파일 접근.
        config_dir: 저장소 폴더(폴더 기준 POSIX 상대 경로, 예: ``.agent-console``).
            ``SddInfo.spec_root`` = ``<config_dir>/<mod-sdd spec_dir>``.
    """

    store: DefinitionStore
    folder: Path
    config_writable: bool
    files: SpecFiles
    config_dir: str


def config_dir_of(space: SpaceLike) -> str:
    """공간 구성 폴더의 폴더 기준 상대 경로(POSIX).

    >>> from types import SimpleNamespace
    >>> config_dir_of(SimpleNamespace(folder=Path("/w/app"), root=Path("/w/app/.cfg/x")))
    '.cfg/x'

    Raises:
        UnsafeSpaceRoot: 구성 폴더가 프로젝트 폴더와 같거나 밖이다.
    """
    try:
        return relative_inside(space.root, space.folder)
    except ValueError as exc:
        raise UnsafeSpaceRoot(f"project config folder: {exc}") from None


def _check_manifest(space: SpaceLike) -> None:
    if isinstance(space, ProjectSpace):
        read_manifest(space)  # 깨졌으면 ManifestInvalid(409)


class ProjectSddSpaces:
    """``sdd.spaces`` 구현: 공간 이름(등록 id) → ``ProjectSddSpace``.

    Args:
        spaces: 지금 ``projects.spaces``(없으면 None — 모든 이름이 ``LookupError``).
        reserved: 구성 폴더 말고도 가져오기·내보내기에서 손대지 않을 폴더(폴더 기준 상대 경로).
        check_manifest: 공간 → 매니페스트 검사(주입, 기본 ``project.yaml`` 읽기).

    >>> import tempfile
    >>> from agent_console_link_projects_sdd.testing import FolderSpaces
    >>> folder = Path(tempfile.mkdtemp())
    >>> space = ProjectSddSpaces(lambda: FolderSpaces({"a": folder})).open("a")
    >>> space.config_dir, space.config_writable
    ('.agent-console', True)
    """

    def __init__(
        self,
        spaces: Callable[[], ProjectSpaces | None],
        *,
        reserved: Iterable[str] = (),
        check_manifest: Callable[[SpaceLike], None] = _check_manifest,
    ) -> None:
        self._spaces = spaces
        self._reserved = normalize_reserved(reserved)
        self._check_manifest = check_manifest

    def open(self, space: str) -> ProjectSddSpace:
        """그 프로젝트의 SDD 공간. 아무것도 만들거나 쓰지 않는다.

        Raises:
            LookupError: 모르는 프로젝트(또는 ``projects.spaces`` 없음).
            agent_console_project_space.FolderMissing: 폴더가 없다(409).
            agent_console_project_space.ManifestInvalid: 매니페스트가 깨졌다(409).
            agent_console_project_space.SpaceError: 그 밖에 열 수 없다(``code``).
        """
        provider = self._spaces()
        if provider is None:
            raise LookupError(space)
        found = provider.open(space)
        self._check_manifest(found)
        config_dir = config_dir_of(found)
        writable = bool(found.config_writable)
        files = ProjectSpecFiles(
            found.folder, reserved=(config_dir, *self._reserved), writable=writable
        )
        return ProjectSddSpace(
            store=found.definitions,
            folder=Path(found.folder),
            config_writable=writable,
            files=files,
            config_dir=config_dir,
        )

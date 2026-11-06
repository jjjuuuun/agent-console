"""등록 프로젝트별 내보내기(5.7R.33k, design §PI.5 내보내기 행).

선택 포트 ``projects.folders``가 있으면:

- 폴더 쓰기 대상(루트) = 등록 프로젝트 폴더(루트 id = 등록 id). 설치자 ``roots``는 쓰지 않는다.
  등록되지 않은 루트는 404 ``not_found``이고, 루트 밖으로 나가는 ``subdir``·보호 위치는 422다
  (``FolderWriter`` 규칙 그대로). 보관 파일(zip) 내려받기는 그대로다(받는 곳은 사용자가 고른다).
- 내보낼 원본 = 요청 ``?project=``의 프로젝트 공간(기본, ``definitions.spaces``) 또는
  ``source=library``면 라이브러리(``definitions.lookup``). ``project``가 없으면 라이브러리.

포트가 없으면(모듈 단독 사용) 지금 설정(``roots``)과 라이브러리 그대로다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from agent_console_contracts import ErrorCodes
from agent_console_exports import Exporter, ExportError, ExportRoot, ExportService, FolderWriter
from agent_console_secret_rules import SecretRules
from agent_console_store import StoreError

from .catalog import LookupExportCatalog
from .ports import DefinitionLookup, ExportDependencies

ExportSource = Literal["project", "library"]
"""내보낼 원본: ``project`` = 그 프로젝트 공간(``project``가 있을 때 기본), ``library`` = 공용."""

SOURCE_PROJECT: Final = "project"
SOURCE_LIBRARY: Final = "library"


class ProjectFolderLike(Protocol):
    """등록 폴더 하나(``agent_console_projects.ProjectFolder``가 만족)."""

    @property
    def id(self) -> str: ...

    @property
    def folder(self) -> Path: ...


class ProjectFoldersLike(Protocol):
    """``projects.folders`` 값 중 이 모듈이 쓰는 부분(등록·보관 아님 폴더 목록)."""

    @property
    def entries(self) -> Sequence[ProjectFolderLike]: ...


class DefinitionSpacesLike(Protocol):
    """``definitions.spaces`` 모양: 등록 id → 그 공간의 정의 저장소(읽기만 쓴다)."""

    def open(self, project_id: str) -> DefinitionLookup: ...


class ExportProjectError(ExportError):
    """프로젝트 범위 내보내기 오류(``code``는 계약 오류 코드)."""

    def __init__(self, message: str, *, code: str, details: Mapping[str, Any] | None = None):
        super().__init__(message, details=details)
        self.code = code


class ProjectExports:
    """요청의 ``project``·``source`` → 내보내기 서비스.

    Args:
        exporters: 형식 id → 형식.
        library: 라이브러리 정의 읽기(``definitions.lookup``).
        dependencies: 라이브러리 정의의 쓰는 정의(``exports.dependencies``). 프로젝트 공간 원본에는
            쓰지 않는다(라이브러리 기준 계산이라 섞인다) — 고른 항목만 내보낸다.
        roots: 프로젝트 기능이 없을 때의 폴더 쓰기 루트(설치자 ``roots``).
        protected: 쓰기 금지 위치(``~/.claude`` 등).
        folders: 등록 프로젝트 폴더(``projects.folders``). 없으면 단독 사용.
        spaces: 프로젝트 공간 정의 저장소(``definitions.spaces``).
        secret_rules: 지금 비밀 의심 규칙.
    """

    def __init__(
        self,
        exporters: Mapping[str, Exporter],
        *,
        library: DefinitionLookup,
        dependencies: ExportDependencies | None = None,
        roots: Sequence[ExportRoot] = (),
        protected: Sequence[Path] = (),
        folders: Callable[[], ProjectFoldersLike | None] = lambda: None,
        spaces: Callable[[], DefinitionSpacesLike | None] = lambda: None,
        secret_rules: Callable[[], SecretRules] | None = None,
    ) -> None:
        self._exporters = dict(exporters)
        self._library = library
        self._dependencies = dependencies
        self._roots = tuple(roots)
        self._protected = tuple(protected)
        self._folders = folders
        self._spaces = spaces
        self._rules = secret_rules

    @property
    def project_scoped(self) -> bool:
        """등록 프로젝트 기능이 조립에 있다(쓰기 대상 = 등록 폴더)."""
        return self._folders() is not None

    def roots(self) -> list[ExportRoot]:
        """폴더 쓰기 루트: 등록 프로젝트 폴더(프로젝트 기능이 있을 때) 또는 설치자 ``roots``."""
        folders = self._folders()
        if folders is None:
            return list(self._roots)
        return [ExportRoot(e.id, Path(e.folder), e.id) for e in folders.entries]

    def _registered(self, project_id: str) -> None:
        folders = self._folders()
        if folders is None or not any(e.id == project_id for e in folders.entries):
            raise ExportProjectError(
                f"등록된 프로젝트가 아닙니다: {project_id}",
                code=ErrorCodes.PROJECT_NOT_FOUND,
                details={"project_id": project_id},
            )

    def _catalog(self, project: str | None, source: ExportSource | None) -> LookupExportCatalog:
        if not self.project_scoped:
            if project is not None or source == SOURCE_PROJECT:
                raise ExportProjectError(
                    "프로젝트 기능이 없어 프로젝트를 고를 수 없습니다",
                    code=ErrorCodes.FEATURE_UNAVAILABLE,
                    details={"feature": "projects"},
                )
            return LookupExportCatalog(self._library, self._dependencies)
        wanted = source or (SOURCE_PROJECT if project else SOURCE_LIBRARY)
        if project is not None:
            self._registered(project)
        if wanted == SOURCE_LIBRARY:
            return LookupExportCatalog(self._library, self._dependencies)
        if project is None:
            raise ExportProjectError("내보낼 프로젝트를 고르세요", code=ErrorCodes.PROJECT_REQUIRED)
        spaces = self._spaces()
        if spaces is None:
            raise ExportProjectError(
                "프로젝트 공간을 열 수 없어 이 프로젝트의 구성을 내보낼 수 없습니다",
                code=ErrorCodes.FEATURE_UNAVAILABLE,
                details={"feature": "definitions.spaces", "project_id": project},
            )
        try:
            lookup = spaces.open(project)
        except LookupError:
            raise ExportProjectError(
                f"등록된 프로젝트가 아닙니다: {project}",
                code=ErrorCodes.PROJECT_NOT_FOUND,
                details={"project_id": project},
            ) from None
        except StoreError as exc:  # 폴더 없음·매니페스트 깨짐 등(공간 예외의 계약 코드)
            raise ExportProjectError(
                "프로젝트 공간을 열 수 없습니다",
                code=str(getattr(exc, "code", ErrorCodes.INTERNAL)),
                details={"project_id": project},
            ) from None
        return LookupExportCatalog(lookup)

    def service(
        self, project: str | None = None, source: ExportSource | None = None
    ) -> ExportService:
        """요청 범위의 내보내기 서비스(루트는 지금 등록 상태로 만든다).

        Raises:
            ExportProjectError: ``project.required``(422)·``project.not_found``(404)·
                ``feature_unavailable``(409).
        """
        return ExportService(
            self._exporters,
            self._catalog(project, source),
            writer=FolderWriter(self.roots(), protected=self._protected),
            secret_rules=self._rules,
        )


__all__ = [
    "SOURCE_LIBRARY",
    "SOURCE_PROJECT",
    "DefinitionSpacesLike",
    "ExportProjectError",
    "ExportSource",
    "ProjectExports",
    "ProjectFolderLike",
    "ProjectFoldersLike",
]

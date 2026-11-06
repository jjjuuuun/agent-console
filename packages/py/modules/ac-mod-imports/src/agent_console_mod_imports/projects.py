"""등록 프로젝트별 가져오기(5.7R.33k, design §PI.5 `.claude` 가져오기 행).

선택 포트 ``projects.folders``가 있으면 가져오기 출처는 **등록 프로젝트 하나의 폴더**에서만 만든다
(요청 ``?project=<등록 id>``). 설치자 설정 ``project_dir``는 쓰지 않는다. 가져온 정의는 기본으로 그
프로젝트 공간(``definitions.spaces``)에 들어가고, ``target=library``면 라이브러리(앱 workspace,
``definitions.store``)에 들어간다. 포트가 없으면(모듈 단독 사용) 지금 설정(``project_dir``)
그대로다.

어느 조립이든 사용자 전역 ``~/.claude`` 출처는 만들지 않는다(출처 맥락 ``home``은 늘 비어 있다,
K33-12·5.7R.30b).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from agent_console_contracts import ErrorCodes
from agent_console_imports import (
    DefinitionWriter,
    ImportService,
    ImportServiceError,
    ImportSourceContext,
    ImportSourceFactory,
    build_import_sources,
)
from agent_console_registry import Registry
from agent_console_secret_rules import SecretRules
from agent_console_store import StoreError

ImportTarget = Literal["project", "library"]
"""가져온 정의를 쓸 곳: ``project`` = 그 프로젝트 공간(기본), ``library`` = 라이브러리(공용)."""

TARGET_PROJECT: Final = "project"
TARGET_LIBRARY: Final = "library"


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
    """``definitions.spaces`` 모양: 등록 id → 그 공간의 정의 저장소."""

    def open(self, project_id: str) -> DefinitionWriter: ...


class ImportProjectError(ImportServiceError):
    """프로젝트 범위 가져오기 오류(``code``·``details``는 계약 오류)."""

    def __init__(self, message: str, *, code: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details: dict[str, Any] = dict(details or {})


@dataclass(frozen=True)
class ImportScope:
    """요청 하나가 쓰는 가져오기 서비스와 찍을 필드.

    Attributes:
        service: 출처·저장소가 정해진 가져오기 서비스.
        stamp: 가져온 정의에 더 찍을 최상위 필드(``ImportService.apply(stamp=)``).
    """

    service: ImportService
    stamp: Mapping[str, Any]


class ProjectImports:
    """요청의 ``project``·``target`` → 가져오기 서비스.

    Args:
        factories: 출처 공장 레지스트리(``import_sources``).
        options: 출처별 설치자 옵션.
        library: 라이브러리 정의 저장소(``definitions.store``).
        default_project_dir: 프로젝트 기능이 없을 때의 출처 폴더(설정 ``project_dir``).
        folders: 등록 프로젝트 폴더(``projects.folders``). 없으면 단독 사용.
        spaces: 프로젝트 공간 정의 저장소(``definitions.spaces``). 없으면 ``target=project`` 불가.
        secret_rules: 지금 비밀 의심 규칙.
    """

    def __init__(
        self,
        factories: Registry[ImportSourceFactory],
        *,
        options: Mapping[str, Any],
        library: DefinitionWriter,
        default_project_dir: Path | None,
        folders: Callable[[], ProjectFoldersLike | None] = lambda: None,
        spaces: Callable[[], DefinitionSpacesLike | None] = lambda: None,
        secret_rules: Callable[[], SecretRules] | None = None,
    ) -> None:
        self._factories = factories
        self._options = dict(options)
        self._library = library
        self._default_dir = default_project_dir
        self._folders = folders
        self._spaces = spaces
        self._rules = secret_rules
        self._standalone: ImportService | None = None

    @property
    def project_scoped(self) -> bool:
        """등록 프로젝트 기능이 조립에 있다(출처 = 등록 프로젝트 폴더)."""
        return self._folders() is not None

    def _service(self, project_dir: Path | None, store: DefinitionWriter) -> ImportService:
        # `home`은 넘기지 않는다: 사용자 전역 ~/.claude 출처는 어느 조립에도 없다(K33-12).
        context = ImportSourceContext(
            project_dir=project_dir, options=self._options, secret_rules=self._rules
        )
        return ImportService(build_import_sources(self._factories, context), store)

    def folder_of(self, project_id: str) -> Path:
        """등록(보관 아님) 프로젝트 폴더.

        Raises:
            ImportProjectError: 등록되지 않은 id(``project.not_found``).
        """
        folders = self._folders()
        for entry in folders.entries if folders is not None else ():
            if entry.id == project_id:
                return Path(entry.folder)
        raise ImportProjectError(
            f"등록된 프로젝트가 아닙니다: {project_id}",
            code=ErrorCodes.PROJECT_NOT_FOUND,
            details={"project_id": project_id},
        )

    def scope(self, project: str | None, target: ImportTarget | None = None) -> ImportScope:
        """요청 범위의 서비스.

        Args:
            project: 등록 id(``?project=``). 프로젝트 기능이 있는데 없으면 폴더가 필요 없는
                출처(플러그인)만 있고 저장 위치는 공용이다.
            target: 가져온 정의를 쓸 곳(기본 ``project``, 프로젝트가 없거나 단독 사용이면 공용).

        Raises:
            ImportProjectError: ``project.required``(422)·``project.not_found``(404)·
                ``feature_unavailable``(409, 프로젝트 기능·공간 없음).
        """
        if not self.project_scoped:
            if project is not None or target == TARGET_PROJECT:
                raise ImportProjectError(
                    "프로젝트 기능이 없어 프로젝트를 고를 수 없습니다",
                    code=ErrorCodes.FEATURE_UNAVAILABLE,
                    details={"feature": "projects"},
                )
            if self._standalone is None:
                self._standalone = self._service(self._default_dir, self._library)
            return ImportScope(self._standalone, {})
        if not project:
            # 프로젝트를 고르지 않으면 폴더가 필요 없는 출처(플러그인)만 있다 — 설정 project_dir를
            # 대신 쓰지 않는다. 저장 위치는 공용뿐이다.
            if target == TARGET_PROJECT:
                raise ImportProjectError(
                    "가져올 프로젝트를 고르세요", code=ErrorCodes.PROJECT_REQUIRED
                )
            return ImportScope(self._service(None, self._library), {})
        folder = self.folder_of(project)
        if (target or TARGET_PROJECT) == TARGET_LIBRARY:
            return ImportScope(self._service(folder, self._library), {})
        spaces = self._spaces()
        if spaces is None:
            raise ImportProjectError(
                "프로젝트 공간을 열 수 없어 이 프로젝트에 가져올 수 없습니다",
                code=ErrorCodes.FEATURE_UNAVAILABLE,
                details={"feature": "definitions.spaces", "project_id": project},
            )
        try:
            store = spaces.open(project)
        except LookupError:
            raise ImportProjectError(
                f"등록된 프로젝트가 아닙니다: {project}",
                code=ErrorCodes.PROJECT_NOT_FOUND,
                details={"project_id": project},
            ) from None
        except StoreError as exc:  # 폴더 없음·매니페스트 깨짐 등(공간 예외의 계약 코드)
            raise ImportProjectError(
                "프로젝트 공간을 열 수 없습니다",
                code=str(getattr(exc, "code", ErrorCodes.INTERNAL)),
                details={"project_id": project},
            ) from None
        # 프로젝트 공간의 정의에는 옛 범위 필드(`project`)를 찍지 않는다(값 None = 필드 빼기).
        return ImportScope(self._service(folder, store), {"project": None})


__all__ = [
    "TARGET_LIBRARY",
    "TARGET_PROJECT",
    "DefinitionSpacesLike",
    "ImportProjectError",
    "ImportScope",
    "ImportTarget",
    "ProjectFolderLike",
    "ProjectFoldersLike",
    "ProjectImports",
]

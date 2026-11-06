"""mod-projects의 공개 포트·토픽(이름 = 포트, design §PI.10).

제공:

- ``projects.lookup``: 프로젝트 읽기(``ProjectLookup`` — ``get_project``·``list_projects``, 등록부 +
  폴더 매니페스트를 합친 ``Project``). ``link-projects-runs`` 등이 이름으로 받는다.
- ``projects.folders``: 등록된 프로젝트 폴더(``ProjectFolderSet`` — ``entries``(id·폴더)·
  ``archived``(보관 폴더)·``project_for(path)``). 로그 수집 범위·세션 ``project_id`` 등이 받는다.
- ``projects.spaces``: 등록 id → 프로젝트 공간(``ProjectSpaces.open`` → ``ProjectSpace``:
  ``folder``·``definitions``·``records_db_path``·``memory_db_path``·``sessions_dir``·``state_dir``·
  ``config_writable``). 열린 공간 캐시(상한·유휴 닫기). 모르는 프로젝트 ``LookupError``, 폴더 없음
  ``FolderMissing``. ``link-projects-records``(필수)·``link-projects-memory``가 받는다.
- ``definitions.spaces``: 등록 id → 그 공간의 정의 저장소(``DefinitionSpaces.open``). 정의 모듈이
  ``?project=``로 쓴다(프로젝트를 모르고 이름 → 저장소만).

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``definitions.lookup``·``definitions.store``: 라이브러리(앱 workspace) 정의. 없으면 라이브러리가
  낀 복사·옛 데이터 계획이 409 ``feature_unavailable``. 저장소가 ``kind_info``를 주면 그 종류 정보
  (해시 함수 포함)로 프로젝트 공간을 연다(없으면 ``ac-store`` 기본 종류).
- ``definitions.references``(여러 제공자, X25): 참조 추출. 없으면 복사 계획에
  ``project.references_unavailable`` 정보.
- ``definitions.reference_rewriters``(여러 제공자, 신규): 이름 바꾸기 복사의 참조 고치기
  (``RewriteReferences``). 없으면 참조는 그대로 두고 결과 항목에 정보 이슈.
- ``records.spaces``(``link-projects-records``): ``ProjectView.records_*``. 없으면
  ``records_state = unavailable``·``reason = link_disabled``.
- ``secrets.rules``: 비밀 의심 규칙(프로젝트 공간 쓰기·라이브러리로 복사할 때 검사). 없으면
  기본 규칙.
- 토픽 ``definitions.saved``: 옛 범위 정리용 정의 스냅샷 캐시를 버린다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Project
from agent_console_modkit import PortKey, Topic
from agent_console_project_space import ProjectSpace
from agent_console_projects import ProjectFolderSet, RewriteReferences
from agent_console_secret_rules import SecretRules
from agent_console_store import RECORDS_SPACES_PORT, DefinitionStore, RecordsSpaces


class StoredLike(Protocol):
    """저장된 정의 하나(문서·버전)."""

    @property
    def document(self) -> dict[str, Any]: ...

    @property
    def version_hash(self) -> str: ...


@runtime_checkable
class DefinitionReader(Protocol):
    """정의 읽기(``definitions.lookup`` 모양의 일부). 없는 정의는 저장소 예외(``NotFound``)."""

    def kinds(self) -> list[str]: ...

    def list_ids(self, kind: str) -> list[str]: ...

    def get(self, kind: str, id: str) -> StoredLike: ...


@runtime_checkable
class DefinitionWriter(DefinitionReader, Protocol):
    """정의 쓰기(``definitions.store`` 모양의 일부)."""

    def save(
        self,
        kind: str,
        document: Mapping[str, Any],
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> StoredLike: ...

    def delete(self, kind: str, id: str, *, expected_version: str | None = None) -> None: ...


@runtime_checkable
class ProjectLookup(Protocol):
    """``projects.lookup`` 모양: 프로젝트 읽기."""

    def get_project(self, project_id: str) -> Project | None:
        """id의 프로젝트(등록부 + 매니페스트). 없거나 읽을 수 없으면 None."""
        ...

    def list_projects(self) -> list[Project]:
        """모든 프로젝트(id 순, 보관 포함, 읽을 수 없는 파일은 뺀다)."""
        ...


@runtime_checkable
class ProjectSpaces(Protocol):
    """``projects.spaces`` 모양: 등록 id → 열린 프로젝트 공간."""

    def open(self, project_id: str) -> ProjectSpace:
        """공간을 연다(캐시). 아무것도 만들거나 쓰지 않는다.

        Raises:
            LookupError: 모르는 프로젝트.
            agent_console_project_space.FolderMissing: 폴더가 없거나 지정되지 않았다.
            agent_console_project_space.SpaceError: 그 밖에 열 수 없다(링크 구성 폴더 등).
        """
        ...

    def close(self, project_id: str) -> None:
        """캐시에서 뺀다(다음 ``open``이 다시 연다)."""
        ...


@runtime_checkable
class DefinitionSpaces(Protocol):
    """``definitions.spaces`` 모양: 공간 이름(등록 id) → 정의 저장소."""

    def open(self, project_id: str) -> DefinitionStore:
        """그 프로젝트 공간의 정의 저장소. 예외는 ``ProjectSpaces.open``과 같다."""
        ...


class References(Protocol):
    """``definitions.references`` 모양(X25): 문서 하나가 쓰는 정의의 ``(종류, id)``."""

    def __call__(self, kind: str, document: Mapping[str, Any]) -> Iterable[tuple[str, str]]: ...


class SavedLike(Protocol):
    """``definitions.saved`` 항목 모양(``kind``·``id``·``version_hash``)."""

    @property
    def kind(self) -> str: ...

    @property
    def id(self) -> str: ...


PROJECTS_LOOKUP: PortKey[ProjectLookup] = PortKey("projects.lookup", "프로젝트 읽기")
PROJECT_FOLDERS: PortKey[Callable[[], ProjectFolderSet]] = PortKey(
    "projects.folders", "앱에 등록된 프로젝트 폴더(전체·보관)"
)
PROJECTS_SPACES: PortKey[ProjectSpaces] = PortKey("projects.spaces", "프로젝트 공간 열기")
DEFINITIONS_SPACES: PortKey[DefinitionSpaces] = PortKey(
    "definitions.spaces", "공간 이름(등록 id) → 정의 저장소"
)
DEFINITIONS_LOOKUP: PortKey[DefinitionReader] = PortKey("definitions.lookup", "정의 읽기")
DEFINITIONS_STORE: PortKey[DefinitionWriter] = PortKey("definitions.store", "정의 저장소")
DEFINITIONS_REFERENCES: PortKey[References] = PortKey(
    "definitions.references", "정의 문서의 참조 추출(X25)", multi=True
)
DEFINITIONS_REWRITERS: PortKey[RewriteReferences] = PortKey(
    "definitions.reference_rewriters", "정의 문서의 참조 고치기(이름 바꾸기 복사)", multi=True
)
RECORDS_SPACES: PortKey[RecordsSpaces] = PortKey(
    RECORDS_SPACES_PORT, "공간 이름 → 프로젝트 기록 DB 핸들"
)
SECRET_RULES: PortKey[Callable[[], SecretRules]] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
DEFINITIONS_SAVED: Topic[SavedLike] = Topic("definitions.saved")

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_REFERENCES",
    "DEFINITIONS_REWRITERS",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_SPACES",
    "DEFINITIONS_STORE",
    "PROJECTS_LOOKUP",
    "PROJECTS_SPACES",
    "PROJECT_FOLDERS",
    "RECORDS_SPACES",
    "SECRET_RULES",
    "DefinitionReader",
    "DefinitionSpaces",
    "DefinitionWriter",
    "ProjectLookup",
    "ProjectSpaces",
    "References",
    "SavedLike",
    "StoredLike",
]

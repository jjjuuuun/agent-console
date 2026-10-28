"""계약 하위 모듈 `projects`: 프로젝트 정의와 그 REST DTO(design §PI, 3.0.0 — 0.12.0).

프로젝트 = 로컬 폴더 하나(절대 경로) + 그 폴더 안의 프로젝트 구성(`.agent-console/`, design §PI.2).
기능(채팅·실행·로그·메모리 등)은 등록된 프로젝트 폴더에 대해서만 동작한다. 앱 workspace의 구성은
라이브러리(기본값)이고, 프로젝트는 쓰는 구성을 자기 폴더 안에 **사본**으로 갖는다(복사 계획·적용,
§PI.4.2). 프로젝트 목록·속성은 전부 사용자 데이터이며 코드에 프로젝트가 없다(0개가 기본). 정의 종류
이름(`DefinitionKey.kind`)도 열린 문자열이다.

저장은 두 곳이다: 앱 등록부 `ProjectRegistration`(`<workspace>/projects/<id>.yaml`)과 폴더
매니페스트 `ProjectManifest`(`<folder>/.agent-console/project.yaml`). API의 `Project`는 둘을 합친
보기다.

2.0에서 바뀐 것(3.0.0):
- `uses`·`import_mode`·`ProjectUse`·`ProjectUseMode`·`ProjectImportMode` 삭제. 옛 파일의 두 키는
  읽을 때 버린다(`IGNORED_PROJECT_KEYS`, 저장 때 키가 빠짐).
- `ProjectUsesUpdate`·`UseCopyRequest`·`UseCopyResult`·`DefinitionCopy`·`LegacyUse*` 삭제 → 공간
  사이 복사 `CopyPlanRequest`·`CopyPlan`·`CopyApplyRequest`·`CopyApplyResult`.
- 새 모델 `ProjectRegistration`·`ProjectManifest`, `ProjectView.config_writable`·`manifest_id`·
  `kinds`·`issues`, 상태 `manifest_invalid`, 폴더 선택 `FolderCapabilities`·`FolderPickRequest`·
  `FolderPickResult`.
- `ProjectNotImportedDetails`: `reason`·`import_mode` → `in_library`.

1.x에서 바뀐 것(2.0.0): `working_directory` → `folder`(읽을 때 옮김), `log_projects` 삭제(버림),
`archived`·`archived_at`, 상태 보기·폴더 확인·탐색·이전 기록 넣기·개수 DTO. 정의 범위 옮기기
(`MovePlan` 등)와 `ProjectDeleteMode`의 `delete_definitions`는 deprecated(다음 major에서 삭제).

새 정의 범위 설정 `ProjectPreferences`(deprecated)는 공통 설정의 섹션이라 `definitions`에 있고
편의를 위해 여기서도 다시 내보낸다.

의존: `common`(`SpaceRef`), `definitions`. 실행·대화의 `project_id`는 `runs`·`chat`의 불투명
문자열이다.
"""

from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel, DefinitionModel, JsonObject, NonEmptyStr, Slug
from .common import JsonPointer, SpaceRef, x_ui
from .definitions import AgentSettings, DefinitionScope, Issue, ProjectPreferences

type ProjectDeleteMode = Literal["move_to_shared", "delete_definitions"]
"""(deprecated, 0.11.0) 1.x 프로젝트 삭제 때 그 프로젝트 정의 처리. 2.0에서 삭제는 등록 해제
(보관) 하나이고 정의는 프로젝트 소유가 아니다(design §PI.2 K33-4). 다음 major에서 삭제."""

type ProjectStatus = str
"""프로젝트 상태(계산 값, 저장하지 않음). 열린 문자열이고 알려진 값은 `KnownProjectStatuses`."""


class KnownProjectStatuses:
    """`ProjectView.status`의 알려진 값(design §PI.2). **문서 상수**다.

    목록·enum이 아니다. 서버가 다른 상태를 낼 수 있고 화면은 모르는 값을 원문 + 일반 경고로
    보인다. 이름 → 값 표를 스키마 `x-constants.KNOWN_PROJECT_STATUSES`로 내보낸다.
    """

    READY: Final = "ready"
    """폴더가 있고 쓸 수 있다."""
    FOLDER_MISSING: Final = "folder_missing"
    """폴더가 없다(지우거나 옮김·드라이브 분리). 기록 보기만 된다(K33-3)."""
    NOT_A_DIRECTORY: Final = "not_a_directory"
    """경로가 폴더가 아니다."""
    NO_ACCESS: Final = "no_access"
    """서버 계정이 폴더를 읽을 수 없다."""
    FOLDER_UNSET: Final = "folder_unset"
    """옛 파일이라 폴더가 지정되지 않았다(`folder` null)."""
    FOLDER_CONFLICT: Final = "folder_conflict"
    """옛 파일끼리 같은·겹치는 폴더를 가리킨다(design §PI.8)."""
    MANIFEST_INVALID: Final = "manifest_invalid"
    """폴더는 있으나 매니페스트(`.agent-console/project.yaml`)를 읽을 수 없다(0.12.0)."""


class KnownFolderCheckStatuses:
    """`FolderCheck.status`의 알려진 값(design §PI.6, screen-projects §3.3). **문서 상수**다.

    폴더만 보고 정하는 값(`ac-local-folders`)과 등록부를 보고 정하는 값(mod-projects)을 함께 담는다.
    목록·enum이 아니다. 이름 → 값 표를 스키마 `x-constants.KNOWN_FOLDER_CHECK_STATUSES`로 내보낸다.
    """

    OK: Final = "ok"
    OK_READONLY: Final = "ok_readonly"
    MISSING: Final = "missing"
    """없고 만들 수 있다(`can_create`). 탐색 시작은 `nearest_existing`."""
    MISSING_PARENT: Final = "missing_parent"
    NOT_DIRECTORY: Final = "not_directory"
    NO_ACCESS: Final = "no_access"
    INVALID: Final = "invalid"
    """입력이 쓸 수 있는 경로가 아니다(이유 `problem`, 다른 OS 경로면 `foreign_path`)."""
    TAKEN: Final = "taken"
    """같은 폴더가 이미 등록됨(`conflict.project_id`)."""
    TAKEN_ARCHIVED: Final = "taken_archived"
    """같은 폴더의 프로젝트가 보관(등록 해제)됨 — 다시 등록을 제안."""
    OVERLAP_PARENT: Final = "overlap_parent"
    """이 폴더를 포함하는 프로젝트가 있다(`conflict.relation = "parent"`)."""
    OVERLAP_CHILD: Final = "overlap_child"
    """이 폴더 안에 등록된 프로젝트가 있다(`conflict.relation = "child"`)."""
    SAME_PATH: Final = "same_path"
    """경로 다시 지정에서 지금 경로와 같다(`exclude_project_id`의 프로젝트)."""


class KnownFolderConflictRelations:
    """`FolderConflict.relation`·`ProjectFolderConflictDetails.relation`의 알려진 값.

    **문서 상수**다.

    기준은 확인한 경로다: parent = 등록된 프로젝트가 이 경로를 포함, child = 이 경로 안에 등록된
    프로젝트가 있음, same = 같은 폴더.
    """

    SAME: Final = "same"
    PARENT: Final = "parent"
    CHILD: Final = "child"


# ---------------------------------------------------------------- 프로젝트 정의(등록부·매니페스트)

IGNORED_PROJECT_KEYS: Final = ("log_projects", "uses", "import_mode")
"""프로젝트 파일(등록부·합친 보기)을 읽을 때 버리는 옛 키(0.11.0 `log_projects`, 0.12.0 `uses`·
`import_mode`). 모르는 키 보존 규칙과 달리 저장 때 빠진다. 읽는 쪽(저장소)은
`ignored_project_keys`로 찾아 정보 이슈 `settings.ignored_key`를 낼 수 있다."""

PROJECT_MANIFEST_FORMAT: Final = 1
"""이 계약이 쓰는 매니페스트 형식 번호(`ProjectManifest.format`의 기본값)."""


def ignored_project_keys(data: Any) -> list[str]:
    """프로젝트 문서 `data`에 들어 있는, 읽을 때 버리는 옛 키 이름(`IGNORED_PROJECT_KEYS` 순서).

    Args:
        data: 파일에서 읽은 문서. 매핑이 아니면 빈 목록.

    Returns:
        들어 있는 옛 키 이름 목록. 없으면 빈 목록.

    >>> ignored_project_keys({"id": "p", "uses": [], "import_mode": "all"})
    ['uses', 'import_mode']
    >>> ignored_project_keys("x")
    []
    """
    if not isinstance(data, Mapping):
        return []
    return [key for key in IGNORED_PROJECT_KEYS if key in data]


def _read_legacy_project_keys(data: Any) -> Any:
    """옛 키를 읽는다: `working_directory` → `folder`(folder 우선), 버릴 키는 뺀다."""
    if not isinstance(data, Mapping):
        return data
    doc = dict(data)
    legacy_folder = doc.pop("working_directory", None)
    for key in IGNORED_PROJECT_KEYS:
        doc.pop(key, None)
    if doc.get("folder") is None:
        doc["folder"] = legacy_folder or None
    return doc


class _ManifestFields(DefinitionModel):
    """폴더 매니페스트에 저장하는 사용자 필드(매니페스트·합친 보기·만들기 공통)."""

    description: str = Field(
        default="",
        title="설명",
        description="이 프로젝트가 무엇인지 적습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 프로젝트가 무엇인지 함께 쓰는 사람에게 알리고 싶을 때 적으세요.",
            example="결제 API와 관리 화면",
        ),
    )
    settings: AgentSettings | None = Field(
        default=None,
        title="프로젝트 층 설정",
        description="이 프로젝트의 에이전트 설정입니다. 비운 항목은 공통 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="이 프로젝트에서만 모델·지침을 다르게 하고 싶을 때 바꾸세요."
        ),
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description="다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.",
        json_schema_extra={"default": {}, **x_ui(tier="advanced")},
    )


class _LabelFields(DefinitionModel):
    """앱 등록부에 저장하는 꼬리표(등록부·합친 보기·만들기 공통)."""

    labels: list[str] = Field(
        default_factory=list,
        title="라벨",
        description="찾기·거르기에 쓰는 꼬리표입니다.",
        json_schema_extra={"default": [], **x_ui(tier="advanced")},
    )


class _RegistrationFields(_LabelFields):
    """앱 등록부에만 있는 상태 필드(등록부·합친 보기 공통)."""

    archived: bool = Field(
        default=False,
        title="등록 해제됨",
        description="등록 해제(보관)한 프로젝트입니다. 목록·기능에서 빠지고 기록은 남습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    archived_at: float | None = Field(
        default=None,
        title="등록 해제 시각",
        description="등록 해제한 시각(Unix epoch 초)입니다. 서버가 채웁니다.",
        json_schema_extra=x_ui(tier="advanced", example=None),
    )


_FOLDER_DESCRIPTION = (
    "이 프로젝트의 로컬 폴더(절대 경로)입니다. 기능은 이 폴더 안에서만 동작합니다."
)
_ID_DESCRIPTION = "가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 씁니다."


class ProjectRegistration(_RegistrationFields):
    """이 앱이 프로젝트로 등록한 폴더입니다. 폴더와 등록 상태만 담습니다."""

    # 앱 등록부 파일(`<workspace>/projects/<id>.yaml`, 정의 종류 `project`, design §PI.2 K33-1).
    # 이름·설명·프로젝트 층은 폴더 매니페스트에 있다. 옛(0.11 이하) 파일의 그 키들은 모르는 키로
    # 보존되므로 저장소(33e)가 매니페스트로 옮긴다. 옛 `working_directory`는 `folder`로 읽고
    # `IGNORED_PROJECT_KEYS`는 버린다.

    model_config = ConfigDict(title="프로젝트 등록")

    kind: Literal["project"] = "project"
    id: Slug = Field(
        title="등록 id",
        description=_ID_DESCRIPTION + " 실행·대화 기록이 이 id로 프로젝트를 가리킵니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    folder: NonEmptyStr | None = Field(
        title="폴더",
        description=_FOLDER_DESCRIPTION + " 옛 파일에 폴더가 없으면 비어 있습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="폴더를 옮기거나 이름을 바꿨을 때 [경로 다시 지정]으로 바꾸세요.",
            example="/home/me/work/payments",
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _read_legacy_keys(cls, data: Any) -> Any:
        return _read_legacy_project_keys(data)


class ProjectManifest(_ManifestFields):
    """프로젝트 폴더에 들어 있는 프로젝트 정보입니다. 폴더와 함께 옮겨지고 git으로 관리됩니다."""

    # 폴더 매니페스트(`<folder>/.agent-console/project.yaml`, design §PI.2). 모르는 키는 보존한다
    # (다른 앱·다른 버전이 쓴 키를 왕복). `id`는 폴더 id(폴더 안 데이터용, §PI.4.4)이고 앱 등록
    # id와 다를 수 있다.

    model_config = ConfigDict(title="프로젝트 매니페스트")

    format: int = Field(
        default=PROJECT_MANIFEST_FORMAT,
        ge=1,
        title="형식 버전",
        description="매니페스트 파일 형식 번호입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    id: Slug = Field(
        title="폴더 id",
        description="이 폴더의 프로젝트 id입니다. 프로젝트 메모리 범위 등 폴더 안 데이터가 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example="payments"),
    )
    name: NonEmptyStr = Field(
        title="이름",
        description="프로젝트를 부르는 이름입니다. 왼쪽 메뉴 프로젝트 목록에 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="프로젝트 목록에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="결제 서비스",
        ),
    )


class Project(_RegistrationFields, _ManifestFields):
    """프로젝트입니다. 로컬 폴더 하나와 그 프로젝트에서 쓸 설정을 묶습니다."""

    # 합친 보기(design §PI.2): `id`·`folder`·`archived`·`archived_at`·`labels`는 등록부,
    # `name`·`description`·`settings`·`attributes`는 매니페스트. 0.11 이하에서는 이 모양 그대로
    # `<workspace>/projects/<id>.yaml`에 저장했다. 읽기 호환(§PI.8): 옛 키 `working_directory`는
    # `folder`로 옮기고(상대 경로 절대화는 ac-projects), `IGNORED_PROJECT_KEYS`는 버린다. 폴더가
    # 없던 옛 파일은 `folder: null`(folder_unset).

    model_config = ConfigDict(title="프로젝트")

    kind: Literal["project"] = "project"
    id: Slug = Field(
        title="id",
        description=_ID_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )
    name: NonEmptyStr = Field(
        title="이름",
        description="프로젝트를 부르는 이름입니다. 왼쪽 메뉴 프로젝트 목록에 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="프로젝트 목록에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="결제 서비스",
        ),
    )
    folder: NonEmptyStr | None = Field(
        title="폴더",
        description=_FOLDER_DESCRIPTION + " 옛 파일에 폴더가 없으면 비어 있습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="폴더를 옮기거나 이름을 바꿨을 때 [경로 다시 지정]으로 바꾸세요.",
            example="/home/me/work/payments",
        ),
    )
    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description="파일 형식 번호입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )

    @model_validator(mode="before")
    @classmethod
    def _read_legacy_keys(cls, data: Any) -> Any:
        """옛 키를 읽는다: `working_directory` → `folder`, `IGNORED_PROJECT_KEYS`는 버린다."""
        return _read_legacy_project_keys(data)

    # ---- 1.x 호환 읽기 전용(파이썬 소비자만, 스키마에 없음). 33e·33i가 소비자를 옮긴 뒤 삭제한다.

    @property
    def working_directory(self) -> str | None:
        """(deprecated, 0.11.0) `folder`와 같다. 새 코드는 `folder`를 쓴다."""
        return self.folder

    @property
    def log_projects(self) -> list[str]:
        """(deprecated, 0.11.0) 늘 빈 목록. 로그의 프로젝트는 폴더로 정한다(design §PI.5)."""
        return []


class ProjectCreate(_LabelFields, _ManifestFields):
    """프로젝트 폴더를 등록할 때 적는 값입니다."""

    # `POST /projects` 요청. 응답은 `ProjectView`(201). 같은 폴더 409 `project.folder_taken`,
    # 겹침 409 `project.folder_overlaps`(design §PI.2 K33-2). id·이름을 비우면 서버가 채운다
    # (폴더에 매니페스트가 있으면 그 값, 없으면 폴더 이름. id는 겹치면 `-2`…, K33-25).

    model_config = ConfigDict(title="프로젝트 폴더 추가")

    folder: NonEmptyStr = Field(
        title="폴더",
        description=_FOLDER_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic",
            when="이 프로젝트로 작업할 저장소·폴더를 [폴더 선택]으로 고르거나 경로를 적으세요.",
            example="/home/me/work/payments",
        ),
    )
    id: Slug | None = Field(
        default=None,
        title="id",
        description="고유 이름입니다. 비우면 폴더 이름으로 만듭니다. 만든 뒤에는 바꿀 수 없습니다.",
        json_schema_extra=x_ui(tier="advanced", example="payments"),
    )
    name: NonEmptyStr | None = Field(
        default=None,
        title="이름",
        description="프로젝트를 부르는 이름입니다. 비우면 폴더 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="폴더 이름과 다른 이름으로 부르고 싶을 때 적으세요.",
            example="결제 서비스",
        ),
    )


class ProjectUpdate(ContractModel):
    """`PUT /projects/{id}` 요청. 생략한 필드는 그대로 둔다.

    `settings`의 null은 값을 지운다(상속으로 되돌림). 다른 필드의 null은 생략과 같다.
    `folder`는 경로 다시 지정이다(같은·겹침 검사는 자기 자신을 빼고 한다). `archived: false`는
    등록 해제한 프로젝트를 다시 등록한다(폴더 검사를 다시 한다). 이름·설명·설정·속성은 폴더
    매니페스트에, 폴더·보관·라벨은 등록부에 쓴다. 옛 키(`uses`·`import_mode`)는 무시한다.
    """

    name: NonEmptyStr | None = None
    description: str | None = None
    folder: NonEmptyStr | None = None
    settings: AgentSettings | None = None
    archived: bool | None = None
    labels: list[str] | None = None
    attributes: JsonObject | None = None


class ProjectView(ContractModel):
    """프로젝트 + 서버가 계산한 상태(저장하지 않음).

    `GET /projects`(→ `ProjectView[]`)·`GET /projects/{id}`·`POST /projects`·`PUT /projects/{id}`
    응답이다.
    """

    project: Project
    status: ProjectStatus = Field(
        description="ready 또는 문제 상태(`KnownProjectStatuses`, 열린 문자열)."
    )
    status_detail: str | None = Field(
        default=None, description="상태 이유 한 줄(예: 겹치는 프로젝트 id). 화면에 그대로 보인다."
    )
    version_hash: str | None = Field(
        default=None,
        description=(
            "버전 해시(`If-Match`에 쓴다). 등록부·매니페스트 둘 중 하나가 바뀌면 바뀐다. "
            "저장소가 주지 않으면 null."
        ),
    )
    config_writable: bool = Field(
        default=True,
        description=(
            "폴더 안 프로젝트 구성(`.agent-console/`)에 쓸 수 있는가. false면 가져오기·편집·메모리 "
            "쓰기를 막고(409 `project.config_readonly`) 보기·로그는 된다. "
            "보내지 않은 옛 서버는 true."
        ),
    )
    manifest_id: Slug | None = Field(
        default=None,
        description="폴더 id(매니페스트 `id`). 등록 id와 다를 때만 화면에 보인다. 모르면 null.",
    )
    kinds: list[str] = Field(
        default_factory=list,
        description=(
            "이 프로젝트 공간에 둘 수 있는 정의 종류 이름(옮길 수 있는 종류, 열린 문자열). "
            "빈 목록 = 서버가 알리지 않음."
        ),
    )
    issues: list[Issue] = Field(
        default_factory=list,
        description=(
            "상태와 별개인 안내(예: 정보 `project.memory_network_fs`). 화면은 모르는 코드도 보인다."
        ),
    )


# ---------------------------------------------------------------- 공간 사이 복사(design §PI.4.2)


class KnownCopyActions:
    """`CopyApplyItem.action`·`CopyPlanItem.default_action`의 알려진 값(design §PI.4.2).

    **문서 상수**다.

    목록·enum이 아니다. 이름 → 값 표를 스키마 `x-constants.KNOWN_COPY_ACTIONS`로 내보낸다.
    """

    COPY: Final = "copy"
    """대상에 없다 — 그대로 복사."""
    REUSE: Final = "reuse"
    """같은 내용이 이미 있다 — 쓰지 않고 그것을 쓴다."""
    OVERWRITE: Final = "overwrite"
    """대상의 다른 내용을 원본으로 덮어쓴다(대상에서 바꾼 내용이 사라짐)."""
    RENAME: Final = "rename"
    """새 id(`new_id`)로 복사하고 이 묶음 안의 참조를 새 id로 고친다."""
    SKIP: Final = "skip"
    """복사하지 않는다(참조 항목을 빼면 실행 전에 막힐 수 있다는 경고)."""


class KnownCopyTargetStates:
    """`CopyPlanItem.target_state`의 알려진 값. **문서 상수**다.

    이름 → 값 표를 스키마 `x-constants.KNOWN_COPY_TARGET_STATES`로 내보낸다. 기본 동작:
    absent → copy, identical → reuse, different → 없음(사용자 선택 필요).
    """

    ABSENT: Final = "absent"
    IDENTICAL: Final = "identical"
    """같은 (종류, id)가 있고 내용 해시가 같다."""
    DIFFERENT: Final = "different"
    """같은 (종류, id)가 있고 내용이 다르다."""


class KnownCopyStatuses:
    """`CopyApplyItemResult.status`의 알려진 값. **문서 상수**다.

    이름 → 값 표를 스키마 `x-constants.KNOWN_COPY_STATUSES`로 내보낸다.
    """

    COPIED: Final = "copied"
    REUSED: Final = "reused"
    OVERWRITTEN: Final = "overwritten"
    RENAMED: Final = "renamed"
    SKIPPED: Final = "skipped"
    CONFLICT: Final = "conflict"
    """계획 뒤 원본(`source_version`)이나 대상(`target_version`)이 바뀌어 적용하지 않았다
    (`issue.code = project.copy_conflict`). 나머지 항목은 적용된다."""


class DefinitionKey(ContractModel):
    """정의 하나를 가리키는 키(종류 이름 + id). 표시 이름은 선택."""

    kind: NonEmptyStr = Field(description="정의 종류 이름(예: agent, graph, resource).")
    id: NonEmptyStr
    name: str = ""


class CopyPlanRequest(ContractModel):
    """`POST /projects/copy/plan` 요청: 고른 정의를 원본 공간에서 대상 공간으로 복사할 계획.

    공간은 `SpaceRef`(`project_id` null = 라이브러리). 라이브러리 → 프로젝트가 기본 방향이고
    프로젝트 → 라이브러리, 프로젝트 → 프로젝트도 같은 모양이다. 계획은 아무것도 쓰지 않는다.
    """

    source: SpaceRef
    target: SpaceRef
    items: list[DefinitionKey] = Field(description="복사할 정의(종류·id). 표시 이름은 무시한다.")
    include_references: bool = Field(
        default=True,
        description="참조 닫힘(팀이 쓰는 에이전트·리소스·중첩 팀)도 계획에 넣는다.",
    )


class CopyPlanItem(ContractModel):
    """복사 계획의 항목 하나(요청한 것 또는 참조 때문에 함께 들어온 것)."""

    kind: NonEmptyStr
    id: NonEmptyStr
    name: str = ""
    reason: str = Field(
        description="계획에 든 이유(열린 문자열): requested = 요청함, referenced = 참조로 들어옴."
    )
    referenced_by: list[DefinitionKey] = Field(
        default_factory=list, description="이 항목을 참조하는 계획 안 정의."
    )
    source_version: str = Field(description="원본 버전 해시(적용 때 바뀌었으면 conflict).")
    target_state: str = Field(
        description="대상 공간의 같은 (종류, id) 상태(`KnownCopyTargetStates`, 열린 문자열)."
    )
    target_version: str | None = Field(
        default=None, description="대상의 지금 버전 해시(대상에 없으면 null). 적용 때 `If-Match`."
    )
    default_action: str | None = Field(
        default=None,
        description="기본 동작(`KnownCopyActions`). null = 사용자가 골라야 한다(대상 내용이 다름).",
    )


class CopyPlan(ContractModel):
    """`POST /projects/copy/plan` 응답(저장하지 않음)."""

    items: list[CopyPlanItem] = Field(default_factory=list)
    warnings: list[Issue] = Field(
        default_factory=list, description="계획 경고(예: 참조를 찾지 못함, 순환 참조)."
    )


class CopyApplyItem(ContractModel):
    """적용할 항목 하나와 사용자가 고른 동작."""

    kind: NonEmptyStr
    id: NonEmptyStr
    action: NonEmptyStr = Field(description="동작(`KnownCopyActions`, 열린 문자열).")
    new_id: Slug | None = Field(default=None, description="rename일 때 새 id(필수).")
    source_version: str = Field(description="계획 때 원본 버전 해시.")
    target_version: str | None = Field(
        default=None, description="계획 때 대상 버전 해시(대상에 없었으면 null)."
    )

    @model_validator(mode="after")
    def _rename_needs_new_id(self) -> "CopyApplyItem":
        if self.action == KnownCopyActions.RENAME and not self.new_id:
            raise ValueError("action이 rename이면 new_id가 필요합니다")
        return self


class CopyApplyRequest(ContractModel):
    """`POST /projects/copy/apply` 요청: 계획에서 고른 항목을 적용한다.

    사본에는 원본 id·버전·시각을 쓰지 않는다(완전 독립, 사용자 결정 B). 리소스 본문 파일도 함께
    복사한다. 대상 프로젝트 폴더에 쓸 수 없으면 409 `project.config_readonly`.
    """

    source: SpaceRef
    target: SpaceRef
    items: list[CopyApplyItem]
    remove_source: bool = Field(
        default=False,
        description="적용한 항목을 원본 공간에서 지운다(옛 프로젝트 전용 정의 정리에 쓴다).",
    )


class CopyApplyItemResult(ContractModel):
    """적용 항목 하나의 결과."""

    kind: NonEmptyStr
    id: NonEmptyStr = Field(description="원본 id.")
    new_id: str | None = Field(default=None, description="대상에 쓴 id(rename일 때).")
    status: str = Field(description="결과(`KnownCopyStatuses`, 열린 문자열).")
    issue: Issue | None = Field(
        default=None, description="conflict·skipped 등의 이유(예: `project.copy_conflict`)."
    )


class CopyApplyResult(ContractModel):
    """`POST /projects/copy/apply` 응답."""

    items: list[CopyApplyItemResult] = Field(default_factory=list)


# ---------------------------------------------------------------- 폴더 확인·탐색(design §PI.6)


class FolderCheckRequest(ContractModel):
    """`POST /projects/folders/check` 요청(루프백 전용, 아니면 403 `folders.remote_disabled`)."""

    path: str = Field(description="사용자가 입력한 경로(그대로). 비면 status invalid.")
    create: bool = Field(
        default=False,
        description="없으면 만든다(사용자가 [이 경로에 폴더 만들기]를 누를 때만 true). 한 단계만.",
    )
    exclude_project_id: Slug | None = Field(
        default=None,
        description=(
            "이 프로젝트를 같은·겹침 검사에서 뺀다(경로 다시 지정, K33-13). 없는 id면 무시한다."
        ),
    )


class FolderConflict(ContractModel):
    """폴더 확인에서 찾은 등록 충돌 하나."""

    project_id: NonEmptyStr
    relation: str = Field(description="same·parent·child(`KnownFolderConflictRelations`).")
    archived: bool = Field(default=False, description="보관(등록 해제)된 프로젝트인가.")
    folder: str | None = Field(default=None, description="그 프로젝트의 폴더.")


class FolderCheck(ContractModel):
    """폴더 확인 결과(ac-local-folders `check_folder` + 등록부). 폴더 안 파일 이름·내용은 없다."""

    input: str = Field(description="받은 입력 그대로.")
    path: str | None = Field(
        default=None, description="저장될 경로(정규화 + 링크를 푼 실제 경로). 경로가 아니면 null."
    )
    exists: bool = False
    is_dir: bool = False
    readable: bool = False
    writable: bool = False
    can_create: bool = Field(default=False, description="없고, 상위 폴더에 만들 수 있다.")
    hidden: bool = False
    link: bool = Field(default=False, description="입력 경로와 저장될 경로가 다르다(링크를 거침).")
    nearest_existing: str | None = Field(
        default=None,
        description=(
            "경로가 없을 때 가장 가까운 존재하는 상위 폴더(탐색 시작용, K33-13). "
            "탐색 범위 밖이면 null."
        ),
    )
    problem: str | None = Field(
        default=None, description="입력이 쓸 수 없는 경로인 이유 코드(예: relative, foreign_path)."
    )
    status: str = Field(description="확인 상태(`KnownFolderCheckStatuses`, 열린 문자열).")
    conflict: FolderConflict | None = Field(
        default=None, description="같은·겹치는 등록 프로젝트(taken·overlap_* 상태일 때)."
    )


class FolderEntry(ContractModel):
    """하위 폴더 하나. 파일은 목록에 없다."""

    name: str
    path: str = Field(description="목록 경로 + 이름(링크는 풀지 않음).")
    hidden: bool = False
    link: bool = Field(default=False, description="심볼릭 링크·접합점(등록하면 실제 경로로 저장).")
    locked: bool = Field(default=False, description="읽을 수 없어 들어갈 수 없다.")
    project_id: str | None = Field(default=None, description="이 폴더로 등록된 프로젝트 id.")


class FolderRoot(ContractModel):
    """탐색 시작 위치 하나(홈·드라이브·마운트 등)."""

    kind: str = Field(description="시작 위치 종류(열린 문자열, 예: home·root·drive·mount).")
    path: str
    label: str = ""


class FolderListing(ContractModel):
    """`GET /projects/folders?path=&hidden=` 응답: 하위 폴더 이름만(루프백 서버 전용)."""

    path: str = Field(description="목록 경로(정규화, 링크는 풀지 않음).")
    parent: str | None = Field(default=None, description="상위 폴더. 루트·탐색 범위 밖이면 null.")
    entries: list[FolderEntry] = Field(default_factory=list)
    roots: list[FolderRoot] = Field(default_factory=list, description="탐색 시작 위치.")
    truncated: bool = Field(default=False, description="개수·시간 상한으로 잘렸다.")
    timed_out: bool = Field(default=False, description="시간 상한으로 멈췄다.")
    hidden_count: int = Field(default=0, ge=0, description="숨겨서 뺀 폴더 수.")


class KnownFolderPickStatuses:
    """`FolderPickResult.status`의 알려진 값(design §PI.6, X35). **문서 상수**다.

    목록·enum이 아니다. 이름 → 값 표를 스키마 `x-constants.KNOWN_FOLDER_PICK_STATUSES`로 내보낸다.
    """

    PICKED: Final = "picked"
    """골랐다(`path`·`check`가 있다)."""
    CANCELLED: Final = "cancelled"
    UNAVAILABLE: Final = "unavailable"
    """쓸 수 있는 네이티브 대화상자가 없다(앱 안 찾아보기로 간다)."""
    BUSY: Final = "busy"
    """다른 선택 창이 열려 있다(한 번에 하나)."""
    TIMEOUT: Final = "timeout"
    FAILED: Final = "failed"


class FolderCapabilities(ContractModel):
    """`GET /projects/folders/capabilities` 응답: 이 서버에서 쓸 수 있는 폴더 고르기 방법."""

    browse: bool = Field(default=False, description="앱 안 찾아보기(`GET /projects/folders`).")
    native_dialog: bool = Field(
        default=False, description="서버가 데스크톱 폴더 대화상자를 띄울 수 있다."
    )
    provider: str | None = Field(
        default=None, description="쓸 대화상자 제공자 id(데이터·플러그인, 열린 문자열)."
    )
    reason: str | None = Field(
        default=None,
        description=(
            "쓸 수 없는 이유(열린 문자열, 예: remote·off·no_provider). 화면에 그대로 보인다."
        ),
    )


class FolderPickRequest(ContractModel):
    """`POST /projects/folders/pick` 요청(루프백 전용). 사용자가 고를 때까지 열려 있다."""

    initial: str | None = Field(default=None, description="처음 열 폴더(없으면 제공자 기본).")
    title: str | None = Field(default=None, description="대화상자 제목.")


class FolderPickResult(ContractModel):
    """`POST /projects/folders/pick` 응답. 고른 경로는 폴더 확인을 지나 `check`에 담긴다."""

    status: str = Field(description="결과(`KnownFolderPickStatuses`, 열린 문자열).")
    path: str | None = Field(default=None, description="고른 경로(picked일 때).")
    check: FolderCheck | None = Field(default=None, description="고른 경로의 폴더 확인 결과.")
    provider: str | None = Field(default=None, description="쓴 대화상자 제공자 id.")


# ---------------------------------------------------------------- 오류 details(§PI.2·§PI.4·§PI.5)


class ProjectFolderConflictDetails(ContractModel):
    """409 `project.folder_taken`·`project.folder_overlaps`의 `details`."""

    project_id: NonEmptyStr = Field(description="이미 그 폴더(또는 겹치는 폴더)를 가진 프로젝트.")
    relation: str | None = Field(
        default=None, description="겹침의 관계 parent·child(`folder_taken`이면 null)."
    )
    archived: bool = False
    folder: str | None = None


class ProjectFolderUnavailableDetails(ContractModel):
    """409 `project.folder_missing`의 `details`: 프로젝트 상태가 ready가 아니다."""

    project_id: NonEmptyStr
    status: ProjectStatus
    folder: str | None = None


class ProjectNotImportedDetails(ContractModel):
    """422 `project.not_imported`의 `details`: 실행 대상이 이 프로젝트 공간에 없다(K33-18)."""

    project_id: NonEmptyStr
    kind: NonEmptyStr = Field(description="실행 대상 정의 종류.")
    id: NonEmptyStr = Field(description="실행 대상 정의 id.")
    in_library: bool = Field(
        default=False,
        description="라이브러리에 같은 (종류, id)가 있다 — 화면은 [가져와서 실행]을 낸다.",
    )


class OutsideFolderPath(ContractModel):
    """프로젝트 폴더 밖을 가리킨 경로 값 하나."""

    value: str = Field(description="설정에 적힌 값 그대로.")
    resolved: str | None = Field(default=None, description="폴더 기준으로 푼 절대 경로.")
    pointer: JsonPointer = Field(description="값의 위치(설정 문서 기준 JSON Pointer).")
    layer: str | None = Field(
        default=None, description="값을 정한 설정 층 이름(열린 문자열, 예: 공통·프로젝트·팀·노드)."
    )
    node_id: str | None = None


class ProjectOutsideFolderDetails(ContractModel):
    """422 `project.outside_folder`의 `details`(경로 지킴, `x-path` 필드만 본다)."""

    project_id: NonEmptyStr
    folder: str
    paths: list[OutsideFolderPath] = Field(default_factory=list)


# ---------------------------------------------------------------- 이전 기록 넣기·개수(design §PI.8)


class AssignProjectRequest(ContractModel):
    """`POST /runs/assign-project`·`POST /conversations/assign-project` 요청.

    `ids`(그 기록만) 또는 `from_null: true`(프로젝트 없는 기록 전부) 중 하나만 준다. 루트 Run이면
    자식 Run도 함께 넣는다. 이미 다른 프로젝트인 기록은 `ids`로 명시했을 때만 옮긴다.
    `project_id`는 불투명 문자열이다(기능 모듈은 프로젝트를 모른다).
    """

    to: NonEmptyStr = Field(description="넣을 프로젝트 id.")
    ids: list[NonEmptyStr] | None = None
    from_null: bool = False

    @model_validator(mode="after")
    def _one_selector(self) -> "AssignProjectRequest":
        if (self.ids is not None) == self.from_null:
            raise ValueError("ids와 from_null 중 하나만 지정합니다")
        return self


class AssignProjectSkip(ContractModel):
    """넣지 않은 기록 하나."""

    id: NonEmptyStr
    reason: str = Field(description="열린 문자열(예: not_found, other_project, busy).")
    project_id: str | None = Field(default=None, description="그 기록의 지금 프로젝트.")


class AssignProjectResult(ContractModel):
    """assign-project 응답."""

    assigned: int = Field(ge=0, description="넣은 기록 수(함께 넣은 자식 Run 포함).")
    skipped: list[AssignProjectSkip] = Field(default_factory=list)


class ProjectCounts(ContractModel):
    """기능 하나의 기록 개수(`GET /runs/project-counts`·`GET /conversations/project-counts`)."""

    total: int = Field(default=0, ge=0)
    no_project: int = Field(default=0, ge=0, description="`project_id`가 null인 기록 수.")
    by_project: dict[str, int] = Field(
        default_factory=dict, description="project_id → 개수(없는·보관 프로젝트 id도 그대로)."
    )


# ---------------------------------------------------------------- (deprecated) 1.x 정의 범위 옮기기


class DefinitionMove(DefinitionKey):
    """(deprecated, 0.11.0) 정의 하나의 범위 바꾸기(필드 `project`를 고쳐 저장). null = 공용."""

    from_: str | None = Field(default=None, alias="from", description="지금 범위(null = 공용).")
    to: str | None = Field(default=None, description="옮길 범위(null = 공용).")
    required: bool = Field(
        default=False,
        description="옮기려는 그 정의면 true. false는 참조 때문에 함께 옮기기를 권하는 정의.",
    )


class MovePlanRequest(ContractModel):
    """(deprecated, 0.11.0) `POST /projects/move-plan` 요청. 다음 major에서 삭제."""

    kind: NonEmptyStr
    id: NonEmptyStr
    to: Slug | None = Field(default=None, description="옮길 프로젝트 id. null = 공용으로.")


class MovePlan(ContractModel):
    """(deprecated, 0.11.0) 옮기기 계획(순수 함수 `move_plan`의 결과). 저장하지 않는다.

    2.0에서 정의의 프로젝트 전용 범위가 없어졌다(K33-5). 옛 `project` 필드 정리는
    복사 계획(`CopyPlan`, `remove_source`)을 쓴다. 다음 major에서 삭제.
    """

    target: DefinitionKey = Field(description="옮기려는 정의.")
    to: str | None = Field(default=None, description="옮길 범위(null = 공용).")
    moves: list[DefinitionMove] = Field(default_factory=list)
    warnings: list[Issue] = Field(
        default_factory=list,
        description="옮긴 뒤 생길 범위 경고(project.shared_uses_project 등)나 검사 못 함 정보.",
    )


class DeletePlan(ContractModel):
    """(deprecated, 0.11.0) `POST /projects/{id}/delete-plan` 응답. 2.0 삭제 = 등록 해제(보관)."""

    project_id: NonEmptyStr
    definitions: list[DefinitionKey] = Field(
        default_factory=list, description="이 프로젝트 전용 정의(공용으로 옮기거나 함께 삭제)."
    )
    default_mode: ProjectDeleteMode = "move_to_shared"
    warnings: list[Issue] = Field(default_factory=list)


__all__ = [
    "IGNORED_PROJECT_KEYS",
    "PROJECT_MANIFEST_FORMAT",
    "AssignProjectRequest",
    "AssignProjectResult",
    "AssignProjectSkip",
    "CopyApplyItem",
    "CopyApplyItemResult",
    "CopyApplyRequest",
    "CopyApplyResult",
    "CopyPlan",
    "CopyPlanItem",
    "CopyPlanRequest",
    "DefinitionKey",
    "DefinitionMove",
    "DefinitionScope",
    "DeletePlan",
    "FolderCapabilities",
    "FolderCheck",
    "FolderCheckRequest",
    "FolderConflict",
    "FolderEntry",
    "FolderListing",
    "FolderPickRequest",
    "FolderPickResult",
    "FolderRoot",
    "KnownCopyActions",
    "KnownCopyStatuses",
    "KnownCopyTargetStates",
    "KnownFolderCheckStatuses",
    "KnownFolderConflictRelations",
    "KnownFolderPickStatuses",
    "KnownProjectStatuses",
    "MovePlan",
    "MovePlanRequest",
    "OutsideFolderPath",
    "Project",
    "ProjectCounts",
    "ProjectCreate",
    "ProjectDeleteMode",
    "ProjectFolderConflictDetails",
    "ProjectFolderUnavailableDetails",
    "ProjectManifest",
    "ProjectNotImportedDetails",
    "ProjectOutsideFolderDetails",
    "ProjectPreferences",
    "ProjectRegistration",
    "ProjectStatus",
    "ProjectUpdate",
    "ProjectView",
    "ignored_project_keys",
]

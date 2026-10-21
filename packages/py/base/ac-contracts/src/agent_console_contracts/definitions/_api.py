"""정의(에이전트·팀 구성·설정·버전·프리셋) REST DTO(design §5.2, `/api/v1`)."""

from typing import Any, Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr, Slug
from agent_console_contracts.resources import ResourceBundle

from ._issues import Issue
from ._models import AgentSettings, Graph

type ConflictPolicy = Literal["skip", "overwrite", "rename"]
"""같은 id가 이미 있을 때(프리셋 적용·가져오기). skip = 기존 정의를 건드리지 않음."""

type ItemAction = Literal["created", "overwritten", "renamed", "skipped", "failed"]

type DiffOp = Literal["add", "remove", "replace"]
"""문서 비교 변경 하나의 종류(JSON Patch 어휘 일부, design §2R.9)."""


class VersionedGraph(ContractModel):
    """`GET/PUT /graphs/{id}`, `POST /graphs` 응답. `version_hash`는 ETag와 같은 값."""

    graph: Graph
    version_hash: NonEmptyStr
    saved_at: float | None = None


class DuplicateGraphRequest(ContractModel):
    """`POST /graphs/{id}/duplicate` 요청. 응답은 새 그래프 `VersionedGraph`(201)."""

    id: Slug = Field(description="새 팀 구성 id. 이미 있으면 409 already_exists.")
    name: NonEmptyStr = Field(description="새 팀 구성 이름.")


class GraphValidationSummary(ContractModel):
    """팀 구성 검증 결과 요약(엔진 검증 + 팀 검증을 합친 것)."""

    blocks_run: bool = Field(description="실행을 막는 이슈가 있는지.")
    error_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    codes: list[str] = Field(
        default_factory=list, description="나온 이슈 코드(중복 없음, 표시·필터용)."
    )


class GraphSummary(ContractModel):
    """`GET /graphs` 목록 항목."""

    id: NonEmptyStr
    name: str
    description: str = ""
    labels: list[str] = Field(default_factory=list)
    version_hash: NonEmptyStr
    saved_at: float | None = None
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    entry_labels: list[str] | None = Field(
        default=None,
        description="입구 노드 표시 이름(입구 연결의 도착 노드). null = 계산하지 않음.",
    )
    validation: GraphValidationSummary | None = Field(
        default=None, description="검증 요약. null = 계산하지 않음(`?validate=false` 등)."
    )
    project: str | None = Field(
        default=None,
        description="정의의 프로젝트 id(0.8.0). null = 공용. 웹이 이 값으로 목록을 거른다.",
    )


class DefinitionVersion(ContractModel):
    """정의 버전 이력 항목. 목록(`GET /graphs/{id}/versions`)은 `content` 없이,
    단건(`GET /graphs/{id}/versions/{version_hash}`)은 `content`를 담는다."""

    kind: NonEmptyStr
    id: NonEmptyStr
    version_hash: NonEmptyStr
    saved_at: float
    message: str = ""
    content: JsonObject | None = None


class VersionConflictDetails(ContractModel):
    """`version_conflict`(HTTP 412) 오류의 `error.details`. 서버의 현재 버전 요약."""

    current_version_hash: NonEmptyStr
    saved_at: float | None = None
    node_count: int | None = None
    edge_count: int | None = None


class SettingsLayerInfo(ContractModel):
    """유효 설정을 만든 층 하나. 층 목록은 데이터다(코드에 고정된 층 이름 없음)."""

    id: NonEmptyStr = Field(description="층 id(출처 표시 키).")
    label: str = Field(default="", description="화면 이름.")
    source: str | None = Field(
        default=None, description="층 값이 온 곳(예: 정의 종류/id, 파일). 표시용."
    )


class EffectiveSettings(ContractModel):
    """층을 병합한 유효 설정. `provenance`는 잎 값의 JSON Pointer → 층 id."""

    value: AgentSettings
    provenance: dict[str, str] = Field(default_factory=dict)
    layers: list[SettingsLayerInfo] = Field(default_factory=list)
    warnings: list[Issue] = Field(
        default_factory=list, description="병합 경고(예: 아래 층이 실행 범위를 넓힘). path = 필드."
    )
    inapplicable: list[str] = Field(
        default_factory=list,
        description="이 자리(예: 위임받는 노드)에서 적용되지 않는 필드의 JSON Pointer 목록.",
    )


class PresetSummary(ContractModel):
    """`GET /presets` 목록 항목. 프리셋은 데이터이며 지워도 시스템이 동작한다."""

    id: NonEmptyStr
    name: str
    description: str = ""
    labels: list[str] = Field(default_factory=list)
    item_count: int = Field(default=0, ge=0)
    items: list[JsonObject] = Field(
        default_factory=list, description="항목 요약(종류·id 등). 형식은 프리셋 패키지가 정한다."
    )
    # 0.8.0(design §5.2R.3 #8). 값은 프리셋 매니페스트(데이터)에서 온다.
    badges: list[str] = Field(
        default_factory=list, description="카드에 보일 짧은 배지 글자(예: 체험, 추천)."
    )
    featured: int | None = Field(
        default=None,
        description="'바로 시작' 순서(작을수록 앞). null = 바로 시작에 없음, 목록 순서대로.",
    )
    start_graph: str | None = Field(
        default=None, description="적용한 뒤 바로 열 팀 구성 id(프리셋 안 id). null = 열지 않음."
    )


class ApplyPresetRequest(ContractModel):
    """`POST /presets/{id}/apply` 요청."""

    on_conflict: ConflictPolicy = "skip"
    project: Slug | None = Field(
        default=None,
        description="만든 정의에 찍을 프로젝트 id(0.8.0). 생략 = 공용(지금과 같음).",
    )


class AppliedItemInfo(ContractModel):
    """정의 하나를 쓴 결과(프리셋 적용·가져오기 공통)."""

    source: str = Field(description="출처 안 경로·키.")
    kind: NonEmptyStr = Field(description="정의 종류 이름.")
    id: str = Field(description="출처 안 id 또는 제안 id.")
    target_id: str | None = Field(default=None, description="워크스페이스에 쓴 id.")
    action: ItemAction
    error: str | None = None


class ApplyPresetResult(ContractModel):
    """`POST /presets/{id}/apply` 응답."""

    preset_id: NonEmptyStr
    items: list[AppliedItemInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DefinitionReference(ContractModel):
    """정의를 쓰는 곳 하나(사용처 화면, 삭제 확인)."""

    kind: NonEmptyStr = Field(description="쓰는 쪽 정의 종류 이름.")
    id: NonEmptyStr
    name: str = ""
    node_ids: list[str] = Field(
        default_factory=list, description="그래프 안에서 쓰는 노드(그래프일 때)."
    )
    layer: str | None = Field(default=None, description="설정 층 첨부로 쓰면 그 층 id.")


class MergeStrategyInfo(ContractModel):
    """`GET /merge-strategies` 항목: 설정 `settings_merge`에 쓸 수 있는 병합 전략 이름 하나.

    목록은 서버의 전략 표(기본 + 플러그인)에서 온다. 계약에 고정 목록은 없다.
    """

    id: NonEmptyStr = Field(description="전략 이름(`settings_merge` 값, 스키마 `x-merge` 값).")
    description: str = Field(default="", description="짧은 설명(표시용).")


class BundlePreview(ContractModel):
    """노드 실행 묶음 미리보기(`GET /graphs/{id}/nodes/{node}/bundle-preview`, 초안 `POST`)."""

    bundle: ResourceBundle
    warnings: list[Issue] = Field(
        default_factory=list, description="묶음 경고(받지 않는 칸, 세션 공유 칸 등)."
    )


class DraftGraphRequest(ContractModel):
    """저장하지 않은 초안 그래프로 계산하는 요청(검증·계획 미리보기). 저장하지 않는다."""

    graph: Graph


class DraftNodeRequest(ContractModel):
    """초안 그래프의 노드 하나로 계산하는 요청(유효 설정·묶음 미리보기). 저장하지 않는다."""

    graph: Graph
    node_id: NonEmptyStr


class DiffChange(ContractModel):
    """정의 문서 변경 하나. 비밀 위치면 `secret` = true이고 before·after는 가린 값이다."""

    op: DiffOp
    path: str = Field(
        pattern=r"^(/.*)?$", description="정의 문서 기준 RFC 6901 JSON Pointer(예: /nodes/3/label)."
    )
    before: Any = Field(default=None, description="이전 값(add면 없음).")
    after: Any = Field(default=None, description="새 값(remove면 없음).")
    secret: bool = False


class ContentChange(ContractModel):
    """본문 파일 변경 하나(해시만 비교). 한쪽 해시가 없으면 추가·삭제."""

    path: NonEmptyStr
    before_hash: str | None = None
    after_hash: str | None = None


class DefinitionDiff(ContractModel):
    """두 버전 비교 결과(`GET /{kind}/{id}/versions/{a}/diff/{b}`)."""

    kind: NonEmptyStr
    id: NonEmptyStr
    from_hash: NonEmptyStr
    to_hash: NonEmptyStr
    changes: list[DiffChange] = Field(default_factory=list)
    content_changes: list[ContentChange] = Field(default_factory=list)


class RestoreVersionRequest(ContractModel):
    """`POST /{kind}/{id}/versions/{hash}/restore` 요청. 복원은 새 버전으로 저장된다."""

    message: str | None = Field(default=None, description="버전 메시지. 비우면 서버 기본 문구.")

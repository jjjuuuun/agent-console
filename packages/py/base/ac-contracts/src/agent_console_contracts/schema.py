"""계약 모델 → JSON Schema(2020-12) 생성과 드리프트 검사.

생성물은 단일 파일 `agent-console.schema.json`이다. 모든 모델은 `$defs`에 있고,
루트의 `x-constants`에 TS 쪽에도 필요한 상수를, `x-modules`에 하위 모듈별 모델 이름을 담는다
(TS 하위 경로 `@agent-console/contracts/<하위 모듈>` 생성에 쓴다).
"""

import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, models_json_schema

from . import (
    architecture,
    chat,
    common,
    definitions,
    exports,
    imports,
    logs,
    memory,
    modules,
    projects,
    resources,
    runs,
    usage,
)
from .common import X_UI, X_UI_TIERS
from .constants import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    LOG_EVENT_ORDERS,
    LOG_PROJECT_UNGROUPED,
    RUN_ORIGINS,
    USAGE_REPORT_PARTS,
    WS_AUTH_CLOSE_CODES,
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_UNAUTHORIZED,
    ErrorCodes,
    KnownIssueCodes,
    KnownSuggestionIds,
)
from .user_text import user_text_rules_data

_SUBMODULES: dict[str, ModuleType] = {
    "common": common,
    "resources": resources,
    "logs": logs,
    "definitions": definitions,
    "runs": runs,
    "usage": usage,
    "projects": projects,
    "chat": chat,
    "exports": exports,
    "imports": imports,
    "architecture": architecture,
    "memory": memory,
    "modules": modules,
}

SCHEMA_FILENAME = "agent-console.schema.json"
SCHEMA_ID = "urn:agent-console:contracts"

CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    # 공통
    common.ErrorInfo,
    common.ErrorResponse,
    definitions.Issue,
    common.Usage,
    common.PortDef,
    common.PortSpec,
    common.Endpoint,
    common.UiHints,
    common.Fix,
    # 정의
    definitions.Agent,
    definitions.Limits,
    definitions.Graph,
    definitions.NodeSpec,
    definitions.EdgeSpec,
    definitions.NodeLayout,
    definitions.EdgeLayout,
    definitions.GraphUiLayout,
    definitions.WorkspaceSettings,
    definitions.AgentSettings,
    definitions.AgentDefaults,
    definitions.GraphSettings,
    definitions.ObserveSettings,
    definitions.CollectorSetting,
    definitions.ChatSettings,
    definitions.EditorSettings,
    definitions.DelegationSettings,
    definitions.InteractionSettings,
    definitions.UsageSettings,
    definitions.UiPreferences,
    definitions.VersionUiSettings,
    definitions.NotificationSettings,
    definitions.UsageIndicatorSettings,
    definitions.UsageIndicatorColorRule,
    definitions.SecretRuleSettings,
    definitions.ProjectPreferences,
    # 프로젝트(0.8.0)
    projects.Project,
    projects.ProjectCreate,
    projects.ProjectUpdate,
    projects.MovePlanRequest,
    projects.MovePlan,
    projects.DeletePlan,
    # 리소스
    resources.Resource,
    resources.ResourceAttachment,
    resources.ResourceBundle,
    resources.ResourceSummary,
    resources.ResourceFile,
    # 디스크립터
    runs.NodeTypeDescriptor,
    runs.EdgeTypeDescriptor,
    runs.BackendDescriptor,
    runs.CollectorDescriptor,
    runs.ModelInfo,
    runs.DelegationStrategyDescriptor,
    resources.ResourceTypeDescriptor,
    runs.InteractionKindDescriptor,
    runs.ConditionOperatorDescriptor,
    runs.ConditionSpec,
    usage.UsageSourceDescriptor,
    runs.BackendUnresolvedDetails,
    # 실행 백엔드 준비 상태·연결 테스트(0.8.0, ux-overhaul §15.8)
    runs.BackendReadiness,
    runs.ReadinessCheck,
    runs.BackendProbeRequest,
    runs.BackendProbeResult,
    # 실행 백엔드 로그인·로그아웃(0.8.0, ux-overhaul §15.9 F14)
    runs.LoginMethodInfo,
    runs.ReadinessAction,
    runs.BackendLoginStartRequest,
    runs.BackendLoginSession,
    runs.BackendLoginInput,
    runs.BackendLogoutResult,
    # 런타임
    runs.Run,
    runs.NodeRun,
    runs.RunSnapshot,
    runs.WaitInfo,
    # 상호작용
    runs.Interaction,
    runs.InteractionGrant,
    runs.RespondInteractionRequest,
    runs.ReviewDecision,
    # 채팅
    chat.Conversation,
    chat.ConversationSummary,
    chat.ChatTurn,
    chat.CreateConversationRequest,
    chat.UpdateConversationRequest,
    chat.PostMessageRequest,
    chat.QueuedMessage,
    # 관측
    usage.UsageWindowSnapshot,
    usage.UsageReport,
    usage.UsageSourceInfo,
    runs.Trace,
    runs.HandoffMatrix,
    # 가져오기
    imports.ImportSourceDescriptor,
    imports.ImportPreviewRequest,
    imports.ImportPreview,
    imports.ImportRequest,
    imports.ImportResult,
    # 내보내기
    exports.ExporterDescriptor,
    exports.ExportRequest,
    exports.ExportPlan,
    exports.ExportRootInfo,
    exports.ExportWriteRequest,
    exports.ExportResult,
    # 로그(design §4R.9)
    logs.LogSettings,
    logs.LogTaxonomy,
    logs.LogDashboard,
    logs.LogEvent,
    logs.LogEventPage,
    logs.LogEventDetail,
    logs.LogEvidenceLink,
    logs.LogDocumentRef,
    logs.LogSourceDescriptor,
    logs.LogClassifierDescriptor,
    logs.LogSourceInfo,
    logs.LogScanReport,
    logs.LogSessionSummary,
    logs.LogTimeline,
    logs.LogAggregateRequest,
    logs.LogAggregateRow,
    logs.LogQuerySchema,
    logs.LogArchive,
    # 구조도(design §5.5R.2.4, 0.9.0)
    architecture.ArchitectureSettings,
    architecture.ArchitectureProfile,
    architecture.ArchitectureProfileInfo,
    architecture.ArchitectureProfileList,
    architecture.ArchitectureProfileDetail,
    architecture.ArchitectureProfileCheckRequest,
    architecture.ArchitectureProfileCheckResult,
    architecture.ArchitectureProjectRequest,
    architecture.ArchitectureView,
    architecture.ArchitectureMembership,
    architecture.ArchitectureScopeTooLargeDetails,
    # 공유 메모리(design §5.7R.5, 0.10.0)
    memory.MemorySettings,
    memory.MemoryAccessConfig,
    memory.MemoryScopeKindSpec,
    memory.MemoryScopeKindInfo,
    memory.MemoryScopeKindList,
    memory.MemoryScopeRef,
    memory.MemoryAuthor,
    memory.MemoryEntry,
    memory.MemoryEntrySummary,
    memory.MemoryEntryPage,
    memory.MemoryVersion,
    memory.MemoryVersionSummary,
    memory.MemoryScopeSummary,
    memory.MemoryWriteRequest,
    memory.MemoryUpdateRequest,
    memory.MemoryMoveRequest,
    memory.MemoryRetentionRule,
    memory.MemoryRetentionPlanRequest,
    memory.MemoryRetentionPlan,
    memory.MemoryRetentionResult,
    memory.MemoryImportResult,
    memory.MemorySecretRejectedDetails,
    memory.MemoryTagList,
    memory.MemoryEventPayload,
    memory.MemoryChanged,
    # 이벤트
    runs.RunEvent,
    runs.KnownRunEvent,
    # 호스트·모듈
    modules.ModuleInfo,
    modules.FeatureUnavailableDetails,
    modules.ModuleOptionsView,
    # WS
    modules.WsClientMessage,
    modules.WsServerMessage,
    # REST DTO
    modules.BootstrapResponse,
    modules.HealthResponse,
    runs.ResolvePortsRequest,
    runs.CreateRunRequest,
    definitions.VersionedGraph,
    definitions.GraphSummary,
    definitions.DefinitionVersion,
    definitions.VersionConflictDetails,
    definitions.EffectiveSettings,
    definitions.DefinitionReference,
    modules.ServerInfo,
    definitions.DuplicateGraphRequest,
    definitions.MergeStrategyInfo,
    definitions.GraphValidationSummary,
    definitions.BundlePreview,
    runs.TeamPlanSummary,
    definitions.DraftGraphRequest,
    definitions.DraftNodeRequest,
    runs.ResumeOptions,
    runs.ResumeRunRequest,
    definitions.DefinitionDiff,
    definitions.RestoreVersionRequest,
)
"""스키마에 포함하는 최상위 모델. 여기서 참조되는 하위 모델도 `$defs`에 들어간다."""


class _Generator(GenerateJsonSchema):
    """필드 자동 제목("Node Id" 등)을 넣지 않는다. 명시한 `title`만 남는다."""

    def field_title_should_be_set(self, schema: Any) -> bool:
        return False


def _upper_constants(holder: type) -> dict[str, str]:
    """상수 모음 클래스의 대문자 속성 → 값 표(정의 순서 유지)."""
    return {name: value for name, value in vars(holder).items() if name.isupper()}


def _error_codes() -> dict[str, str]:
    return _upper_constants(ErrorCodes)


def _submodule_of(obj: object) -> str | None:
    module = getattr(obj, "__module__", None)
    if not isinstance(module, str) or not module.startswith(f"{__package__}."):
        return None
    head = module[len(__package__) + 1 :].split(".", 1)[0]
    return head if head in CONTRACT_SUBMODULES else None


def submodule_definitions(names: Sequence[str]) -> dict[str, list[str]]:
    """스키마 `$defs` 이름 → 그 모델을 정의한 계약 하위 모듈로 묶는다(TS 하위 경로 생성용).

    반환: `CONTRACT_SUBMODULES` 순서의 {하위 모듈: 정렬된 이름 목록}.
    예외: 어느 하위 모듈에도 정의되지 않은 이름이 있으면 `ValueError`(새 모델의 자리를 정하라는 뜻).
    """
    owner: dict[str, str] = {}
    for sub in CONTRACT_SUBMODULES:
        namespace = vars(_SUBMODULES[sub])
        for name in getattr(_SUBMODULES[sub], "__all__", ()):
            if _submodule_of(namespace[name]) == sub:
                owner[name] = sub
    missing = [name for name in names if name not in owner]
    if missing:
        raise ValueError(f"하위 모듈이 정해지지 않은 계약 모델: {missing}")
    grouped: dict[str, list[str]] = {sub: [] for sub in CONTRACT_SUBMODULES}
    for name in sorted(names):
        grouped[owner[name]].append(name)
    return grouped


def build_schema() -> dict[str, Any]:
    """모든 계약 모델의 JSON Schema 문서를 만든다(결정적: 같은 코드 → 같은 결과)."""
    _, top = models_json_schema(
        [(model, "validation") for model in CONTRACT_MODELS],
        ref_template="#/$defs/{model}",
        schema_generator=_Generator,
    )
    defs = top.get("$defs", {})
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "AgentConsoleContracts",
        "description": (
            "Agent Console 공용 계약. 자동 생성 — 직접 수정하지 말 것(uv run poe contracts)."
        ),
        "type": "object",
        "additionalProperties": False,
        "x-constants": {
            "CONTRACTS_VERSION": CONTRACTS_VERSION,
            "CONTRACT_VERSIONS": dict(CONTRACT_VERSIONS),
            "USAGE_REPORT_PARTS": list(USAGE_REPORT_PARTS),
            "KNOWN_RUN_EVENT_TYPES": list(runs.KNOWN_RUN_EVENT_TYPES),
            "KNOWN_MEMORY_EVENT_TYPES": list(memory.KNOWN_MEMORY_EVENT_TYPES),
            "MEMORY_ACCESS_OPS": list(memory.MEMORY_ACCESS_OPS),
            "MEMORY_CONTEXT_FIELDS": list(memory.MEMORY_CONTEXT_FIELDS),
            "KNOWN_MEMORY_CONTEXT_FIELDS": _upper_constants(memory.KnownMemoryContextFields),
            "MEMORY_SCOPE_SEPARATOR": memory.MEMORY_SCOPE_SEPARATOR,
            "MEMORY_ENTRY_SORTS": list(memory.MEMORY_ENTRY_SORTS),
            "RUN_ORIGINS": list(RUN_ORIGINS),
            "LOG_EVENT_ORDERS": list(LOG_EVENT_ORDERS),
            "LOG_PROJECT_UNGROUPED": LOG_PROJECT_UNGROUPED,
            "ERROR_CODES": _error_codes(),
            "HTTP_STATUS_BY_ERROR_CODE": dict(HTTP_STATUS_BY_ERROR_CODE),
            "KNOWN_ISSUE_CODES": _upper_constants(KnownIssueCodes),
            "KNOWN_SUGGESTION_IDS": _upper_constants(KnownSuggestionIds),
            "WS_CLOSE_UNAUTHORIZED": WS_CLOSE_UNAUTHORIZED,
            "WS_CLOSE_FORBIDDEN": WS_CLOSE_FORBIDDEN,
            "WS_AUTH_CLOSE_CODES": list(WS_AUTH_CLOSE_CODES),
            "X_UI": X_UI,
            "X_UI_TIERS": list(X_UI_TIERS),
            "USER_TEXT_RULES": user_text_rules_data(),
        },
        "x-modules": submodule_definitions(sorted(defs)),
        "$defs": {name: defs[name] for name in sorted(defs)},
    }


def render_schema() -> str:
    """`build_schema()`를 파일에 쓰는 텍스트(UTF-8, LF, 들여쓰기 2)로 만든다."""
    return json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n"


def export_schemas(out_dir: str | Path) -> list[Path]:
    """JSON Schema 파일을 `out_dir`에 쓴다. 쓴 파일 경로 목록을 돌려준다.

    예외: 디렉터리를 만들거나 쓸 수 없으면 `OSError`.
    """
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / SCHEMA_FILENAME
    path.write_bytes(render_schema().encode("utf-8"))
    return [path]


def check_schemas(out_dir: str | Path) -> list[Path]:
    """`out_dir`의 파일이 지금 코드로 생성한 내용과 같은지 확인한다.

    다른(또는 없는) 파일 목록을 돌려준다. 빈 목록이면 최신 상태.
    """
    path = Path(out_dir) / SCHEMA_FILENAME
    if not path.is_file():
        return [path]
    current = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return [] if current == render_schema() else [path]

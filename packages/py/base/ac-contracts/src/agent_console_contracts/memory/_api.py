"""메모리 REST DTO·이벤트 payload·문서 상수(design §5.7R.5).

경로(메모리 모듈 `mod-memory`, 꺼지면 404): `GET /memory/scope-kinds` → `MemoryScopeKindList`,
`GET /memory/scopes` → `MemoryScopeSummary[]`, `GET /memory/entries` → `MemoryEntryPage`,
`POST /memory/entries`(`MemoryWriteRequest`) / `PUT /memory/entries/{id}`(`MemoryUpdateRequest`,
`If-Match: <version>`) → `MemoryEntry`, `POST /memory/entries/{id}/move`(`MemoryMoveRequest`),
`GET /memory/entries/{id}/versions` → `MemoryVersionSummary[]`, `POST /memory/retention/plan` →
`MemoryRetentionPlan`, `POST /memory/retention/apply` → `MemoryRetentionResult`,
`POST /memory/import` → `MemoryImportResult`, `GET /memory/tags` → `MemoryTagList`.
WS 메시지 `memory.changed`의 payload는 `MemoryChanged`.

실행 이벤트 `memory.*`의 payload는 `MemoryEventPayload`다. RunEvent `type`은 열린 문자열이고
`runs`의 알려진 이벤트 목록(`KNOWN_RUN_EVENT_TYPES`)에는 넣지 않는다(design K57-10). payload에는
**본문·검색어 원문을 싣지 않는다**(크기·해시만).
"""

from typing import Final, Literal, get_args

from pydantic import Field, model_validator

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr, Slug
from agent_console_contracts.definitions import Issue

from ._models import (
    MemoryAccessContext,
    MemoryAuthorKind,
    MemoryChangeOp,
    MemoryScopeRef,
)
from ._settings import MemoryAccessOp, MemoryRetentionAction


class MemoryScopeKindInfo(ContractModel):
    """범위 종류 목록 항목(병합 결과 하나). `GET /memory/scope-kinds`."""

    kind: Slug = Field(description="범위 종류 id(사용자 설정·플러그인의 키).")
    label: str = Field(description="표시 이름(데이터).")
    description: str = ""
    id: str | None = Field(
        default=None,
        description=(
            "범위 id 틀(접근 맥락의 JSON 포인터 틀, 예 `{/project_id}`). 빈 문자열 = 범위 하나. "
            "계산 범위(플러그인)는 틀이 없어 null."
        ),
    )
    origin: NonEmptyStr = Field(
        description="출처(열린 문자열): `default`(패키지 기본), `plugin:<배포 이름>`, `user`."
    )
    overrides: str | None = Field(
        default=None, description="같은 id의 기본·플러그인 종류를 덮어썼으면 그 출처. 아니면 null."
    )
    disabled: bool = Field(
        default=False, description="사용자 설정에서 null로 끈 종류(목록에 함께 실을 때만 true)."
    )
    context_fields: list[str] = Field(
        default_factory=list,
        description=(
            "틀이 읽는 접근 맥락 필드 이름(`MEMORY_CONTEXT_FIELDS` 중). 웹이 프로젝트·팀 범위를 "
            "이름이 아니라 이 값으로 판단한다. 계산 범위는 빈 목록(모든 프로젝트에서만 보임)."
        ),
    )


class MemoryScopeKindList(ContractModel):
    """`GET /memory/scope-kinds` 응답."""

    kinds: list[MemoryScopeKindInfo] = Field(
        default_factory=list, description="병합 순서(기본 → 플러그인 → 사용자)."
    )
    include_defaults: bool = Field(default=True, description="설정의 기본 범위 종류 사용 값.")


class MemoryWriteRequest(ContractModel):
    """`POST /memory/entries` 본문(만들기). 같은 범위·키가 있으면 409."""

    scope: MemoryScopeRef
    key: NonEmptyStr
    content: str
    content_type: str | None = Field(default=None, description="생략 = 기본 형식.")
    tags: list[str] | None = None
    pinned: bool | None = None


class MemoryUpdateRequest(ContractModel):
    """`PUT /memory/entries/{id}` 본문(고치기, `If-Match: <version>`). 생략한 필드는 그대로."""

    content: str | None = None
    content_type: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None


class MemoryMoveRequest(ContractModel):
    """`POST /memory/entries/{id}/move` 본문: 키·범위 바꾸기(둘 중 하나 이상)."""

    to_scope: MemoryScopeRef | None = None
    to_key: str | None = None

    @model_validator(mode="after")
    def _needs_target(self) -> "MemoryMoveRequest":
        if self.to_scope is None and not self.to_key:
            raise ValueError("to_scope와 to_key 중 하나는 있어야 한다")
        return self


class MemoryRetentionPlanItem(ContractModel):
    """정리 계획의 항목 하나: 어느 규칙이 무엇을 할지."""

    entry_id: NonEmptyStr
    scope: MemoryScopeRef
    key: NonEmptyStr
    version: int = Field(ge=1, description="판단한 때의 버전(적용 때 바뀌었으면 건너뜀).")
    rule: NonEmptyStr = Field(description="맞은 규칙 id(선언 순서의 첫 규칙).")
    action: MemoryRetentionAction


class MemoryRetentionPlanRequest(ContractModel):
    """`POST /memory/retention/plan`·`/apply` 본문. 규칙을 주면 저장 전 규칙으로 시험한다."""

    rules: list[JsonObject] | None = Field(
        default=None,
        description=(
            "시험할 정리 규칙(`MemoryRetentionRule` 모양, 형식 오류도 이슈로 알림). "
            "생략 = 저장된 설정의 규칙."
        ),
    )
    limit: int | None = Field(default=None, ge=1, description="계획 항목 최대 수(응답 크기).")


class MemoryRetentionPlan(ContractModel):
    """정리 미리보기(dry run) 결과."""

    items: list[MemoryRetentionPlanItem] = Field(default_factory=list)
    count: int = Field(ge=0, description="맞은 항목 전체 수(`items`가 잘렸어도 전체).")
    truncated: bool = Field(default=False, description="`items`를 `limit`에서 잘랐는지.")
    issues: list[Issue] = Field(default_factory=list, description="규칙 검사 문제.")


class MemoryRetentionResult(ContractModel):
    """정리 적용 결과. 적용은 버전(쓴 주체 system, 표시 = 규칙 id)으로 남아 되돌릴 수 있다."""

    archived: int = Field(default=0, ge=0)
    deleted: int = Field(default=0, ge=0)
    skipped: int = Field(
        default=0, ge=0, description="계획 뒤 바뀌어(버전 다름·고정됨) 건너뛴 항목 수."
    )
    issues: list[Issue] = Field(default_factory=list)


MemoryImportPolicy = Literal["skip", "overwrite", "rename"]
"""가져오기에서 같은 범위·키가 있을 때: 건너뜀·덮어씀(새 버전)·이름 바꿔 만듦."""


class MemoryImportProblem(ContractModel):
    """가져오기에서 받지 못한 파일 하나(본문·찾은 비밀 값은 싣지 않는다)."""

    path: str = Field(description="zip 안 경로.")
    code: NonEmptyStr = Field(description="사유 코드(예: `memory.invalid_key`).")
    message: str = ""


class MemoryImportResult(ContractModel):
    """`POST /memory/import` 결과. `dry_run=true`로 부르면 쓰지 않고 같은 수를 센다(미리보기)."""

    dry_run: bool = Field(default=False, description="미리보기였는지(true면 아무것도 쓰지 않음).")
    created: int = Field(default=0, ge=0)
    overwritten: int = Field(default=0, ge=0)
    renamed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    errors: list[MemoryImportProblem] = Field(default_factory=list)


MemorySecretField = Literal["content", "key", "tags"]
"""비밀 의심 값이 나온 곳(항목 필드 이름)."""


class MemorySecretRejectedDetails(ContractModel):
    """오류 `memory.secret_rejected`의 `details`. **찾은 값·본문 조각은 싣지 않는다**."""

    field: MemorySecretField | None = Field(
        default=None, description="비밀 의심 값이 나온 필드. 모르면 null(화면은 일반 문구)."
    )
    rules: list[str] = Field(default_factory=list, description="맞은 비밀 규칙 id.")


class MemoryTagCount(ContractModel):
    """태그 하나와 그 태그가 붙은 항목 수."""

    tag: NonEmptyStr
    entries: int = Field(ge=0)


class MemoryTagList(ContractModel):
    """`GET /memory/tags?scope=&include_archived=` 응답(필터 선택지). 항목 수 내림차순."""

    tags: list[MemoryTagCount] = Field(default_factory=list)
    truncated: bool = Field(default=False, description="상한에서 잘랐는지.")


MEMORY_ENTRY_SORTS: Final[tuple[str, ...]] = ("updated_at", "created_at", "key", "bytes", "version")
"""목록 질의 `sort`의 값(서버 정렬, 커서 쪽 넘김과 함께 맞게). 방향은 `order`(`asc`·`desc`, 기본
`updated_at`·`desc`). 모르는 값은 422."""


MemoryEventStatus = Literal[
    "ok",
    "denied",
    "not_found",
    "conflict",
    "too_large",
    "secret_rejected",
    "rate_limited",
    "scope_unavailable",
    "error",
]
"""도구 호출 결과 상태. ok 밖의 값은 도구 결과 `is_error`와 사유 코드 `memory.<값>`에 대응한다."""


class MemoryEventPayload(ContractModel):
    """RunEvent `memory.<op>`의 payload: 에이전트 메모리 도구 호출 하나.

    **본문·검색어 원문 없음**: 크기(`bytes`·`query_chars`)와 해시(`sha256`·`query_sha256`)만 싣는다.
    로그 대응표는 이 값으로 문서 표지 `{kind: memory, path: <범위 종류>/<범위 id>/<키>}`를 만든다.
    """

    op: MemoryAccessOp
    status: MemoryEventStatus
    scope: MemoryScopeRef | None = Field(default=None, description="쓴·읽은 범위(모르면 null).")
    key: str | None = None
    entry_id: str | None = None
    version: int | None = Field(default=None, ge=1, description="쓴·읽은 버전(충돌이면 현재 버전).")
    bytes: int | None = Field(default=None, ge=0, description="본문 바이트 수.")
    sha256: str | None = Field(default=None, description="본문 sha256(16진수).")
    results: int | None = Field(default=None, ge=0, description="검색 결과 수.")
    query_chars: int | None = Field(default=None, ge=0, description="검색어 글자 수.")
    query_sha256: str | None = Field(default=None, description="검색어 sha256(16진수).")
    tool: str | None = Field(default=None, description="사용자가 정한 도구 이름.")
    tool_use_id: str | None = Field(default=None, description="모델의 도구 호출 id.")
    duration_ms: float | None = Field(default=None, ge=0, description="처리 시간(ms).")


class MemoryChanged(ContractModel):
    """WS 메시지 `memory.changed`의 payload: 항목 하나가 바뀜(본문 없음, 웹 목록 갱신용)."""

    scope: MemoryScopeRef
    key: NonEmptyStr
    entry_id: NonEmptyStr
    version: int = Field(ge=1, description="바뀐 뒤 버전(완전 삭제면 마지막 버전).")
    op: MemoryChangeOp
    author_kind: MemoryAuthorKind


MEMORY_EVENT_PREFIX: Final = "memory."
"""메모리 RunEvent `type` 접두. `type` = 접두 + `MemoryEventPayload.op`."""

KNOWN_MEMORY_EVENT_TYPES: Final[tuple[str, ...]] = tuple(
    f"{MEMORY_EVENT_PREFIX}{op}" for op in get_args(MemoryAccessOp)
)
"""메모리 RunEvent type 목록(문서 상수). `runs`의 `KNOWN_RUN_EVENT_TYPES`에는 넣지 않는다."""

MEMORY_CONTEXT_FIELDS: Final[tuple[str, ...]] = tuple(MemoryAccessContext.model_fields)
"""접근 맥락 필드 이름(범위 id 틀이 가리킬 수 있는 값, `MemoryScopeKindInfo.context_fields`)."""

MEMORY_ACCESS_OPS: Final[tuple[str, ...]] = get_args(MemoryAccessOp)
"""허용 동작 어휘(정의 순서): read·search·write·delete."""


class KnownMemoryContextFields:
    """웹이 프로젝트·팀 범위를 가를 때 보는 맥락 필드. **문서 상수**다(이름은 계약 어휘)."""

    PROJECT_ID: Final = "project_id"
    """이 필드를 읽는 범위 종류는 프로젝트별 범위다."""
    GRAPH_ID: Final = "graph_id"
    """이 필드를 읽는 범위 종류는 팀 구성별 범위다."""

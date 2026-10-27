"""메모리 항목·버전·범위 모델(design §5.7R.1.1·§5.7R.5.1).

항목은 실행 중 에이전트(도구)나 사람(화면)이 쓰는 데이터다. 범위 종류 이름(`team`·`project` 등)은
계약이 모른다: 범위는 `MemoryScopeRef{kind, id}`이고 `kind`는 사용자·플러그인 데이터의
범위 종류 id다.
시각은 다른 계약과 같이 Unix epoch 초(float)다.
"""

from typing import Final, Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, NonEmptyStr, Slug

MEMORY_SCOPE_SEPARATOR = ":"
"""범위 문자열 표기 `<범위 종류>:<범위 id>`의 구분자(질의 인자 `scope`). 범위 종류 id(Slug)에는 이
글자가 없으므로 첫 구분자에서 나눈다. 범위 id가 빈 범위는 `<범위 종류>:`이다."""

MEMORY_DEFAULT_CONTENT_TYPE = "text/markdown"
"""본문 형식을 적지 않았을 때의 값(화면 편집기 모드만 바꾼다)."""


class MemoryScopeRef(ContractModel):
    """메모리 범위 하나: 범위 종류 id + 범위 id.

    범위 id는 범위 종류의 id 틀을 접근 맥락으로 푼 값이다(예: 팀 구성 id). 공용처럼 id가 없는
    종류는 빈 문자열이다. 문자열 표기는 `to_text()`·`parse()`.
    """

    kind: Slug = Field(description="범위 종류 id(사용자·플러그인 데이터, 고정 목록 아님).")
    id: str = Field(default="", description="범위 id. 빈 문자열 = id가 없는 범위(예: 공용).")

    def to_text(self) -> str:
        """`<kind>:<id>` 문자열.

        >>> MemoryScopeRef(kind="notes", id="g1").to_text()
        'notes:g1'
        """
        return f"{self.kind}{MEMORY_SCOPE_SEPARATOR}{self.id}"

    @classmethod
    def parse(cls, text: str) -> "MemoryScopeRef":
        """`<kind>:<id>` 문자열을 읽는다. 구분자가 없으면 범위 id가 빈 범위로 본다.

        예외: 범위 종류 id가 글자 규칙에 맞지 않으면 `pydantic.ValidationError`(`ValueError`).

        >>> MemoryScopeRef.parse("notes:a:b")
        MemoryScopeRef(kind='notes', id='a:b')
        >>> MemoryScopeRef.parse("shared-x").id
        ''
        """
        kind, _, scope_id = text.partition(MEMORY_SCOPE_SEPARATOR)
        return cls(kind=kind, id=scope_id)


MemoryAuthorKind = NonEmptyStr
"""쓴 주체 종류(열린 문자열, 알려진 값은 `KnownMemoryAuthorKinds`). 팀 모드 등이 새 값을
더할 수 있다."""


class KnownMemoryAuthorKinds:
    """쓴 주체 종류의 알려진 값. **문서 상수**다(화면은 모르는 값을 그대로 보인다)."""

    AGENT: Final = "agent"
    """실행 중 에이전트 도구."""
    USER: Final = "user"
    """사람(화면·REST)."""
    SYSTEM: Final = "system"
    """정리 규칙·가져오기."""


class MemoryAuthor(ContractModel):
    """항목·버전을 쓴 주체. 에이전트면 실행·노드·팀 구성·프로젝트가 함께 남는다."""

    kind: MemoryAuthorKind
    agent_id: str | None = Field(default=None, description="에이전트 정의 id(에이전트일 때).")
    node_id: str | None = Field(default=None, description="쓴 노드 id.")
    node_path: list[str] = Field(
        default_factory=list, description="중첩 팀 노드 경로(바깥 → 안). 없으면 빈 목록."
    )
    run_id: str | None = Field(default=None, description="쓴 실행(Run) id.")
    root_run_id: str | None = Field(default=None, description="루트 실행 id(중첩 팀이면 바깥).")
    graph_id: str | None = Field(default=None, description="그 노드를 실행한 팀 구성 id.")
    project_id: str | None = Field(default=None, description="루트 실행의 프로젝트 id.")
    label: str | None = Field(
        default=None,
        description=(
            "사람이 읽는 표시(system이면 정리 규칙 id 등, 사람이면 사용자 이름). 없으면 null."
        ),
    )


class _MemoryEntryBase(ContractModel):
    id: NonEmptyStr = Field(description="항목 id(UUID). 키·범위를 옮겨도 그대로.")
    scope: MemoryScopeRef
    key: NonEmptyStr = Field(
        description=(
            "범위 안에서 유일한 키. `/`로 나눈 경로 모양. 글자 규칙(빈 마디·`.`·`..`·앞뒤 `/`·"
            "제어 문자 금지, 최대 256자)은 저장소가 검사한다(`memory.invalid_key`)."
        )
    )
    content_type: str = Field(
        default=MEMORY_DEFAULT_CONTENT_TYPE, description="본문 형식(열린 문자열)."
    )
    tags: list[str] = Field(default_factory=list, description="자유 태그.")
    pinned: bool = Field(default=False, description="고정(정리 규칙이 판단하지 않는다).")
    archived: bool = Field(
        default=False, description="보관(에이전트 도구 결과에서 빠지고 화면에는 보관됨으로)."
    )
    version: int = Field(ge=1, description="쓸 때마다 1 오른다. 낙관적 동시성 키(If-Match).")
    bytes: int = Field(ge=0, description="본문 UTF-8 바이트 수.")
    sha256: str = Field(description="본문 sha256(16진수).")
    created_at: float = Field(description="만든 시각(Unix epoch 초).")
    created_by: MemoryAuthor
    updated_at: float = Field(description="마지막으로 쓴 시각(Unix epoch 초).")
    updated_by: MemoryAuthor
    last_read_at: float | None = Field(
        default=None, description="에이전트 도구가 마지막으로 읽은 시각. 화면 읽기는 세지 않는다."
    )
    deleted_at: float | None = Field(
        default=None, description="지운 시각(표시 삭제). 지우지 않았으면 null."
    )


class MemoryEntry(_MemoryEntryBase):
    """메모리 항목 하나(본문 포함). `GET /memory/entries/{id}` 응답."""

    content: str = Field(description="본문(UTF-8).")


class MemoryEntrySummary(_MemoryEntryBase):
    """목록 항목. 본문 대신 앞부분 미리보기(비밀 가림 뒤)를 싣는다."""

    preview: str = Field(default="", description="본문 앞 200자(비밀 의심 값은 가린 뒤).")


class MemoryEntryPage(ContractModel):
    """`GET /memory/entries` 응답(목록·검색)."""

    items: list[MemoryEntrySummary] = Field(default_factory=list)
    next_cursor: str | None = Field(
        default=None, description="다음 쪽 커서(불투명 문자열). 마지막 쪽이면 null."
    )
    total: int | None = Field(default=None, ge=0, description="전체 수. 세지 않았으면 null.")


MemoryVersionOp = Literal["create", "update", "delete", "restore", "archive", "unarchive", "move"]
"""버전을 남긴 동작. 완전 삭제(purge)는 버전까지 지우므로 버전 동작이 아니다."""

MemoryChangeOp = Literal[
    "create", "update", "delete", "restore", "archive", "unarchive", "move", "purge"
]
"""변경 알림(`MemoryChanged.op`)의 동작 = 버전 동작 + 완전 삭제(purge)."""


class MemoryVersionSummary(ContractModel):
    """버전 목록 항목(본문 없음). 그 버전을 쓴 때의 키·범위를 함께 남긴다."""

    entry_id: NonEmptyStr
    version: int = Field(ge=1)
    op: MemoryVersionOp
    scope: MemoryScopeRef
    key: NonEmptyStr
    bytes: int = Field(ge=0)
    sha256: str
    author: MemoryAuthor
    at: float = Field(description="쓴 시각(Unix epoch 초).")


class MemoryVersion(MemoryVersionSummary):
    """버전 하나(본문 포함). `GET /memory/entries/{id}/versions/{v}` 응답."""

    content: str = Field(description="그 버전의 본문.")


class MemoryScopeSummary(ContractModel):
    """`GET /memory/scopes` 항목: 범위 하나의 요약."""

    scope: MemoryScopeRef
    entries: int = Field(ge=0, description="지우지 않은 항목 수(보관 포함).")
    archived: int = Field(default=0, ge=0, description="그중 보관 항목 수.")
    bytes: int = Field(default=0, ge=0, description="본문 바이트 합.")
    updated_at: float | None = Field(default=None, description="최근 쓴 시각. 항목이 없으면 null.")
    kind_known: bool = Field(
        default=True,
        description=(
            "범위 종류가 지금 목록에 있는지. false = 알 수 없는 범위 종류(에이전트는 못 씀)."
        ),
    )


class MemoryAccessContext(ContractModel):
    """접근 맥락: 범위 종류의 id 틀이 읽는 값(design §5.7R.1.3). 값이 없는 필드는 빈 문자열.

    틀 `{/project_id}`처럼 이 모델의 필드 이름을 JSON 포인터로 가리킨다. 틀이 읽는 필드
    (`MemoryScopeKindInfo.context_fields`)로 웹이 프로젝트·팀 범위를 판단한다(이름이 아니라 틀).
    """

    run_id: str = ""
    root_run_id: str = ""
    graph_id: str = Field(default="", description="그 노드를 실행한 Run의 팀 구성(중첩이면 자식).")
    root_graph_id: str = ""
    project_id: str = Field(default="", description="루트 Run의 프로젝트 id.")
    agent_id: str = ""
    node_id: str = ""
    node_path: list[str] = Field(default_factory=list)

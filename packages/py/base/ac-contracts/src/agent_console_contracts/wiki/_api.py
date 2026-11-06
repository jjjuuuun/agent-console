"""위키 REST 요청·결과, 실행 이벤트 payload, 오류 상세, 문서 상수(design §7R.7·§7R.18.1).

경로(위키 모듈 `mod-wiki`, 꺼지면 404, `?project=` = 공간). 이것은 계약 모델이 아니라 경로 문서다.

- `GET /wiki/info` → `WikiInfo`
- `GET·POST /wiki/wikis`(`WikiCreateRequest`) → `WikiSummary[]`·`WikiView`,
  `GET·PUT·DELETE /wiki/wikis/{wiki}`
- `GET …/pages` → `WikiPageList`, `GET·PUT·DELETE …/pages/{path}`(`WikiPageWrite`) →
  `WikiPageView`
- `POST …/pages/{path}/preview`(`WikiPagePreviewRequest`) → `WikiPagePreview`(쓰지 않음)
- `POST …/pages/{path}/move`(`WikiMoveRequest`) → `WikiMoveResult`
- `GET …/pages/{path}/history` → `WikiHistoryPage`, `GET …/pages/{path}/history/{version}`,
  `POST …/pages/{path}/restore`(`WikiRestoreRequest`)
- `POST /wiki/wikis/{wiki}/link-text`(`WikiLinkTextRequest`) → `WikiLinkText`
- `GET …/templates` → `WikiPageTemplateInfo[]`,
  `POST …/templates/{id}/render`(`WikiTemplateRenderRequest`) → `WikiTemplateRender`
- `GET …/search` → `WikiSearchResult`, `GET …/graph` → `WikiGraph`, `GET …/lint` → `WikiLintReport`
- `GET …/changes?op=&author_run=` · `GET /wiki/changes?author_run=&op=`(공간 전체) →
  `WikiChangePage`
- `GET …/syntax` → `EffectiveWikiSyntax`, `POST …/scan` → `WikiScanResult`
- `POST …/export`(zip 바이트, `Content-Disposition: attachment; filename="<wiki id>.zip"`) ·
  `POST …/import` → `WikiImportResult`
- `GET·POST /wiki/rules`(→ `WikiRulesListItem[]`) · `GET·PUT·DELETE /wiki/rules/{id}`
  (→ `WikiRulesView`) · `POST /wiki/rules/check`(`WikiRulesCheckRequest`) → `WikiRulesCheckResult`

실행 이벤트 `wiki.*`의 payload는 `WikiEventPayload`다. RunEvent `type`은 열린 문자열이고
`runs`의 알려진 이벤트 목록에는 넣지 않는다(메모리 `memory.*`와 같음). payload에는 **본문·검색어
원문을 싣지 않는다**(크기·해시만).
"""

from typing import Final, Literal, get_args

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr, Slug

from ._rules import WikiAccessOp
from ._views import WikiHeading, WikiIssue, WikiLink, WikiPageSummary

type WikiImportPolicy = Literal["skip", "overwrite", "rename"]
"""zip 가져오기에서 같은 경로의 페이지가 있을 때(고정 어휘)."""

WikiEventStatus = Literal[
    "ok",
    "denied",
    "not_found",
    "conflict",
    "too_large",
    "secret_rejected",
    "rule_rejected",
    "rate_limited",
    "wiki_unavailable",
    "invalid_path",
    "error",
]
"""도구 호출 결과 상태. ok 밖의 값은 도구 결과 `is_error`와 사유 코드 `wiki.<값>`에 대응한다."""


# ---------------------------------------------------------------- 위키·페이지 요청


class WikiCreateRequest(ContractModel):
    """`POST /wiki/wikis` 본문: 위키 만들기(정의만, 페이지 폴더는 첫 쓰기 때 생긴다)."""

    id: Slug | None = Field(default=None, description="비우면 이름에서 만든다(겹치면 뒤에 수).")
    name: NonEmptyStr
    description: str = ""
    home: str | None = None
    rules: list[Slug] = Field(default_factory=list, description="쓸 위키 규칙 id(같은 공간).")


class WikiPageWrite(ContractModel):
    """`PUT …/pages/{path}` 본문. 새 페이지는 `If-None-Match: *`, 고치기는 `If-Match: <해시>`."""

    content: str = Field(description="본문 원문(머리말 포함).")
    message: str | None = Field(default=None, description="기록에 남길 한 줄(선택).")
    template: str | None = Field(
        default=None,
        description="새 페이지를 이 페이지 틀로 만든다(`content`가 비었을 때만 틀 본문을 쓴다).",
    )


class WikiMoveRequest(ContractModel):
    """`POST …/pages/{path}/move` 본문."""

    to: NonEmptyStr = Field(description="새 페이지 경로(확장자 없음).")
    rewrite_links: bool = Field(default=True, description="다른 페이지의 링크 문자열도 고친다.")
    dry_run: bool = Field(default=False, description="참이면 옮기지 않고 결과만 계산한다.")
    if_hash: str | None = Field(default=None, description="옮길 페이지의 본문 해시(다르면 409).")
    message: str | None = None


class WikiRewrittenPage(ContractModel):
    """옮기기에서 링크를 고친(고칠) 페이지 하나."""

    path: NonEmptyStr
    count: int = Field(ge=1, description="고친 링크 수.")


class WikiMoveResult(ContractModel):
    """옮기기 결과(`dry_run`이면 고칠 것 미리보기)."""

    moved: bool = Field(default=False, description="실제로 옮겼다(`dry_run`이면 false).")
    from_: NonEmptyStr = Field(alias="from")
    to: NonEmptyStr
    rewritten: list[WikiRewrittenPage] = Field(default_factory=list)
    conflicts: list[str] = Field(
        default_factory=list,
        description="그사이 바뀌어 링크를 고치지 않은 페이지 경로(다시 읽고 손으로 고친다).",
    )
    issues: list[WikiIssue] = Field(default_factory=list)


class WikiRestoreRequest(ContractModel):
    """`POST …/pages/{path}/restore` 본문: 그 버전 본문으로 새 버전(op `restore`)을 만든다."""

    version: int = Field(ge=1)
    message: str | None = None


class WikiScanResult(ContractModel):
    """`POST …/scan`: 앱 밖 변경 다시 읽기 결과."""

    external: list[str] = Field(
        default_factory=list, description="앱 밖에서 바뀐 것으로 기록한 페이지(op `external`)."
    )
    imported: list[str] = Field(
        default_factory=list, description="기록이 없어 처음 기록한 페이지(op `import`)."
    )
    deleted: list[str] = Field(default_factory=list, description="파일이 사라진 페이지.")
    recorded: bool = Field(
        default=True, description="기록에 남겼다(기록 저장소를 쓸 수 없으면 false, 감지만)."
    )


class WikiImportItem(ContractModel):
    """zip 가져오기 항목 하나의 결과."""

    path: NonEmptyStr = Field(description="zip 안 페이지 경로(확장자 없음).")
    status: NonEmptyStr = Field(
        description=(
            "created·skipped·overwritten·renamed·rejected(열린 문자열, `KnownWikiImportStatuses`)."
        )
    )
    to: str | None = Field(default=None, description="renamed면 새 경로.")
    issues: list[WikiIssue] = Field(
        default_factory=list, description="rejected·skipped의 이유(경로 공격·크기·비밀 등)."
    )


class WikiImportResult(ContractModel):
    """`POST …/import`(zip) 결과. `dry_run=true`면 쓰지 않고 같은 결과를 계산한다."""

    dry_run: bool = False
    items: list[WikiImportItem] = Field(default_factory=list)
    issues: list[WikiIssue] = Field(
        default_factory=list, description="zip 전체 이슈(크기 상한·형식 등)."
    )


class WikiPageNotFoundDetails(ContractModel):
    """`wiki.page_not_found`(HTTP 404) 오류의 `error.details`."""

    path: NonEmptyStr
    has_history: bool = Field(
        default=False, description="파일은 없지만 기록이 있다(기록에서 되돌릴 수 있음)."
    )


# ---------------------------------------------------------------- 미리보기·링크 넣기·틀 렌더


class WikiPagePreviewRequest(ContractModel):
    """`POST …/pages/{path}/preview` 본문: 저장 전 시험(쓰지 않는다)."""

    content: str = Field(description="시험할 본문 원문(머리말 포함).")


class WikiRuleResult(ContractModel):
    """쓰기 규칙 하나의 판정 결과(맞은 규칙만)."""

    rule_id: NonEmptyStr
    action: NonEmptyStr = Field(description="reject·warn(모르는 값은 warn으로 읽은 결과).")
    message: str = ""
    lines: list[int] = Field(default_factory=list, description="금지 패턴에 맞은 줄 번호(1부터).")


class WikiPagePreview(ContractModel):
    """저장 전 시험 결과. 판단은 REST 쓰기와 같다(쓴 주체 사람, 기록·색인·알림을 건드리지 않음)."""

    page: WikiPageSummary
    links: list[WikiLink] = Field(default_factory=list)
    headings: list[WikiHeading] = Field(default_factory=list)
    issues: list[WikiIssue] = Field(default_factory=list)
    rule_results: list[WikiRuleResult] = Field(default_factory=list)
    would_reject: bool = Field(
        default=False, description="지금 저장하면 거부된다(쓰기 규칙 또는 비밀 검사)."
    )


class WikiLinkTextRequest(ContractModel):
    """`POST /wiki/wikis/{wiki}/link-text` 본문: 링크 넣기 글자 만들기."""

    from_page: NonEmptyStr = Field(description="링크를 넣을 페이지 경로(상대 경로 계산 기준).")
    target: NonEmptyStr = Field(description="대상 페이지 경로.")
    label: str | None = Field(
        default=None, description="링크 글자(생략 = 대상 제목, 없으면 target)."
    )
    rule_id: str | None = Field(
        default=None, description="쓸 링크 규칙(생략 = 삽입 틀이 있는 첫 링크 규칙)."
    )


class WikiLinkText(ContractModel):
    """링크 넣기 글자."""

    rule_id: NonEmptyStr
    text: str


class WikiTemplateRenderRequest(ContractModel):
    """`POST /wiki/wikis/{wiki}/templates/{id}/render` 본문(쓰지 않는다)."""

    title: str | None = None
    values: dict[str, str] = Field(default_factory=dict, description="선언 변수 이름 → 값.")


class WikiTemplateRender(ContractModel):
    """페이지 틀 렌더 결과."""

    path: str | None = Field(
        default=None, description="새 페이지 경로(경로 틀이 없거나 규칙에 어긋나면 null)."
    )
    content: str = ""
    missing: list[str] = Field(default_factory=list, description="값이 없어 비운 변수 이름.")
    issues: list[WikiIssue] = Field(default_factory=list)


# ---------------------------------------------------------------- 규칙 검사·오류 상세


class WikiRulesCheckRequest(ContractModel):
    """`POST /wiki/rules/check`: 위키 규칙 검사(저장하지 않음). 응답은 `WikiRulesCheckResult`."""

    rules: JsonObject = Field(default_factory=dict, description="규칙 문서(위키 규칙 모양).")
    files: list[str] | None = Field(
        default=None,
        description="본문 폴더의 파일 목록(페이지 틀 파일 확인용). null = 저장된 규칙 것을 본다.",
    )


class WikiRulesCheckResult(ContractModel):
    """위키 규칙 검사 결과."""

    issues: list[WikiIssue] = Field(default_factory=list)


class WikiRuleRejectedDetails(ContractModel):
    """`wiki.rule_rejected`(HTTP 422) 오류의 `error.details`(값 원문 없음)."""

    rule_id: NonEmptyStr
    message: str = ""
    lines: list[int] = Field(default_factory=list, description="금지 패턴에 맞은 줄 번호(1부터).")
    issues: list[WikiIssue] = Field(
        default_factory=list, description="거부한 규칙이 여럿이면 모두(첫 것이 위 필드)."
    )


# ---------------------------------------------------------------- 실행 이벤트


class WikiEventPayload(ContractModel):
    """RunEvent `wiki.<op>`의 payload: 에이전트 위키 도구 호출 하나.

    **본문·검색어 원문 없음**: 크기(`bytes`·`query_chars`)와 해시(`sha256`·`query_sha256`)만 싣는다.
    로그 대응표는 이 값으로 문서 표지 `{kind: wiki, path: <위키>/<페이지>}`를 만든다.
    """

    op: WikiAccessOp
    wiki: str | None = Field(default=None, description="위키 id(모르면 null).")
    path: str | None = Field(default=None, description="페이지 경로(옮기기는 옛 경로).")
    to: str | None = Field(default=None, description="옮기기의 새 경로.")
    status: WikiEventStatus
    code: str | None = Field(default=None, description="실패 사유 코드(`wiki.*`, ok면 null).")
    version: int | None = Field(default=None, ge=1, description="쓴 뒤 버전(기록 없으면 null).")
    bytes: int | None = Field(default=None, ge=0, description="본문 바이트 수.")
    sha256: str | None = Field(default=None, description="본문 sha256(16진수).")
    rule_ids: list[str] = Field(default_factory=list, description="거부·경고한 규칙 id.")
    results: int | None = Field(default=None, ge=0, description="검색·목록 결과 수.")
    query_chars: int | None = Field(default=None, ge=0, description="검색어 글자 수.")
    query_sha256: str | None = Field(default=None, description="검색어 sha256(16진수).")
    tool: str | None = Field(default=None, description="사용자가 정한 도구 이름.")
    tool_use_id: str | None = Field(default=None, description="모델의 도구 호출 id.")
    duration_ms: float | None = Field(default=None, ge=0, description="처리 시간(ms).")


WIKI_EVENT_PREFIX: Final = "wiki."
"""위키 RunEvent `type` 접두. `type` = 접두 + `WikiEventPayload.op`."""

WIKI_ACCESS_OPS: Final[tuple[str, ...]] = get_args(WikiAccessOp)
"""허용 동작 어휘(정의 순서): read·search·list·links·write·move·delete."""

KNOWN_WIKI_EVENT_TYPES: Final[tuple[str, ...]] = tuple(
    f"{WIKI_EVENT_PREFIX}{op}" for op in WIKI_ACCESS_OPS
)
"""위키 RunEvent type 목록(문서 상수). `runs`의 `KNOWN_RUN_EVENT_TYPES`에는 넣지 않는다."""


# ---------------------------------------------------------------- 문서 상수


class KnownWikiLinkKinds:
    """링크 규칙 `kind`의 알려진 값. **문서 상수**다(열린 문자열, 모르는 값은 이슈 후 건너뜀)."""

    PATTERN: Final = "pattern"
    """정규식(`pattern`)으로 인라인 텍스트에서 찾는다."""
    MARKDOWN: Final = "markdown"
    """마크다운 링크 중 상대 경로이고 확장자가 페이지 확장자인 것."""


class KnownWikiResolvers:
    """링크 대상 찾기(`resolve`)의 값 — 코드 개념 넷(design §7R.1·§7R.12)."""

    PATH: Final = "path"
    TITLE: Final = "title"
    ALIAS: Final = "alias"
    RELATIVE_PATH: Final = "relative_path"


class KnownWikiAuthorKinds:
    """쓴 주체 `WikiAuthor.kind`의 알려진 값(설정 `secret_scan` 키로도 쓴다)."""

    USER: Final = "user"
    AGENT: Final = "agent"
    SYSTEM: Final = "system"
    EXTERNAL: Final = "external"
    """앱 밖에서 파일을 고친 것을 감지했다."""


class KnownWikiVersionOps:
    """기록 `WikiPageVersion.op`의 알려진 값."""

    CREATE: Final = "create"
    UPDATE: Final = "update"
    DELETE: Final = "delete"
    MOVE_OUT: Final = "move_out"
    """옛 경로 쪽 기록(`to` = 새 경로)."""
    MOVE_IN: Final = "move_in"
    """새 경로 쪽 기록(`from` = 옛 경로)."""
    RESTORE: Final = "restore"
    EXTERNAL: Final = "external"
    """앱 밖 변경 감지(쓴 주체 external)."""
    IMPORT: Final = "import"
    """기록이 없던 파일의 첫 기록(처음 보거나 git·zip으로 들어옴)."""


class KnownWikiChangeOps:
    """쓰기 판단 대상 `/change/op`의 값(쓰기 규칙 조건 위젯 제안용)."""

    CREATE: Final = "create"
    UPDATE: Final = "update"
    DELETE: Final = "delete"
    MOVE: Final = "move"


class KnownWikiLintCodes:
    """기본 점검 이름(문법 `lint.builtin` 키) — 코드 개념 셋. 이슈 코드는 `wiki.<값>`."""

    BROKEN_LINK: Final = "broken_link"
    ORPHAN: Final = "orphan"
    DUPLICATE_TITLE: Final = "duplicate_title"


class KnownWikiFrontMatterRoles:
    """머리말 역할(문법 `front_matter.roles` 키) — 코드 개념 셋.

    어느 머리말 키가 그 역할인지는 데이터다."""

    TITLE: Final = "title"
    TAGS: Final = "tags"
    ALIASES: Final = "aliases"


class KnownWikiTitleSources:
    """제목 출처(문법 `title_sources` 값)."""

    FRONT_MATTER: Final = "front_matter"
    FIRST_HEADING: Final = "first_heading"
    FILE_NAME: Final = "file_name"


class KnownWikiWriteActions:
    """쓰기 규칙 `action`의 알려진 값(열린 문자열, 모르는 값은 warn으로 읽고 이슈)."""

    REJECT: Final = "reject"
    WARN: Final = "warn"


class KnownWikiLinkStatuses:
    """`WikiLink.status`의 알려진 값(우선순위 scheme > outside > broken > ok)."""

    OK: Final = "ok"
    BROKEN: Final = "broken"
    OUTSIDE: Final = "outside"
    SCHEME: Final = "scheme"


class KnownWikiImportStatuses:
    """`WikiImportItem.status`의 알려진 값."""

    CREATED: Final = "created"
    SKIPPED: Final = "skipped"
    OVERWRITTEN: Final = "overwritten"
    RENAMED: Final = "renamed"
    REJECTED: Final = "rejected"


class KnownWikiRuleEntryKinds:
    """`WikiRuleEntry.kind`의 알려진 값."""

    WRITE: Final = "write"
    LINT: Final = "lint"
    TEMPLATE: Final = "template"


class KnownWikiSyntaxSources:
    """`EffectiveWikiSyntax.sources` 값의 알려진 모양. 규칙 층은 `rules:<규칙 id>`다."""

    DEFAULT: Final = "default"
    SETTINGS: Final = "settings"
    RULES_PREFIX: Final = "rules:"


__all__ = [
    "KNOWN_WIKI_EVENT_TYPES",
    "WIKI_ACCESS_OPS",
    "WIKI_EVENT_PREFIX",
    "KnownWikiAuthorKinds",
    "KnownWikiChangeOps",
    "KnownWikiFrontMatterRoles",
    "KnownWikiImportStatuses",
    "KnownWikiLinkKinds",
    "KnownWikiLinkStatuses",
    "KnownWikiLintCodes",
    "KnownWikiResolvers",
    "KnownWikiRuleEntryKinds",
    "KnownWikiSyntaxSources",
    "KnownWikiTitleSources",
    "KnownWikiVersionOps",
    "KnownWikiWriteActions",
    "WikiCreateRequest",
    "WikiEventPayload",
    "WikiEventStatus",
    "WikiImportItem",
    "WikiImportPolicy",
    "WikiImportResult",
    "WikiLinkText",
    "WikiLinkTextRequest",
    "WikiMoveRequest",
    "WikiMoveResult",
    "WikiPageNotFoundDetails",
    "WikiPagePreview",
    "WikiPagePreviewRequest",
    "WikiPageWrite",
    "WikiRestoreRequest",
    "WikiRewrittenPage",
    "WikiRuleRejectedDetails",
    "WikiRuleResult",
    "WikiRulesCheckRequest",
    "WikiRulesCheckResult",
    "WikiScanResult",
    "WikiTemplateRender",
    "WikiTemplateRenderRequest",
]

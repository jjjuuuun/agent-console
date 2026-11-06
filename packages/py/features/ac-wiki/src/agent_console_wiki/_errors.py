"""위키 라이브러리 예외. 모두 `WikiError`(계약 코드 `code` + 값 원문 없는 `details`)다.

전송 계층(REST·도구)은 `code`로 HTTP 상태·도구 사유 코드를 고른다. 메시지는 사람이 읽는 문장이고
본문·비밀 의심 값은 담지 않는다.
"""

from __future__ import annotations

from typing import Any

from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.wiki import WikiIssue, WikiRuleRejectedDetails

__all__ = [
    "WikiConflictError",
    "WikiError",
    "WikiHistoryUnavailableError",
    "WikiLinkInsertUnavailableError",
    "WikiPageExistsError",
    "WikiPageNotFoundError",
    "WikiPathError",
    "WikiRuleRejectedError",
    "WikiSecretRejectedError",
    "WikiSectionNotFoundError",
    "WikiTemplateNotFoundError",
    "WikiTooLargeError",
    "WikiVersionNotFoundError",
    "WikiZipFormatError",
]


class WikiError(Exception):
    """위키 라이브러리 오류의 공통 바탕.

    Attributes:
        code: 계약 오류·이슈 코드(`wiki.*`).
        details: 오류 상세(값 원문 없음).
    """

    code: str = "wiki.error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details or {})


class WikiPathError(WikiError, ValueError):
    """페이지·파일 경로가 위키 폴더를 벗어나거나 쓸 수 없는 이름이다(`wiki.invalid_path`).

    Attributes:
        path: 받은 경로(그대로).
        reason: `invalid`(`..`·절대·드라이브·역슬래시·금지 문자·빈 구성요소) · `hidden`(`.`로
            시작하는 구성요소) · `reserved`(예약 이름) · `link`(심볼릭 링크·정션을 지나감) ·
            `extension`(페이지 확장자가 아님).
    """

    code = KnownIssueCodes.WIKI_INVALID_PATH

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"위키 경로로 쓸 수 없습니다({reason}): {path!r}",
            details={"path": path, "reason": reason},
        )
        self.path = path
        self.reason = reason


class WikiPageNotFoundError(WikiError, LookupError):
    """페이지가 없다(`wiki.page_not_found`). `details` 모양은 계약 `WikiPageNotFoundDetails`.

    Attributes:
        path: 페이지 경로.
        has_history: 파일은 없지만 기록이 있다(기록에서 되돌릴 수 있음, §7R.18 Q9).
    """

    code = KnownIssueCodes.WIKI_PAGE_NOT_FOUND

    def __init__(self, path: str, *, has_history: bool = False) -> None:
        super().__init__(
            f"페이지가 없습니다: {path!r}", details={"path": path, "has_history": has_history}
        )
        self.path = path
        self.has_history = has_history


class WikiSectionNotFoundError(WikiError, LookupError):
    """페이지에 그 제목의 절이 없다(`wiki.not_found`, `details.reason = section_not_found`).

    Attributes:
        path: 페이지 경로.
        section: 찾은 제목.
    """

    code = KnownIssueCodes.WIKI_NOT_FOUND

    def __init__(self, path: str, section: str) -> None:
        super().__init__(
            f"페이지에 그 절이 없습니다: {path!r}",
            details={"path": path, "section": section, "reason": "section_not_found"},
        )
        self.path = path
        self.section = section


class WikiPageExistsError(WikiError, FileExistsError):
    """그 경로에 페이지(파일)가 이미 있다(`wiki.page_exists`)."""

    code = KnownIssueCodes.WIKI_PAGE_EXISTS

    def __init__(self, path: str) -> None:
        super().__init__(f"페이지가 이미 있습니다: {path!r}", details={"path": path})
        self.path = path


class WikiLinkInsertUnavailableError(WikiError):
    """링크 삽입 틀(`insert`)이 있는 링크 규칙이 없다(`wiki.link_insert_unavailable`)."""

    code = KnownIssueCodes.WIKI_LINK_INSERT_UNAVAILABLE

    def __init__(self, rule_id: str | None = None) -> None:
        detail = f"링크 규칙 '{rule_id}'에" if rule_id else "유효 문법에"
        super().__init__(
            f"{detail} 링크 넣기 틀이 없습니다.",
            details={"rule_id": rule_id} if rule_id else {},
        )
        self.rule_id = rule_id


class WikiConflictError(WikiError):
    """`if_hash`가 지금 본문 해시와 다르다(REST 412 `version_conflict`, 도구 `wiki.conflict`).

    Attributes:
        path: 페이지 경로.
        expected: 받은 해시.
        actual: 지금 해시(파일이 없으면 None).
    """

    code = ErrorCodes.VERSION_CONFLICT

    def __init__(self, path: str, *, expected: str, actual: str | None) -> None:
        super().__init__(
            f"페이지가 그사이 바뀌었습니다: {path!r}",
            details={"path": path, "expected": expected, "actual": actual},
        )
        self.path = path
        self.expected = expected
        self.actual = actual


class WikiTooLargeError(WikiError):
    """크기·개수 한도를 넘었다(`wiki.too_large`, 422).

    Attributes:
        limit: 넘은 한도 이름(예 `max_page_bytes`·`max_pages`·zip 상한 이름).
        value: 그 한도 값.
    """

    code = KnownIssueCodes.WIKI_TOO_LARGE

    def __init__(self, message: str, *, limit: str, value: int) -> None:
        super().__init__(message, details={"limit": limit, "value": value})
        self.limit = limit
        self.value = value


class WikiRuleRejectedError(WikiError):
    """쓰기 규칙(또는 쓰기 검사 X50)이 거부했다(`wiki.rule_rejected`, 422).

    `details`는 계약 `WikiRuleRejectedDetails`(첫 거부 규칙 + 모든 거부 이슈) 모양이다.

    Attributes:
        issues: 거부 이슈 전부(`severity=error`).
        warnings: 같은 판단에서 나온 경고(쓰기를 했다면 함께 보였을 것).
    """

    code = KnownIssueCodes.WIKI_RULE_REJECTED

    def __init__(self, issues: list[WikiIssue], *, warnings: list[WikiIssue] | None = None) -> None:
        first = issues[0]
        lines = list(first.details.get("lines") or ([first.line] if first.line else []))
        details = WikiRuleRejectedDetails(
            rule_id=first.rule_id or first.code,
            message=first.message,
            lines=lines,
            issues=issues,
        )
        super().__init__(first.message, details=details.model_dump(mode="json"))
        self.issues = issues
        self.warnings = list(warnings or [])


class WikiSecretRejectedError(WikiError):
    """비밀로 보이는 값이 있어 거부했다(`wiki.secret_rejected`, 422). 값은 싣지 않고 줄 번호만.

    Attributes:
        lines: 의심 줄 번호(1부터, 못 정하면 빈 목록).
    """

    code = KnownIssueCodes.WIKI_SECRET_REJECTED

    def __init__(self, lines: list[int], *, issues: list[WikiIssue] | None = None) -> None:
        super().__init__(
            "비밀로 보이는 값이 있어 저장하지 않았습니다.",
            details={
                "lines": list(lines),
                "issues": [i.model_dump(mode="json") for i in issues or []],
            },
        )
        self.lines = list(lines)


class WikiHistoryUnavailableError(WikiError):
    """기록 저장소가 없다(`wiki.history_unavailable`, 409)."""

    code = KnownIssueCodes.WIKI_HISTORY_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("이 위키에는 기록 저장소가 없습니다.")


class WikiVersionNotFoundError(WikiError, LookupError):
    """그 버전이 없다 — 없던 번호이거나 보관 수로 지웠다(`wiki.version_not_found`, 404)."""

    code = KnownIssueCodes.WIKI_VERSION_NOT_FOUND

    def __init__(self, path: str, version: int) -> None:
        super().__init__(
            f"페이지 {path!r}의 버전 {version}이 없습니다.",
            details={"path": path, "version": version},
        )
        self.path = path
        self.version = version


class WikiTemplateNotFoundError(WikiError, LookupError):
    """합친 규칙에 그 페이지 틀이 없다(`wiki.template_missing`)."""

    code = KnownIssueCodes.WIKI_TEMPLATE_MISSING

    def __init__(self, template_id: str) -> None:
        super().__init__(f"페이지 틀이 없습니다: {template_id!r}", details={"id": template_id})
        self.template_id = template_id


class WikiZipFormatError(WikiError, ValueError):
    """가져올 데이터가 zip으로 읽히지 않는다(`validation_failed`)."""

    code = ErrorCodes.VALIDATION_FAILED

    def __init__(self) -> None:
        super().__init__("zip 파일로 읽지 못했습니다.")

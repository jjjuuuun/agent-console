"""SDD 오류. `code`는 계약 오류 코드(`ErrorCodes`) 값이고 `details`에는 값 원문을 넣지 않는다.

전송 계층(서버 모듈)이 `code`로 HTTP 상태(`ERROR_HTTP_STATUS`)를 고르고 `details`를 그대로 싣는다.
작업 줄 고치기 오류(`TaskPatchError`·`TaskChangedError`)는 `_patch.py`에 있다(같은 모양).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts.constants import ErrorCodes
from agent_console_contracts.sdd import SddDocumentMissingDetails, SddGateBlockedDetails

__all__ = [
    "DocumentChangedError",
    "DocumentExistsError",
    "DocumentMissingError",
    "GateBlockedError",
    "SddError",
    "SpecNotFoundError",
    "SpecPathError",
    "TemplateExistsError",
    "TransitionDeniedError",
]


class SddError(Exception):
    """SDD 기능 오류의 베이스.

    Attributes:
        code: 계약 오류 코드.
        details: 화면에 줄 세부(`error.details`).
    """

    code: str = ErrorCodes.BAD_REQUEST

    def __init__(self, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details or {})


class SpecNotFoundError(SddError):
    """스펙·문서 틀·문서가 없다(`sdd.not_found`, 404). `details{kind, id}`."""

    code = ErrorCodes.SDD_NOT_FOUND

    def __init__(self, kind: str, id: str) -> None:
        super().__init__(f"{kind} '{id}'이(가) 없습니다.", {"kind": kind, "id": id})


class DocumentMissingError(SddError):
    """문서 본문 파일이 없다(`sdd.document_missing`, 404). 읽기로 파일을 만들지 않는다."""

    code = ErrorCodes.SDD_DOCUMENT_MISSING

    def __init__(self, document_id: str, file: str) -> None:
        self.missing = SddDocumentMissingDetails(document_id=document_id, file=file)
        super().__init__(
            f"문서 '{document_id}'의 본문 파일이 없습니다.", self.missing.model_dump(mode="json")
        )


class DocumentExistsError(SddError):
    """만들기만(`If-None-Match: *`) 요청했는데 본문 파일이 이미 있다(`already_exists`, 409)."""

    code = ErrorCodes.ALREADY_EXISTS

    def __init__(self, document_id: str, content_hash: str) -> None:
        super().__init__(
            f"문서 '{document_id}'의 본문 파일이 이미 있습니다.",
            {"document_id": document_id, "content_hash": content_hash},
        )


class DocumentChangedError(SddError):
    """문서 본문이 화면이 본 것과 다르다(`version_conflict`, 412 — 본문 `If-Match` 파일 해시)."""

    code = ErrorCodes.VERSION_CONFLICT

    def __init__(self, document_id: str, content_hash: str | None) -> None:
        super().__init__(
            "문서 본문이 바뀌었습니다. 새로 읽은 뒤 다시 저장하세요.",
            {"document_id": document_id, "content_hash": content_hash},
        )


class TransitionDeniedError(SddError):
    """문서 상태 전환 규칙에 그 전환(또는 그 쪽 `by`)이 없다(`sdd.transition_denied`, 403)."""

    code = ErrorCodes.SDD_TRANSITION_DENIED

    def __init__(self, document_id: str, from_: str | None, to: str, by: str) -> None:
        super().__init__(
            f"문서 '{document_id}'를 '{from_ or '-'}'에서 '{to}'(으)로 바꿀 수 없습니다({by}).",
            {"document_id": document_id, "from": from_, "to": to, "by": by},
        )


class GateBlockedError(SddError):
    """관문이 막았다(`sdd.gate_blocked`, 422). `details` = `SddGateBlockedDetails`."""

    code = ErrorCodes.SDD_GATE_BLOCKED

    def __init__(self, blocked: SddGateBlockedDetails) -> None:
        self.blocked = blocked
        super().__init__(
            blocked.message or f"관문 '{blocked.gate_id}'이(가) 막았습니다.",
            blocked.model_dump(mode="json"),
        )


class TemplateExistsError(SddError):
    """틀로 저장(`on_conflict=fail`)에서 같은 id의 문서 틀이 있다(`sdd.template_exists`, 409)."""

    code = ErrorCodes.SDD_TEMPLATE_EXISTS

    def __init__(self, id: str) -> None:
        super().__init__(f"문서 틀 '{id}'이(가) 이미 있습니다.", {"id": id})


class SpecPathError(SddError):
    """경로가 프로젝트 폴더 안 상대 경로가 아니다(`..`·절대 경로·링크·앱 구성 폴더,
    `folders.invalid_path`, 422). `details{path, reason}` — reason은 열린 문자열
    (`invalid`·`link`·`reserved`·`not_found`·`not_directory`)."""

    code = ErrorCodes.FOLDERS_INVALID_PATH

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"쓸 수 없는 경로입니다({reason}).", {"path": path, "reason": reason})

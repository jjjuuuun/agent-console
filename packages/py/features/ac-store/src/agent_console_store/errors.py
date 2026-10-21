# ruff: noqa: N818
"""저장소 예외. 서버는 `code`를 계약의 오류 코드(`ErrorCodes`)로 그대로 쓸 수 있다."""

from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import Interaction, VersionConflictDetails


class StoreError(Exception):
    """저장소 예외의 베이스. `code`는 계약의 오류 코드 문자열이다."""

    code: str = "internal"


class NotFound(StoreError):
    """대상(정의, Run, 버전)이 없다 -> `not_found`(404)."""

    code = "not_found"


class AlreadyExists(StoreError):
    """같은 id가 이미 있다 -> `already_exists`(409)."""

    code = "already_exists"


class VersionRequired(StoreError):
    """기대 버전(If-Match)이 필요한 종류인데 주지 않았다 -> `version_required`(428)."""

    code = "version_required"


class VersionConflict(StoreError):
    """기대 버전과 현재 버전이 다르다 -> `version_conflict`(412).

    `details`가 그대로 오류 응답의 `error.details`가 된다(현재 버전 해시, 저장 시각, 규모).
    """

    code = "version_conflict"

    def __init__(self, details: VersionConflictDetails) -> None:
        super().__init__(f"version conflict: current={details.current_version_hash}")
        self.details = details


class InvalidIdentifier(StoreError):
    """파일 이름으로 쓸 수 없는 id -> `bad_request`(400)."""

    code = "bad_request"


class EventConflict(StoreError):
    """같은 (run_id, seq)에 다른 event_id가 이미 저장되어 있다 -> `internal`."""

    code = "internal"


class DefinitionCorrupt(StoreError):
    """정의 파일을 읽을 수 없다(YAML 문법 오류, 최상위가 객체가 아님) -> `validation_failed`."""

    code = "validation_failed"


class InvalidContentPath(InvalidIdentifier):
    """본문 파일 경로가 정의 폴더 밖이거나 형식이 틀렸다(절대 경로, `..` 등) -> `bad_request`."""


class ContentTooLarge(StoreError):
    """본문 파일들의 총량이 한도를 넘는다 -> `payload_too_large`(413)."""

    code = "payload_too_large"


class InteractionClosed(StoreError):
    """이미 닫힌 상호작용을 다시 닫으려 했다 -> `interaction_closed`(409).

    `interaction`은 지금 저장된(먼저 닫은 쪽의) 상태다. 서버는 이를 409 응답에 쓸 수 있다.
    """

    code = "interaction_closed"

    def __init__(self, interaction: Interaction) -> None:
        super().__init__(f"interaction {interaction.id} is already {interaction.status}")
        self.interaction = interaction


@dataclass(frozen=True)
class StoreErrorBody:
    """저장소 예외 → 계약 오류 응답 재료(전송 계층과 무관, 3R.16 공용화).

    Attributes:
        code: 계약 오류 코드(`StoreError.code`).
        message: 사람이 읽는 문장(예외 문장 — 값은 담지 않는다).
        details: `error.details`. 412는 현재 버전 정보, 422는 `{"issues": []}`.
        headers: 응답 헤더. 412는 `ETag`(서버의 현재 버전).
    """

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


def store_error_body(exc: StoreError) -> StoreErrorBody:
    """`StoreError` → `StoreErrorBody`. 서버 모듈들이 같은 매핑을 쓴다(모듈마다 복사하지 않는다).

    - `VersionConflict`(412): `details` = `VersionConflictDetails`, `ETag` = 현재 버전.
    - `validation_failed`(정의 파일 손상 등): `details = {"issues": []}`(422는 항상 issues).
    - 그 밖: `details = {}`.
    """
    details: dict[str, Any] = {}
    headers: dict[str, str] = {}
    if isinstance(exc, VersionConflict):
        details = exc.details.model_dump(mode="json")
        current = details.get("current_version_hash")
        if isinstance(current, str) and current:
            headers["ETag"] = f'"{current}"'
    elif exc.code == "validation_failed":
        details = {"issues": []}
    return StoreErrorBody(code=exc.code, message=str(exc), details=details, headers=headers)

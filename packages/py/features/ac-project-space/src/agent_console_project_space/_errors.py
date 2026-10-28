# ruff: noqa: N818
"""공간 예외. `code`는 계약의 오류 코드(`ErrorCodes`)다."""

from __future__ import annotations

from dataclasses import dataclass

from agent_console_contracts import ErrorCodes
from agent_console_store import StoreError


class SpaceError(Exception):
    """프로젝트 공간 예외의 베이스."""

    code: str = ErrorCodes.INTERNAL


class FolderMissing(SpaceError):
    """프로젝트 폴더가 없거나 폴더가 아니다 -> `project.folder_missing`(409)."""

    code = ErrorCodes.PROJECT_FOLDER_MISSING


class ConfigReadonly(SpaceError):
    """`.agent-console/`에 쓸 수 없다 -> `project.config_readonly`(409)."""

    code = ErrorCodes.PROJECT_CONFIG_READONLY


class UnsafeConfigDir(SpaceError):
    """구성 폴더가 링크이거나 이름이 폴더 밖을 가리킨다 -> `bad_request`(400)."""

    code = ErrorCodes.BAD_REQUEST


class ManifestInvalid(SpaceError):
    """`project.yaml`을 읽을 수 없거나 쓰면 안 된다 -> `project.manifest_invalid`(409).

    Attributes:
        reason: `unreadable`·`not_utf8`·`yaml`·`schema`·`newer_format` 중 하나.
        issues: 어긋난 필드 위치(JSON Pointer). 값은 담지 않는다.
    """

    code = ErrorCodes.PROJECT_MANIFEST_INVALID

    def __init__(self, reason: str, message: str = "", *, issues: tuple[str, ...] = ()) -> None:
        super().__init__(f"project manifest invalid ({reason}){': ' + message if message else ''}")
        self.reason = reason
        self.issues = issues


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """비밀 의심 위치 하나. 값은 담지 않는다(`path` = JSON Pointer, `reason`은 secret-rules 값)."""

    path: str
    reason: str


class SecretRejected(StoreError):
    """정의·매니페스트에 평문 비밀로 보이는 값이 있어 저장하지 않았다 -> `validation_failed`(422).

    비밀 저장소에 넣고 `secret://<이름>` 참조로 바꿔야 한다. 메시지·`findings`에 값은 없다.
    """

    code = ErrorCodes.VALIDATION_FAILED

    def __init__(self, findings: tuple[SecretFinding, ...]) -> None:
        where = ", ".join(f.path or "/" for f in findings[:5])
        super().__init__(
            f"plain secret values are not stored in a project folder; use secret:// references "
            f"({len(findings)} found at {where})"
        )
        self.findings = findings

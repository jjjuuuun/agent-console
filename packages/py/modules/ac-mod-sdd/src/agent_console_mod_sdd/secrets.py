"""문서 본문 비밀 검사(design §6R.13): 사용자 설정 ``sdd.secret_scan``(off·warn·reject).

스펙·틀 YAML은 공간 저장소의 쓰기 전 검사가 맡는다(프로젝트 공간 ``WriteGuard``). 문서 본문은
산문이라 오탐이 많아 사용자가 고른다: ``warn``(기본)은 저장하고 정보 이슈 ``sdd.secret_suspect``를
싣는다. ``reject``는 저장을 거부한다(422 ``sdd.secret_rejected``). 이슈에는 위치(줄)와 이유만 있고
값은 없다.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.sdd import SpecIssue
from agent_console_secret_rules import SecretRules

SCAN_OFF: Final = "off"
SCAN_WARN: Final = "warn"
SCAN_REJECT: Final = "reject"


class SecretRejectedError(Exception):
    """``secret_scan: reject``에서 본문에 비밀 의심 값이 있다(422 ``sdd.secret_rejected``).

    Attributes:
        issues: 의심 위치(값 없음).
    """

    code = ErrorCodes.SDD_SECRET_REJECTED

    def __init__(self, issues: Iterable[SpecIssue]) -> None:
        self.issues = list(issues)
        super().__init__("비밀로 보이는 값이 있어 저장하지 않았습니다.")

    @property
    def details(self) -> dict[str, Any]:
        return {"issues": [i.model_dump(mode="json", exclude_none=True) for i in self.issues]}


def scan_text(
    rules: SecretRules, text: str, *, document: str | None = None, path: str = ""
) -> list[SpecIssue]:
    """글을 줄마다 검사해 비밀 의심 위치를 낸다(``sdd.secret_suspect``, info).

    Args:
        rules: 비밀 의심 규칙.
        text: 검사할 글.
        document: 문서 id(있으면 이슈에 싣는다).
        path: 이슈 위치 접두(JSON Pointer).

    >>> from agent_console_secret_rules import default_rules
    >>> [i.line for i in scan_text(default_rules(), "hello\\nkey sk-ant-api03-" + "a" * 40)] [2]
    """
    out: list[SpecIssue] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        found = rules.find_suspected(line)
        if not found:
            continue
        extra: dict[str, Any] = {"path": path} if path else {}
        if document is not None:
            extra["document"] = document
        out.append(
            SpecIssue(
                severity="info",
                code=KnownIssueCodes.SDD_SECRET_SUSPECT,
                message="비밀로 보이는 값이 있습니다(값은 보이지 않습니다).",
                line=number,
                details={"reason": found[0].reason},
                **extra,
            )
        )
    return out


__all__ = ["SCAN_OFF", "SCAN_REJECT", "SCAN_WARN", "SecretRejectedError", "scan_text"]

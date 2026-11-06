"""사용자 설정 섹션 ``wiki``(design §7R.1.5) 읽기·검사.

공통 설정 모델(``WorkspaceSettings``)은 이 섹션을 필드로 두지 않고 모르는 키로 보존한다. 이 모듈이
원문을 꺼내 ``WikiSettings``로 해석한다. 깨진 부분만 빼고 쓴다(설정 파일을 손으로 고쳐 깨뜨려도 위키
화면은 동작해야 한다): 최상위 키는 키마다, 쓰기 검사는 항목마다 따로 검증하고 틀린 것은 빼고 문제
(``wiki.settings_invalid``)로 알린다. 모르는 키는 그대로 둔다(``WikiSettings``가 보존).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import ValidationError

from agent_console_contracts import Issue
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import WikiSettings, WikiWriteCheckSetting

SECTION_KEY: Final = "wiki"
"""워크스페이스 설정에서 이 모듈이 소유하는 섹션 이름(설정 문서의 최상위 키)."""

_CHECKS: Final = "write_checks"

type Severity = Literal["error", "warning"]


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def section_of(document: Any, key: str = SECTION_KEY) -> Any:
    """워크스페이스 설정(모델 또는 매핑)에서 섹션 원문을 꺼낸다. 없으면 None."""
    if document is None:
        return None
    if isinstance(document, Mapping):
        return document.get(key)
    extra = getattr(document, "model_extra", None)
    if isinstance(extra, Mapping) and key in extra:
        return extra[key]
    return getattr(document, key, None)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def settings_issue(
    path: str, message: str, severity: Severity = "warning", errors: int = 0
) -> Issue:
    """``wiki.settings_invalid`` 문제 하나(값 원문 없음)."""
    return Issue(
        severity=severity,
        code=KnownIssueCodes.WIKI_SETTINGS_INVALID,
        message=message,
        path=path or "/",
        details={"errors": errors} if errors else {},
    )


def parse_wiki_settings(
    raw: Any, *, base_path: str = f"/{SECTION_KEY}", severity: Severity = "warning"
) -> tuple[WikiSettings, list[Issue]]:
    """섹션 원문 → (``WikiSettings``, 형식 문제). 예외를 내지 않는다.

    Args:
        raw: 섹션 원문(None = 섹션 없음 → 기본값).
        base_path: 문제 위치 접두(설정 문서 기준 JSON Pointer).
        severity: 문제 심각도(서버 경고 ``warning``, 저장 전 검사 ``error``).

    Returns:
        (설정, 문제 목록). 메시지에 값 원문이 없다.

    >>> raw = {"max_versions_per_page": 0, "include_default_syntax": False}
    >>> s, issues = parse_wiki_settings(raw)
    >>> s.include_default_syntax, s.max_versions_per_page, [i.path for i in issues]
    (False, 50, ['/wiki/max_versions_per_page'])
    """
    if raw is None:
        return WikiSettings(), []
    if isinstance(raw, WikiSettings):
        return raw, []
    data = _plain(raw)
    if not isinstance(data, Mapping):
        return WikiSettings(), [
            settings_issue(base_path, "위키 설정이 객체가 아니어서 기본값을 씁니다", severity)
        ]
    issues: list[Issue] = []
    kept: dict[str, Any] = {}
    for key, value in data.items():
        name = str(key)
        where = f"{base_path}/{_escape(name)}"
        if name == _CHECKS:
            kept[name] = _checks(value, where, severity, issues)
            continue
        try:
            WikiSettings.model_validate({name: value})
        except ValidationError as exc:
            issues.append(
                settings_issue(
                    where,
                    f"위키 설정 {name!r} 값이 형식에 맞지 않아 기본값을 씁니다",
                    severity,
                    len(exc.errors()),
                )
            )
            continue
        kept[name] = value
    try:
        return WikiSettings.model_validate(kept), issues
    except ValidationError as exc:  # pragma: no cover - 키마다 검증했으므로 오지 않는다
        return WikiSettings(), [
            *issues,
            settings_issue(base_path, "위키 설정 오류", severity, len(exc.errors())),
        ]


def _checks(value: Any, where: str, severity: Severity, issues: list[Issue]) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(settings_issue(where, "쓰기 검사가 목록이 아니어서 빼고 씁니다", severity))
        return []
    out: list[Any] = []
    for index, item in enumerate(value):
        try:
            WikiWriteCheckSetting.model_validate(item)
        except ValidationError as exc:
            issues.append(
                settings_issue(
                    f"{where}/{index}",
                    "쓰기 검사 항목이 형식에 맞지 않아 빼고 씁니다",
                    severity,
                    len(exc.errors()),
                )
            )
            continue
        out.append(item)
    return out


__all__ = ["SECTION_KEY", "parse_wiki_settings", "section_of", "settings_issue"]

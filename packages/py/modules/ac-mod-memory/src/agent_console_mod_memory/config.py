"""사용자 설정 섹션 ``memory``(design §5.7R.1.4) 읽기·검사.

공통 설정 모델(``WorkspaceSettings``)은 이 섹션을 필드로 두지 않고 모르는 키로 보존한다. 이 모듈이
원문을 꺼내 ``MemorySettings``로 해석한다. 깨진 부분만 빼고 쓴다(설정 파일을 손으로 고쳐 깨뜨려도
메모리 화면과 에이전트 도구는 동작해야 한다): 최상위 키는 키마다, 범위 종류는 id마다, 정리 규칙은
규칙마다 따로 검증하고 틀린 것은 빼고 문제(``memory.settings_invalid``)로 알린다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import ValidationError

from agent_console_contracts import Issue
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.memory import MemoryRetentionRule, MemorySettings
from agent_console_memory import check_scope_kinds

SECTION_KEY: Final = "memory"
"""워크스페이스 설정에서 이 모듈이 소유하는 섹션 이름(설정 문서의 최상위 키)."""

_SCOPE_KINDS: Final = "scope_kinds"
_RETENTION: Final = "retention"
_RULES: Final = "rules"

type Severity = Literal["error", "warning"]


def escape_pointer(token: str) -> str:
    """JSON Pointer 한 마디 이스케이프(``~`` → ``~0``, ``/`` → ``~1``)."""
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


def _issue(path: str, message: str, severity: Severity, errors: int = 0) -> Issue:
    return Issue(
        severity=severity,
        code=KnownIssueCodes.MEMORY_SETTINGS_INVALID,
        message=message,
        path=path or "/",
        details={"errors": errors} if errors else {},
    )


def _plain(value: Any) -> Any:
    """ruamel 등 매핑·목록 형식을 일반 dict·list로(모델 검증·지문용)."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def parse_memory_settings(
    raw: Any,
    *,
    base_path: str = f"/{SECTION_KEY}",
    severity: Severity = "warning",
    rule_issues: bool = True,
) -> tuple[MemorySettings, list[Issue]]:
    """섹션 원문 → (``MemorySettings``, 형식 문제). 예외를 내지 않는다.

    전체가 맞으면 그대로 쓴다(범위 종류 id 틀 검사는 따로 한다). 틀린 곳이 있으면 맞는 부분만
    남긴다: 최상위 키마다, ``scope_kinds``는 id마다, ``retention.rules``는 규칙마다 검증한다.

    Args:
        raw: 섹션 원문(None = 섹션 없음).
        base_path: 문제 위치 접두(설정 문서 기준 JSON Pointer, 섹션 기준이면 빈 문자열).
        severity: 문제 심각도(서버 경고는 ``warning``, 저장 전 검사는 ``error``).
        rule_issues: False면 형식이 틀린 정리 규칙을 문제로 알리지 않고 빼기만 한다(규칙 검사를
            ``compile_retention_rules``로 따로 하는 쪽 — 같은 문제를 두 번 알리지 않게).

    Returns:
        (설정, 문제 목록). 메시지에 값 원문이 없다.
    """
    if raw is None:
        return MemorySettings(), []
    if isinstance(raw, MemorySettings):
        data: Any = raw.model_dump(mode="json", exclude_unset=True)
    else:
        data = _plain(raw)
    if not isinstance(data, Mapping):
        return MemorySettings(), [
            _issue(base_path, "메모리 설정이 객체가 아니어서 기본값을 씁니다", severity)
        ]
    issues: list[Issue] = []
    kept: dict[str, Any] = {}
    for key, value in data.items():
        name = str(key)
        where = f"{base_path}/{escape_pointer(name)}"
        if name == _SCOPE_KINDS:
            kept[name] = _scope_kinds(value, where, severity, issues)
            continue
        if name == _RETENTION:
            kept[name] = _retention(value, where, severity, issues, rule_issues=rule_issues)
            continue
        try:
            MemorySettings.model_validate({name: value})
        except ValidationError as exc:
            issues.append(
                _issue(
                    where,
                    f"메모리 설정 {name!r} 값이 형식에 맞지 않아 기본값을 씁니다",
                    severity,
                    len(exc.errors()),
                )
            )
            continue
        kept[name] = value
    try:
        return MemorySettings.model_validate(kept), issues
    except ValidationError as exc:  # pragma: no cover - 키마다 검증했으므로 오지 않는다
        return MemorySettings(), [
            *issues,
            _issue(base_path, "메모리 설정 오류", severity, len(exc.errors())),
        ]


def _scope_kinds(value: Any, where: str, severity: Severity, issues: list[Issue]) -> Any:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        issues.append(
            _issue(where, "범위 종류 목록이 객체가 아니어서 사용자 범위 종류 없이 씁니다", severity)
        )
        return {}
    prefix = f"/{_SCOPE_KINDS}"
    broken: set[str] = set()
    for problem in check_scope_kinds(value):
        # 경로 = /scope_kinds/<id>[/...] (섹션 기준). id 마디를 꺼내 그 종류만 뺀다.
        rest = (problem.path or "").removeprefix(prefix)
        token = rest.split("/")[1] if rest.startswith("/") else ""
        broken.add(token.replace("~1", "/").replace("~0", "~"))
        issues.append(problem.model_copy(update={"severity": severity, "path": f"{where}{rest}"}))
    return {k: v for k, v in value.items() if str(k) not in broken}


def _retention(
    value: Any, where: str, severity: Severity, issues: list[Issue], *, rule_issues: bool
) -> Any:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        issues.append(_issue(where, "정리 설정이 객체가 아니어서 정리 규칙 없이 씁니다", severity))
        return {}
    kept: dict[str, Any] = {}
    for key, body in value.items():
        name = str(key)
        if name != _RULES:
            kept[name] = body
            continue
        if body is None:
            kept[name] = []
            continue
        if not isinstance(body, list):
            issues.append(
                _issue(f"{where}/{_RULES}", "정리 규칙이 목록이 아니어서 빼고 씁니다", severity)
            )
            kept[name] = []
            continue
        rules: list[Any] = []
        for index, rule in enumerate(body):
            try:
                MemoryRetentionRule.model_validate(rule)
            except ValidationError as exc:
                if not rule_issues:
                    continue
                issues.append(
                    _issue(
                        f"{where}/{_RULES}/{index}",
                        "정리 규칙이 형식에 맞지 않아 빼고 씁니다",
                        severity,
                        len(exc.errors()),
                    )
                )
                continue
            rules.append(rule)
        kept[name] = rules
    try:
        MemorySettings.model_validate({_RETENTION: kept})
    except ValidationError as exc:
        issues.append(
            _issue(
                where, "정리 설정이 형식에 맞지 않아 기본값을 씁니다", severity, len(exc.errors())
            )
        )
        return {}
    return kept


__all__ = [
    "SECTION_KEY",
    "escape_pointer",
    "parse_memory_settings",
    "section_of",
]

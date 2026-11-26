"""공통 설정(``WorkspaceSettings``)과 비밀 의심 규칙(``SecretRules``)을 저장소에서 읽는다.

- ``workspace.settings`` 포트 = ``WorkspaceState.settings``: 저장 원문을 모델로 읽는다(파일이 없으면
  기본값). 버전 해시가 같으면 읽어 둔 모델을 다시 쓴다.
- ``secrets.rules`` 포트 = ``WorkspaceState.rules``: 기본 규칙 + 설정 ``secrets.extra_*``, 약한 키
  이름은 설정 ``secrets.weak_key_names``(null = 기본 데이터, 설정 버전마다 한 번 만든다). 잘못된
  추가 규칙·약한 이름(손으로 고친 파일)은 빼고 경고 로그.
- ``SecretRuleCheck``: 공통 설정 저장 전 검사 — 사용자 규칙이 위험·잘못된 정규식이면 error
  (``secret.invalid_rule``, 패턴 원문은 메시지에 없음).
- ``ignored_settings_issues``: 공통 설정에 남은 옛 최상위 키(예: ``projects``·``default_backend``) →
  정보 ``settings.ignored_key``(``server.warnings``, 읽기·시작은 막지 않음). 값을 옮길 새 위치가
  있는 키(``RENAMED_SETTINGS_KEYS``)는 그 위치를 문구와 ``details.replacement``로 안내한다.
"""

from __future__ import annotations

import logging
import string
import threading
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from agent_console_contracts import (
    Issue,
    KnownIssueCodes,
    SecretRuleSettings,
    WorkspaceSettings,
    ignored_settings_keys,
)
from agent_console_secret_rules import (
    InvalidSecretRuleError,
    RuleProblem,
    SecretRules,
    check_extra_rules,
    default_rules,
)
from agent_console_store import SETTINGS_KIND, DefinitionStore, NotFound

_log = logging.getLogger("agent_console_mod_definitions")

INVALID_RULE = "secret.invalid_rule"
"""설정 ``secrets.extra_*`` 규칙이 잘못됨(설정 저장 422)."""

SECRETS_POINTER = "/secrets"
"""공통 설정 문서에서 비밀 규칙 묶음의 위치."""

WEAK_KEY_NAMES = "weak_key_names"
"""설정 ``secrets``의 약한 키 이름 필드(``RuleProblem.field``와 같은 이름)."""

IGNORED_SETTINGS_MESSAGE = (
    "공통 설정의 ${key}는 더 이상 읽지 않습니다. 새 구성은 만드는 곳(공용 구성 또는 프로젝트)에 "
    "저장됩니다. 설정에서 지워도 됩니다"
)
"""``ignored_settings_issues`` 기본 문구(``string.Template``, 변수 ``key`` = 키 경로)."""

RENAMED_SETTINGS_KEYS: Final[Mapping[str, str]] = MappingProxyType(
    {"default_backend": "agent_defaults.backend"}
)
"""공통 설정에서 읽고 무시하는 옛 최상위 키 → 같은 값을 둘 새 위치(점으로 구분한 경로).

``default_backend``는 1.1.0부터 읽지 않는다(실행 백엔드 공통 기본값은 ``agent_defaults.backend``).
계약 ``IGNORED_SETTINGS_KEYS``에 아직 없는 키도 여기 있으면 찾는다(모델 필드가 남아 있어도 입력에
값이 있었을 때만). 계약 목록과 겹치는 키는 한 번만 낸다."""

RENAMED_SETTINGS_MESSAGE = (
    "공통 설정의 ${key}는 더 이상 읽지 않습니다. 같은 값을 ${replacement}에 두세요. "
    "설정에서 지워도 됩니다"
)
"""새 위치가 있는 옛 키의 기본 문구(``string.Template``, 변수 ``key``·``replacement``)."""


def _top_level_present(settings: WorkspaceSettings | Mapping[str, Any], key: str) -> bool:
    """최상위 ``key``에 값이 있는가(null은 없음). 모델이면 입력에 있었던 필드·모르는 키만 센다."""
    if isinstance(settings, BaseModel):
        if key in type(settings).model_fields:
            return key in settings.model_fields_set and getattr(settings, key) is not None
        return (settings.model_extra or {}).get(key) is not None
    return settings.get(key) is not None


def ignored_settings_issues(
    settings: WorkspaceSettings | Mapping[str, Any] | None,
    *,
    message: str = IGNORED_SETTINGS_MESSAGE,
    renamed: Mapping[str, str] = RENAMED_SETTINGS_KEYS,
    renamed_message: str = RENAMED_SETTINGS_MESSAGE,
) -> list[Issue]:
    """공통 설정에 남은 옛 최상위 키 → 정보 ``settings.ignored_key``(``details.key`` = 키 경로).

    키 목록은 계약 ``IGNORED_SETTINGS_KEYS``(점 없는 것) 다음에 ``renamed``의 키다(겹치면 한 번).
    ``renamed``에 새 위치가 있는 키는 문구 ``renamed_message``와 ``details.replacement``로 그 위치를
    안내한다. 섹션 아래 키(예: ``logs.projects``)는 그 섹션을 읽는 모듈이 낸다(같은 이슈를 두 번
    내지 않게). 모델 필드가 있든 없든 같은 답이다.

    Args:
        settings: 공통 설정(모델·dict). None이면 빈 목록.
        message: 새 위치가 없는 키의 문구(변수 ``key``).
        renamed: 옛 최상위 키 → 새 위치. 빈 매핑이면 계약 목록만 본다.
        renamed_message: 새 위치가 있는 키의 문구(변수 ``key``·``replacement``).

    >>> doc = {"projects": {}, "logs": {"projects": {}}}
    >>> [(i.code, i.details) for i in ignored_settings_issues(doc)]
    [('settings.ignored_key', {'key': 'projects'})]
    >>> [i.details for i in ignored_settings_issues({"default_backend": "b"})]
    [{'key': 'default_backend', 'replacement': 'agent_defaults.backend'}]
    >>> ignored_settings_issues(None), ignored_settings_issues({"default_backend": None})
    ([], [])
    """
    if settings is None:
        return []
    keys = [key for key in ignored_settings_keys(settings) if "." not in key]
    keys += [
        key
        for key in renamed
        if "." not in key and key not in keys and _top_level_present(settings, key)
    ]
    issues: list[Issue] = []
    for key in keys:
        replacement = renamed.get(key)
        if replacement is None:
            text = string.Template(message).safe_substitute(key=key)
            details: dict[str, Any] = {"key": key}
        else:
            text = string.Template(renamed_message).safe_substitute(
                key=key, replacement=replacement
            )
            details = {"key": key, "replacement": replacement}
        issues.append(
            Issue(
                severity="info",
                code=KnownIssueCodes.SETTINGS_IGNORED_KEY,
                message=text,
                details=details,
            )
        )
    return issues


def rule_problem_issues(problems: Iterable[RuleProblem]) -> list[Issue]:
    """사용자 규칙 문제 → 설정 문서 기준 error 이슈(패턴 원문은 메시지에 넣지 않는다)."""
    return [
        Issue(
            severity="error",
            code=INVALID_RULE,
            message=p.message,
            path=f"{SECRETS_POINTER}/{p.field}/{p.index}",
        )
        for p in problems
    ]


def settings_rule_issues(settings: SecretRuleSettings) -> list[Issue]:
    """설정 ``secrets``의 사용자 규칙 검사(위험·잘못된 정규식, 빈 이름, 약한 이름)."""
    problems = check_extra_rules(settings.extra_key_names, settings.extra_value_patterns)
    if settings.weak_key_names is not None:
        problems += weak_name_problems(settings.weak_key_names)
    return rule_problem_issues(problems)


def weak_name_problems(names: Sequence[str]) -> list[RuleProblem]:
    """약한 키 이름 목록의 문제(``RuleProblem.field`` = ``weak_key_names``, 설정 필드 이름)."""
    try:
        SecretRules(weak_key_names=names)
    except InvalidSecretRuleError as exc:
        return [p for p in exc.problems if p.field == WEAK_KEY_NAMES]
    return []


def _base_rules(weak_key_names: Sequence[str] | None) -> SecretRules:
    """기본 규칙. 약한 키 이름을 주면(설정 ``secrets.weak_key_names``) 그 목록으로 바꾼다.

    잘못된 이름은 빼고 경고 로그(위치만)."""
    if weak_key_names is None:
        return default_rules()
    bad = {p.index for p in weak_name_problems(weak_key_names)}
    if bad:
        _log.warning("약한 키 이름 %d개가 잘못돼 빼고 씁니다(위치만: %s)", len(bad), sorted(bad))
    return SecretRules(weak_key_names=[n for i, n in enumerate(weak_key_names) if i not in bad])


def build_rules(settings: SecretRuleSettings) -> SecretRules:
    """기본 규칙(약한 키 이름은 설정값, null이면 기본 데이터) + 사용자 추가분.

    잘못된 추가분·약한 이름은 빼고 경고 로그(위치만)."""
    base = _base_rules(settings.weak_key_names)
    try:
        return base.with_extra(
            key_names=settings.extra_key_names, value_patterns=settings.extra_value_patterns
        )
    except InvalidSecretRuleError as exc:
        bad = {(p.field, p.index) for p in exc.problems}
        _log.warning("비밀 규칙 %d개가 잘못돼 빼고 씁니다(위치만: %s)", len(bad), sorted(bad))
        names = [
            n for i, n in enumerate(settings.extra_key_names) if ("extra_key_names", i) not in bad
        ]
        patterns = [
            p
            for i, p in enumerate(settings.extra_value_patterns)
            if ("extra_value_patterns", i) not in bad
        ]
        return base.with_extra(key_names=names, value_patterns=patterns)


class SecretRuleCheck:
    """``definitions.checks`` 하나: 공통 설정의 사용자 비밀 규칙 검사.

    Args:
        settings_kind: 공통 설정 정의 종류 이름.
    """

    def __init__(self, settings_kind: str = SETTINGS_KIND.name) -> None:
        self._kind = settings_kind

    def issues(self, kind: str, document: Mapping[str, Any] | BaseModel) -> Sequence[Issue]:
        if kind != self._kind:
            return []
        try:
            settings = (
                document
                if isinstance(document, WorkspaceSettings)
                else WorkspaceSettings.model_validate(
                    document.model_dump(mode="json", exclude_unset=True)
                    if isinstance(document, BaseModel)
                    else document
                )
            )
        except ValidationError:
            return []  # 모델 검증은 저장소가 따로 한다
        return settings_rule_issues(settings.secrets)


class WorkspaceState:
    """저장소의 공통 설정과 거기서 만든 비밀 규칙(버전별 캐시, 스레드 안전).

    Args:
        store: 정의 저장소.
        kind: 공통 설정 종류 이름(싱글턴 id = 종류 이름).
    """

    def __init__(self, store: DefinitionStore, kind: str = SETTINGS_KIND.name) -> None:
        self._store = store
        self._kind = kind
        self._lock = threading.Lock()
        self._version: str | None = None
        self._settings = WorkspaceSettings()
        self._rules_version: str | None = None
        self._rules = default_rules()

    def _current(self) -> tuple[WorkspaceSettings, str]:
        try:
            stored = self._store.get(self._kind, self._kind)
        except NotFound:
            return WorkspaceSettings(), ""
        with self._lock:
            if stored.version_hash == self._version:
                return self._settings, stored.version_hash
        model = stored.model(WorkspaceSettings)
        with self._lock:
            self._settings, self._version = model, stored.version_hash
        return model, stored.version_hash

    def settings(self) -> WorkspaceSettings:
        """지금 공통 설정(파일이 없으면 기본값). 손상된 파일이면 저장소·모델 오류를 그대로 낸다."""
        return self._current()[0]

    def rules(self) -> SecretRules:
        """지금 비밀 의심 규칙(기본 + 설정 ``secrets.extra_*``)."""
        current, version = self._current()
        with self._lock:
            if version == self._rules_version:
                return self._rules
        rules = build_rules(current.secrets)
        with self._lock:
            self._rules, self._rules_version = rules, version
        return rules


__all__ = [
    "IGNORED_SETTINGS_MESSAGE",
    "INVALID_RULE",
    "SECRETS_POINTER",
    "SecretRuleCheck",
    "WorkspaceState",
    "build_rules",
    "ignored_settings_issues",
    "rule_problem_issues",
    "settings_rule_issues",
]

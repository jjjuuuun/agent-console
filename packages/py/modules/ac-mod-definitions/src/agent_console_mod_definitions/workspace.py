"""공통 설정(``WorkspaceSettings``)과 비밀 의심 규칙(``SecretRules``)을 저장소에서 읽는다.

- ``workspace.settings`` 포트 = ``WorkspaceState.settings``: 저장 원문을 모델로 읽는다(파일이 없으면
  기본값). 버전 해시가 같으면 읽어 둔 모델을 다시 쓴다.
- ``secrets.rules`` 포트 = ``WorkspaceState.rules``: 기본 규칙 + 설정 ``secrets.extra_*``, 약한 키
  이름은 설정 ``secrets.weak_key_names``(null = 기본 데이터, 설정 버전마다 한 번 만든다). 잘못된
  추가 규칙·약한 이름(손으로 고친 파일)은 빼고 경고 로그.
- ``SecretRuleCheck``: 공통 설정 저장 전 검사 — 사용자 규칙이 위험·잘못된 정규식이면 error
  (``secret.invalid_rule``, 패턴 원문은 메시지에 없음).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from agent_console_contracts import Issue, SecretRuleSettings, WorkspaceSettings
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
    "INVALID_RULE",
    "SECRETS_POINTER",
    "SecretRuleCheck",
    "WorkspaceState",
    "build_rules",
    "rule_problem_issues",
    "settings_rule_issues",
]

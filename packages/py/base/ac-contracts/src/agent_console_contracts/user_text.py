"""사용자 문구 금지 패턴(설계 문서 번호·내부 노드 id) 데이터와 검사 도우미.

규칙은 패키지 데이터 ``data/user_text_rules.json`` 한 곳에 있다. Python 테스트는 이 모듈로, TS
테스트는 생성된 계약 상수 ``USER_TEXT_RULES``로 같은 데이터를 읽는다. 범위(``scope``)는 열린
문자열이며 알려진 값은 ``description``(계약·디스크립터 설명)과 ``messages``(서버·웹 사용자 문구)다.

    >>> from agent_console_contracts.user_text import find_forbidden_text
    >>> [v.rule for v in find_forbidden_text("노드 'n1' 실패", scope="messages")]
    ['node-id']
    >>> find_forbidden_text("'안내원' 실패", scope="messages")
    []
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

__all__ = [
    "UserTextRule",
    "UserTextViolation",
    "find_forbidden_text",
    "scan_forbidden_text",
    "user_text_rules",
    "user_text_rules_data",
]

_DATA = "user_text_rules.json"


@dataclass(frozen=True, slots=True)
class UserTextRule:
    """금지 패턴 하나.

    Attributes:
        id: 규칙 id(보고용).
        pattern: 컴파일한 정규식.
        scopes: 이 규칙을 적용할 범위 이름들.
        reason: 왜 금지하는지(사람용).
    """

    id: str
    pattern: re.Pattern[str]
    scopes: frozenset[str]
    reason: str


@dataclass(frozen=True, slots=True)
class UserTextViolation:
    """위반 하나: 어디(``path``)의 어떤 문자열이 어떤 규칙에 걸렸는가."""

    rule: str
    path: str
    match: str
    text: str


@cache
def user_text_rules_data() -> dict[str, Any]:
    """규칙 데이터 원본(JSON 객체). 계약 생성물의 상수 ``USER_TEXT_RULES``도 이 값에서 만든다."""
    raw = files("agent_console_contracts").joinpath("data", _DATA).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
    return data


@cache
def user_text_rules() -> tuple[UserTextRule, ...]:
    """컴파일한 규칙 목록(데이터 순서)."""
    return tuple(
        UserTextRule(
            id=str(r["id"]),
            pattern=re.compile(str(r["pattern"])),
            scopes=frozenset(str(s) for s in r.get("scopes", ())),
            reason=str(r.get("reason", "")),
        )
        for r in user_text_rules_data()["patterns"]
    )


def find_forbidden_text(
    text: str,
    *,
    scope: str,
    path: str = "",
    rules: Iterable[UserTextRule] | None = None,
) -> list[UserTextViolation]:
    """문자열 하나에서 ``scope``에 적용되는 금지 패턴을 찾는다(없으면 빈 목록).

    Args:
        text: 검사할 문구.
        scope: 범위 이름(예: ``"messages"``).
        path: 보고에 붙일 위치(선택).
        rules: 쓸 규칙(기본 = 패키지 데이터).
    """
    found: list[UserTextViolation] = []
    for rule in user_text_rules() if rules is None else rules:
        if scope not in rule.scopes:
            continue
        m = rule.pattern.search(text)
        if m is not None:
            found.append(UserTextViolation(rule.id, path, m.group(0), text))
    return found


def scan_forbidden_text(
    value: Any,
    *,
    scope: str,
    path: str = "",
    keys: Iterable[str] | None = None,
    rules: Iterable[UserTextRule] | None = None,
) -> list[UserTextViolation]:
    """JSON 값(객체·배열·문자열)을 훑어 금지 패턴을 찾는다.

    Args:
        value: 검사할 값(``model_dump(mode="json")`` 결과 등).
        scope: 범위 이름.
        path: 시작 위치(JSON Pointer 모양으로 이어 붙인다).
        keys: 주면 이 이름의 객체 키에 든 문자열만 본다(예: ``{"description", "title"}``).
            None이면 모든 문자열을 본다.
        rules: 쓸 규칙(기본 = 패키지 데이터).
    """
    only = None if keys is None else frozenset(keys)
    picked = list(user_text_rules() if rules is None else rules)
    found: list[UserTextViolation] = []

    def walk(node: Any, at: str, key: str | None) -> None:
        if isinstance(node, str):
            if only is None or key in only:
                found.extend(find_forbidden_text(node, scope=scope, path=at, rules=picked))
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{at}/{k}", str(k))
        elif isinstance(node, list | tuple):
            for i, v in enumerate(node):
                walk(v, f"{at}/{i}", key)

    walk(value, path, None)
    return found

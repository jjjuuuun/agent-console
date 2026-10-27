"""설정 폼 도움말 린트: JSON Schema의 각 필드가 설명·분류·예시를 갖는지 본다.

폼은 스키마에서 그린다. 그래서 필드마다 **무엇·왜**(``description``), **기본/고급**(``x-ui.tier``),
값을 짐작할 **예시나 기본값**이 스키마에 있어야 한다. 이 모듈은 그 규칙을 검사하는 순수 함수다.
계약 모델, 번들 플러그인, 외부 플러그인의 ``config_schema``에 똑같이 쓴다(심각도는 호출자가 정한다).

규칙(``rule`` 값):

- ``missing-title``: 라벨(``title``)이 없다.
- ``missing-description``: 설명이 없다.
- ``description-too-long``: 설명이 규칙 데이터의 ``max_description_length``(기본 100자)를 넘는다.
- ``description-same-as-title``: 설명이 라벨과 같은 문장이다.
- ``missing-tier``·``bad-tier``: ``x-ui.tier``가 없거나 ``basic``·``advanced``가 아니다.
- ``unknown-x-ui-key``: ``x-ui`` 안에 모르는 키가 있다(오타 방지).
- ``missing-example``: 비워 둘 수 있는 문자열·숫자 필드에 예시(``x-ui.example``·``examples``)도
  null 아닌 기본값도 없다.
- ``missing-enum-labels``: 고르는 값(``enum``, 또는 enum을 가진 ``$ref``·``anyOf``·``oneOf``, 배열
  ``items``의 enum = 다중 선택)에 사람이 읽는 라벨이 없다. 필드의 ``x-ui.enum_labels``(값 → 라벨)가
  모든 값을 덮거나, 선택지가 ``oneOf``의 ``title``을 가져야 한다. 배열이면 라벨은 ``items``가 아니라
  배열 필드의 ``x-ui``에 둔다(다중 선택 위젯이 배열 스키마를 받는다).
- ``forbidden-text``·``jargon``: 설명·``x-ui.when``에 설계 문서 번호(공통 금지 패턴) 또는 개발자용
  표현이 있다.
- ``missing-when``: 규칙 데이터 ``when_required_tiers``(기본 ``basic``) 필드에
  "언제 바꾸나"(``x-ui.when``)가 없다.
- ``hard-term``: 설명·``when``에 사용자에게 어려운 용어(규칙 데이터 ``hard_terms``)가
  풀이 없이 있다(같은 필드 설명에 풀이가 있으면 된다). 기본 심각도는 경고다(``severity``).

각 결과의 ``severity``(``error``·``warning``)는 규칙 데이터 ``severity``에서 온다. 호출자는 이 값과
출처(번들·외부)로 최종 심각도를 정한다.

``const`` 필드(문서 종류 표시 등 사용자가 고르지 않는 값)는 보지 않는다.

``objects=True``면 객체 스키마 자체의 설명(모델 docstring에서 온 ``description``)도 문구 규칙
(``forbidden-text``·``jargon``·``hard-term``)으로 본다. 폼은 이 설명을 폼·묶음 머리말로 보이므로
내부 클래스 이름·필드 경로가 들어가면 안 된다. 계약 폼(``lint_contract_help``)은 켜서 검사한다.

    >>> from agent_console_contracts.schema_help import lint_schema_help
    >>> schema = {"type": "object", "properties": {"n": {"type": "integer", "title": "개수"}}}
    >>> sorted(i.rule for i in lint_schema_help(schema))
    ['missing-description', 'missing-example', 'missing-tier']
    >>> good = {"type": "object", "properties": {"n": {
    ...     "type": "integer", "title": "개수", "default": 3,
    ...     "description": "한 번에 보일 항목 수입니다.", "x-ui": {"tier": "advanced"}}}}
    >>> lint_schema_help(good)
    []
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel

from ._base import DefinitionModel
from .common import X_UI, X_UI_TIERS, XUiKeys
from .user_text import UserTextRule, find_forbidden_text

__all__ = [
    "HelpIssue",
    "contract_form_roots",
    "lint_contract_help",
    "lint_schema_help",
    "schema_help_rules_data",
]

_DATA = "schema_help_rules.json"
_SCALAR_TYPES = frozenset({"string", "number", "integer"})
_KNOWN_X_UI_KEYS = frozenset(
    v for k, v in vars(XUiKeys).items() if k.isupper() and isinstance(v, str)
)
_SCHEMA_KIDS = ("anyOf", "oneOf", "allOf")


@dataclass(frozen=True, slots=True)
class HelpIssue:
    """린트 결과 하나.

    Attributes:
        rule: 규칙 id(모듈 문서의 목록).
        path: 문제 필드의 JSON Pointer 모양 위치(예: ``#/$defs/Agent/properties/name``).
        message: 사람이 읽는 설명.
    """

    rule: str
    path: str
    message: str
    severity: str = "error"


def _severity(rule: str) -> str:
    table = schema_help_rules_data().get("severity", {})
    rules = table.get("by_rule", {}) if isinstance(table, dict) else {}
    default = table.get("default", "error") if isinstance(table, dict) else "error"
    return str(rules.get(rule, default))


def _issue(rule: str, where: str, message: str) -> HelpIssue:
    return HelpIssue(rule, where, message, _severity(rule))


@cache
def schema_help_rules_data() -> dict[str, Any]:
    """규칙 데이터 원본(``data/schema_help_rules.json``)."""
    raw = files("agent_console_contracts").joinpath("data", _DATA).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
    return data


@cache
def _jargon_rules() -> tuple[UserTextRule, ...]:
    return tuple(
        UserTextRule(
            id=str(r["id"]),
            pattern=re.compile(str(r["pattern"])),
            scopes=frozenset({"help"}),
            reason=str(r.get("reason", "")),
        )
        for r in schema_help_rules_data().get("jargon", ())
    )


def _norm(text: str) -> str:
    return re.sub(r"[\s.。·,:()\[\]]+", "", text).casefold()


def _types(prop: Mapping[str, Any]) -> tuple[set[str], bool]:
    """속성이 받을 수 있는 JSON 형식과 '고르는 값(enum·const·$ref)'인지."""
    found: set[str] = set()
    choice = "enum" in prop or "const" in prop or "$ref" in prop
    raw = prop.get("type")
    if isinstance(raw, str):
        found.add(raw)
    elif isinstance(raw, list):
        found.update(str(t) for t in raw)
    for key in _SCHEMA_KIDS:
        for sub in prop.get(key, ()) or ():
            if isinstance(sub, Mapping):
                sub_types, sub_choice = _types(sub)
                found |= sub_types
                choice = choice or sub_choice
    return found, choice


def _has_example(prop: Mapping[str, Any]) -> bool:
    x_ui = prop.get(X_UI)
    if isinstance(x_ui, Mapping) and XUiKeys.EXAMPLE in x_ui:
        return True
    examples = prop.get("examples")
    if isinstance(examples, list) and examples:
        return True
    return prop.get("default") is not None


@cache
def _hard_terms() -> tuple[tuple[str, re.Pattern[str], re.Pattern[str] | None, str], ...]:
    out = []
    for r in schema_help_rules_data().get("hard_terms", ()):
        explained = r.get("explained")
        out.append(
            (
                str(r["id"]),
                re.compile(str(r["pattern"])),
                re.compile(str(explained)) if explained else None,
                str(r.get("reason", "")),
            )
        )
    return tuple(out)


def _check_hard_terms(text: str, where: str, issues: list[HelpIssue], context: str) -> None:
    for term_id, pattern, explained, reason in _hard_terms():
        m = pattern.search(text)
        if m is None or (explained is not None and explained.search(context)):
            continue
        issues.append(
            _issue("hard-term", where, f"어려운 용어 {m.group(0)!r}({term_id}): {reason}")
        )


def _check_text(text: str, where: str, issues: list[HelpIssue], context: str | None = None) -> None:
    for v in find_forbidden_text(text, scope="description"):
        issues.append(_issue("forbidden-text", where, f"사용자 문구 금지 패턴 {v.match!r}"))
    for v in find_forbidden_text(text, scope="help", rules=_jargon_rules()):
        issues.append(_issue("jargon", where, f"개발자용 표현 {v.match!r}({v.rule})"))
    _check_hard_terms(text, where, issues, text if context is None else f"{context}\n{text}")


def _enum_values(
    prop: Mapping[str, Any], defs: Mapping[str, Any], seen: frozenset[str] = frozenset()
) -> tuple[list[str], bool]:
    """속성이 고르게 하는 문자열 값 목록과, 선택지마다 ``title``이 이미 있는지.

    ``enum``·``$ref``·``anyOf``·``oneOf``·``allOf``와 배열 ``items``(다중 선택) 안까지 본다.
    배열의 선택지 라벨은 폼의 다중 선택 위젯이 읽는 **배열 필드** ``x-ui.enum_labels``에 둔다.
    """
    values: list[str] = []
    titled = True
    raw = prop.get("enum")
    if isinstance(raw, list):
        values += [v for v in raw if isinstance(v, str)]
        titled = False
    ref = prop.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        target = defs.get(name)
        if name not in seen and isinstance(target, Mapping):
            sub, sub_titled = _enum_values(target, defs, seen | {name})
            values += sub
            titled = titled and sub_titled
    for key in _SCHEMA_KIDS:
        for sub_node in prop.get(key, ()) or ():
            if not isinstance(sub_node, Mapping):
                continue
            const = sub_node.get("const")
            if isinstance(const, str):
                values.append(const)
                titled = titled and isinstance(sub_node.get("title"), str)
                continue
            sub, sub_titled = _enum_values(sub_node, defs, seen)
            values += sub
            titled = titled and sub_titled
    items = prop.get("items")
    if isinstance(items, Mapping):
        sub, sub_titled = _enum_values(items, defs, seen)
        values += sub
        titled = titled and sub_titled
    return values, titled


def _check_enum_labels(
    name: str, prop: Mapping[str, Any], defs: Mapping[str, Any], where: str, issues: list[HelpIssue]
) -> None:
    values, titled = _enum_values(prop, defs)
    if len(values) < 2 or titled:
        return
    x_ui = prop.get(X_UI)
    labels = x_ui.get(XUiKeys.ENUM_LABELS) if isinstance(x_ui, Mapping) else None
    have = (
        {k for k, v in labels.items() if isinstance(v, str) and v.strip()}
        if isinstance(labels, Mapping)
        else set()
    )
    missing = [v for v in dict.fromkeys(values) if v not in have]
    if missing:
        issues.append(
            _issue(
                "missing-enum-labels",
                where,
                f"{name}: 선택지 {missing}의 라벨(x-ui.enum_labels)이 없습니다",
            )
        )


def _check_property(
    name: str,
    prop: Mapping[str, Any],
    required: bool,
    where: str,
    issues: list[HelpIssue],
    defs: Mapping[str, Any] | None = None,
) -> None:
    if "const" in prop:
        return
    max_len = int(schema_help_rules_data().get("max_description_length", 100))
    title = prop.get("title")
    description = prop.get("description")
    if not isinstance(title, str) or not title.strip():
        issues.append(_issue("missing-title", where, f"{name}: 라벨(title)이 없습니다"))
    if not isinstance(description, str) or not description.strip():
        issues.append(_issue("missing-description", where, f"{name}: 설명이 없습니다"))
    else:
        if len(description) > max_len:
            issues.append(
                _issue(
                    "description-too-long",
                    where,
                    f"{name}: 설명이 {len(description)}자입니다(최대 {max_len}자)",
                )
            )
        if isinstance(title, str) and _norm(title) == _norm(description):
            issues.append(
                _issue("description-same-as-title", where, f"{name}: 설명이 라벨과 같습니다")
            )
        _check_text(description, f"{where}/description", issues)
    x_ui = prop.get(X_UI)
    tier = x_ui.get(XUiKeys.TIER) if isinstance(x_ui, Mapping) else None
    if tier is None:
        issues.append(_issue("missing-tier", where, f"{name}: x-ui.tier가 없습니다"))
    elif tier not in X_UI_TIERS:
        issues.append(_issue("bad-tier", where, f"{name}: 알 수 없는 tier {tier!r}"))
    when_tiers = schema_help_rules_data().get("when_required_tiers", ())
    has_when = isinstance(x_ui, Mapping) and isinstance(x_ui.get(XUiKeys.WHEN), str)
    if tier in when_tiers and not has_when:
        issues.append(_issue("missing-when", where, f"{name}: 언제 바꾸는지(x-ui.when)가 없습니다"))
    if isinstance(x_ui, Mapping):
        unknown = sorted(str(k) for k in x_ui if k not in _KNOWN_X_UI_KEYS)
        if unknown:
            issues.append(_issue("unknown-x-ui-key", where, f"{name}: 모르는 x-ui 키 {unknown}"))
        when = x_ui.get(XUiKeys.WHEN)
        if isinstance(when, str):
            context = description if isinstance(description, str) else None
            _check_text(when, f"{where}/{X_UI}/{XUiKeys.WHEN}", issues, context)
    _check_enum_labels(name, prop, defs or {}, where, issues)
    types, choice = _types(prop)
    if not required and not choice and types & _SCALAR_TYPES and not _has_example(prop):
        issues.append(
            _issue("missing-example", where, f"{name}: 예시(x-ui.example)나 기본값이 없습니다")
        )


def _walk(
    node: Any,
    at: str,
    issues: list[HelpIssue],
    *,
    into_defs: bool,
    objects: bool = False,
    defs: Mapping[str, Any] | None = None,
) -> None:
    """스키마 노드 하나를 훑는다. ``properties``의 각 속성을 검사하고 하위 스키마로 내려간다.

    ``objects``면 ``properties``를 가진 객체 스키마의 설명도 문구 규칙으로 본다.
    """
    if not isinstance(node, Mapping):
        return
    props = node.get("properties")
    if objects and isinstance(props, Mapping):
        description = node.get("description")
        if isinstance(description, str):
            _check_text(description, f"{at}/description", issues)
    if isinstance(props, Mapping):
        required = set(node.get("required", ()) or ())
        for name, prop in props.items():
            where = f"{at}/properties/{name}"
            if isinstance(prop, Mapping):
                _check_property(str(name), prop, name in required, where, issues, defs)
                _walk(prop, where, issues, into_defs=False, objects=objects, defs=defs)
    for key in ("items", "additionalProperties", "not"):
        sub = node.get(key)
        if isinstance(sub, Mapping):
            _walk(sub, f"{at}/{key}", issues, into_defs=False, objects=objects, defs=defs)
    for key in _SCHEMA_KIDS:
        for i, sub in enumerate(node.get(key, ()) or ()):
            _walk(sub, f"{at}/{key}/{i}", issues, into_defs=False, objects=objects, defs=defs)
    if into_defs:
        for key in ("$defs", "definitions"):
            defs = node.get(key)
            if isinstance(defs, Mapping):
                for name, sub in defs.items():
                    _walk(
                        sub,
                        f"{at}/{key}/{name}",
                        issues,
                        into_defs=False,
                        objects=objects,
                        defs=defs,
                    )


def _refs(node: Any, out: set[str]) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                out.add(value.rsplit("/", 1)[-1])
            else:
                _refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _refs(value, out)


def _closure(defs: Mapping[str, Any], roots: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    stack = [r for r in roots if r in defs]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        found: set[str] = set()
        _refs(defs[name], found)
        stack.extend(n for n in found if n in defs and n not in seen)
    return sorted(seen)


def lint_schema_help(
    schema: Mapping[str, Any],
    *,
    path: str = "#",
    roots: Collection[str] | None = None,
    objects: bool = False,
) -> list[HelpIssue]:
    """스키마의 필드 도움말을 검사한다.

    Args:
        schema: JSON Schema 문서(객체). ``$defs``를 포함해도 된다.
        path: 보고 위치 접두사(예: ``node-types/agent/config_schema``).
        roots: 주면 ``$defs`` 중 이 이름들과 그 ``$ref`` 닫힘만 본다(묶음 문서 일부만 검사할 때).
            None이면 문서 전체(루트 + ``$defs``)를 본다.
        objects: True면 객체 스키마 자체의 설명(모델 docstring)도 문구 규칙으로 본다.

    Returns:
        규칙 위반 목록(없으면 빈 목록). 심각도(오류·경고)는 호출자가 정한다.
    """
    issues: list[HelpIssue] = []
    raw_defs = schema.get("$defs", schema.get("definitions", {}))
    all_defs: Mapping[str, Any] = raw_defs if isinstance(raw_defs, Mapping) else {}
    if roots is None:
        _walk(schema, path, issues, into_defs=True, objects=objects, defs=all_defs)
        return issues
    defs = schema.get("$defs", {})
    if not isinstance(defs, Mapping):
        return issues
    for name in _closure(defs, roots):
        _walk(
            defs[name], f"{path}/$defs/{name}", issues, into_defs=False, objects=objects, defs=defs
        )
    return issues


def contract_form_roots(models: Iterable[type[BaseModel]] | None = None) -> tuple[str, ...]:
    """계약 모델 중 사용자가 폼으로 고치는 문서(정의 데이터 모델)의 스키마 이름.

    기준은 이름 목록이 아니라 베이스 클래스다: ``DefinitionModel``을 상속한 모델(YAML로
    저장되는 사용자 데이터)이 폼의 뿌리다. 그 모델이 참조하는 모델은
    ``lint_schema_help(roots=...)``가 따라간다.
    """
    from .schema import CONTRACT_MODELS

    picked = CONTRACT_MODELS if models is None else tuple(models)
    return tuple(m.__name__ for m in picked if issubclass(m, DefinitionModel))


def lint_contract_help() -> list[HelpIssue]:
    """계약 묶음 스키마(``build_schema()``)의 폼 모델을 검사한다(모델 설명 포함)."""
    from .schema import build_schema

    return lint_schema_help(build_schema(), roots=contract_form_roots(), objects=True)

"""묶음 검사와 JSON Schema 화면 문구 뽑기(design §I18N.10 S1~S3의 순수 함수 부분).

검사는 문제 목록만 돌려준다. 무엇을 실패로 볼지(묶어 둔 ``ko``·``en``은 완전해야 하고 사용자 언어는
일부만 있어도 된다 — I-9)는 호출자가 정한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agent_console_i18n._lookup import placeholders
from agent_console_i18n._model import CODES, NS, SECTIONS, TEXT, Catalog, CatalogIssue, Section

__all__ = [
    "DEFAULT_SCHEMA_TEXT_KEYS",
    "PLURAL_SUFFIXES",
    "SchemaTextKeys",
    "check_codes",
    "check_details",
    "check_texts",
    "compare_catalogs",
    "flatten_ns",
    "is_complete",
    "schema_texts",
]

PLURAL_SUFFIXES: Final = ("_zero", "_one", "_two", "_few", "_many", "_other")
"""i18next 복수형 접미사(CLDR 범주). 언어마다 쓰는 범주가 달라 키 비교 전에 뗀다."""


def flatten_ns(ns: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """``ns`` 구역을 ``<네임스페이스>.<경로>`` → 문자열로 편다.

    >>> flatten_ns({"common": {"save": "Save", "menu": {"open": "Open"}}})
    {'common.save': 'Save', 'common.menu.open': 'Open'}
    """
    out: dict[str, str] = {}

    def walk(prefix: str, tree: Mapping[str, Any]) -> None:
        for key, value in tree.items():
            dotted = f"{prefix}.{key}"
            if isinstance(value, Mapping):
                walk(dotted, value)
            else:
                out[dotted] = str(value)

    for name, tree in ns.items():
        walk(name, tree)
    return out


def _entries(
    catalog: Catalog, section: Section, plural_suffixes: Sequence[str]
) -> dict[str, list[str]]:
    """비교 키 → 값 목록(복수형 형태를 한 키로 묶는다)."""
    flat = flatten_ns(catalog.ns) if section == NS else dict(catalog.section(section))
    grouped: dict[str, list[str]] = {}
    for key, value in flat.items():
        base = key
        if section == NS:
            for suffix in plural_suffixes:
                if key.endswith(suffix) and len(key) > len(suffix):
                    base = key[: -len(suffix)]
                    break
        grouped.setdefault(base, []).append(value)
    return grouped


def compare_catalogs(
    base: Catalog,
    other: Catalog,
    *,
    sections: Iterable[Section] = SECTIONS,
    plural_suffixes: Sequence[str] = PLURAL_SUFFIXES,
) -> list[CatalogIssue]:
    """기준 묶음과 다른 언어 묶음의 키·자리표시자를 맞춘다(W2·S3 모양).

    - ``i18n.missing_key``: 기준에 있는데 ``other``에 없음
    - ``i18n.untranslated``: 키는 있는데 값이 빔(뽑기 명령이 더한 빈 값)
    - ``i18n.extra_key``: ``other``에만 있음
    - ``i18n.placeholder_mismatch``: 자리표시자 이름 집합이 다름(``details.expected``·``actual``)

    ``ns``의 복수형 키(``items_one``·``items_other``)는 접미사를 떼고 한 키로 보며
    자리표시자는 형태들의 합집합을 비교한다. 이슈의 ``language``는 ``other`` 언어다.
    """
    issues: list[CatalogIssue] = []
    lang = other.language
    for section in sections:
        left = _entries(base, section, plural_suffixes)
        right = _entries(other, section, plural_suffixes)
        for key, values in left.items():
            if key not in right:
                issues.append(
                    CatalogIssue(
                        code="i18n.missing_key",
                        message=f"'{key}' is in {base.language} but not in {lang}",
                        language=lang,
                        section=section,
                        key=key,
                    )
                )
                continue
            theirs = right[key]
            if all(v == "" for v in theirs):
                issues.append(
                    CatalogIssue(
                        code="i18n.untranslated",
                        message=f"'{key}' has an empty value in {lang}",
                        language=lang,
                        section=section,
                        key=key,
                    )
                )
                continue
            expected = frozenset().union(*(placeholders(v) for v in values))
            actual = frozenset().union(*(placeholders(v) for v in theirs if v != ""))
            if expected != actual:
                issues.append(
                    CatalogIssue(
                        code="i18n.placeholder_mismatch",
                        message=(
                            f"'{key}' placeholders differ: {base.language} {sorted(expected)}, "
                            f"{lang} {sorted(actual)}"
                        ),
                        language=lang,
                        section=section,
                        key=key,
                        details={"expected": sorted(expected), "actual": sorted(actual)},
                    )
                )
        for key in right:
            if key not in left:
                issues.append(
                    CatalogIssue(
                        code="i18n.extra_key",
                        message=f"'{key}' is in {lang} but not in {base.language}",
                        language=lang,
                        section=section,
                        key=key,
                    )
                )
    return issues


def is_complete(base: Catalog, other: Catalog, *, sections: Iterable[Section] = SECTIONS) -> bool:
    """``other``가 기준의 키를 빈 값 없이 다 가졌는지(``LanguageInfo.complete``용)."""
    return not any(
        issue.code in {"i18n.missing_key", "i18n.untranslated"}
        for issue in compare_catalogs(base, other, sections=sections)
    )


def check_codes(catalog: Catalog, codes: Iterable[str]) -> list[CatalogIssue]:
    """코드 목록 중 묶음 ``codes``에 없거나 빈 것(``i18n.missing_code``, S2)."""
    return [
        CatalogIssue(
            code="i18n.missing_code",
            message=f"code '{code}' has no message in {catalog.language}",
            language=catalog.language,
            section=CODES,
            key=code,
        )
        for code in dict.fromkeys(codes)
        if not catalog.codes.get(code)
    ]


def check_texts(catalog: Catalog, texts: Iterable[str]) -> list[CatalogIssue]:
    """원문 목록 중 묶음 ``text``에 없거나 빈 것(``i18n.missing_text``, S1)."""
    return [
        CatalogIssue(
            code="i18n.missing_text",
            message=f"text has no translation in {catalog.language}",
            language=catalog.language,
            section=TEXT,
            key=text,
        )
        for text in dict.fromkeys(texts)
        if not catalog.text.get(text)
    ]


def check_details(
    catalog: Catalog, examples: Mapping[str, Iterable[str] | Mapping[str, Any]]
) -> list[CatalogIssue]:
    """코드 틀의 자리표시자가 그 코드의 ``details`` 키 안에 있는지 본다.

    없는 이름은 ``i18n.unknown_placeholder``(S3).

    Args:
        catalog: 검사할 묶음.
        examples: 코드 → 예시 ``details``(dict) 또는 키 이름 목록. 여기 없는 코드는 보지 않는다.
    """
    issues: list[CatalogIssue] = []
    for code, details in examples.items():
        template = catalog.codes.get(code)
        if not template:
            continue
        known = set(details)
        unknown = sorted(placeholders(template) - known)
        if unknown:
            issues.append(
                CatalogIssue(
                    code="i18n.unknown_placeholder",
                    message=(
                        f"code '{code}' in {catalog.language} uses {unknown} "
                        f"not in details {sorted(known)}"
                    ),
                    language=catalog.language,
                    section=CODES,
                    key=code,
                    details={"unknown": unknown, "details": sorted(known)},
                )
            )
    return issues


@dataclass(frozen=True, slots=True)
class SchemaTextKeys:
    """JSON Schema에서 화면 문구로 볼 키(데이터 — 스키마 확장 키가 늘면 인자로 바꾼다).

    - ``keywords``: 스키마 객체의 문자열 키워드(``title``·``description``)
    - ``ext``: 확장 객체 키(``x-ui``)
    - ``ext_strings``: 확장 객체 안 문자열 값 키
    - ``ext_maps``: 확장 객체 안 "값 → 문구" 사전 키(선택지 라벨)
    - ``ext_lists``: 확장 객체 안 객체 목록 키와 그 안의 문구 키
    - ``data_keywords``: 안으로 들어가지 않는 데이터 키워드(기본값·예시·상수)
    - ``name_maps``: 값이 "이름 → 스키마" 사전인 키워드(그 안의 키는 이름이라 키워드로 보지 않는다)
    """

    keywords: tuple[str, ...] = ("title", "description")
    ext: str = "x-ui"
    ext_strings: tuple[str, ...] = ("when", "group_title", "unit")
    ext_maps: tuple[str, ...] = ("enum_labels",)
    ext_lists: tuple[tuple[str, str], ...] = (("variables", "description"),)
    data_keywords: tuple[str, ...] = ("default", "examples", "example", "const", "enum")
    name_maps: tuple[str, ...] = (
        "properties",
        "patternProperties",
        "$defs",
        "definitions",
        "dependentSchemas",
        "schemas",
    )


DEFAULT_SCHEMA_TEXT_KEYS: Final = SchemaTextKeys()


def schema_texts(schema: Any, *, keys: SchemaTextKeys = DEFAULT_SCHEMA_TEXT_KEYS) -> list[str]:
    """JSON Schema(OpenAPI 조각 포함)에서 화면에 보일 문구를 처음 나온 순서로 모은다(중복 없음).

    속성 이름(``properties`` 키)은 문구가 아니다. 기본값·예시 값 안은 보지 않는다.

    >>> schema_texts({"title": "설정", "properties": {"default": {"type": "string",
    ...     "description": "이름", "default": {"title": "무시"},
    ...     "x-ui": {"when": "바꿀 때", "enum_labels": {"a": "가"}}}}})
    ['설정', '이름', '바꿀 때', '가']
    """
    seen: dict[str, None] = {}

    def add(value: object) -> None:
        if isinstance(value, str) and value.strip():
            seen.setdefault(value, None)

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, Mapping):
            return
        for key, value in node.items():
            if key in keys.keywords and isinstance(value, str):
                add(value)
            elif key == keys.ext and isinstance(value, Mapping):
                _ext(value)
            elif key in keys.data_keywords:
                continue
            elif key in keys.name_maps and isinstance(value, Mapping):
                for child in value.values():
                    walk(child)
            else:
                walk(value)

    def _ext(ext: Mapping[str, Any]) -> None:
        for name in keys.ext_strings:
            add(ext.get(name))
        for name in keys.ext_maps:
            labels = ext.get(name)
            if isinstance(labels, Mapping):
                for label in labels.values():
                    add(label)
        for name, field in keys.ext_lists:
            items = ext.get(name)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, Mapping):
                        add(item.get(field))

    walk(schema)
    return list(seen)

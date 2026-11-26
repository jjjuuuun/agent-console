"""문구 묶음 데이터 모델과 JSON 읽기(design §I18N.3 Python 형식).

파일 하나 = (출처, 언어). 최상위는 객체이고 세 구역을 가진다.

- ``text``: 원문 문자열 → 번역(서버 고정 문구, 원문 키 조회).
- ``codes``: 오류·이슈 코드 → 틀(``{name}`` 자리표시자, 값은 ``details``에서).
- ``ns``: 웹 네임스페이스 → 중첩 객체(잎 = 문자열). 웹 문구를 덮거나 새 언어의 웹 문구를 줄 때.

빈 문자열 값은 "아직 번역 안 함"이다(조회·병합에서 없는 것으로 본다).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

__all__ = [
    "CODES",
    "NS",
    "SECTIONS",
    "TEXT",
    "Catalog",
    "CatalogIssue",
    "Origin",
    "Section",
    "is_language_tag",
    "normalize_language",
    "read_catalog",
]

TEXT: Final = "text"
CODES: Final = "codes"
NS: Final = "ns"
SECTIONS: Final = (TEXT, CODES, NS)
"""묶음 파일의 구역 이름(순서 = 문서 순서)."""

type Section = Literal["text", "codes", "ns"]
type Origin = Literal["package", "folder", "inline"]
"""묶음 출처 종류: entry point 패키지 / 사용자 폴더 / 코드에서 직접 만든 것."""

_TAG = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


@dataclass(frozen=True, slots=True)
class CatalogIssue:
    """불러오기·검사에서 나온 문제 하나. 예외 대신 모아 돌려준다.

    ``code``는 ``i18n.*`` 문자열, ``message``는 터미널용 영어 문장이다. 나머지는 있는 것만 채운다.
    """

    code: str
    message: str
    source: str | None = None
    language: str | None = None
    section: str | None = None
    key: str | None = None
    path: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Catalog:
    """언어 하나의 문구 묶음(파일 하나, 또는 병합 결과).

    ``ns`` 값은 중첩 dict(잎 = 문자열)다. 병합 결과면 ``sources``에 기여한 출처 이름이
    순서대로 들어 있다.
    """

    language: str
    text: Mapping[str, str] = field(default_factory=dict)
    codes: Mapping[str, str] = field(default_factory=dict)
    ns: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    source: str = ""
    origin: Origin = "inline"
    sources: tuple[str, ...] = ()

    def section(self, name: Section) -> Mapping[str, Any]:
        """구역 이름으로 값을 꺼낸다."""
        if name == TEXT:
            return self.text
        if name == CODES:
            return self.codes
        return self.ns

    def to_dict(self) -> dict[str, Any]:
        """파일 형식 그대로의 dict(``{"text":…, "codes":…, "ns":…}``)."""
        return {TEXT: dict(self.text), CODES: dict(self.codes), NS: _plain(self.ns)}


def is_language_tag(tag: str) -> bool:
    """BCP 47 모양(``en``, ``en-US``, ``zh-Hant-TW``)인지. 등록된 언어인지는 보지 않는다."""
    return bool(_TAG.match(tag))


def normalize_language(tag: str) -> str:
    """언어 코드를 한 표기로 맞춘다.

    주 언어는 소문자, 4글자 문자 체계는 첫 글자 대문자, 2글자 지역은 대문자다.

    ``_``는 ``-``로 바꾼다. 모양이 틀리면 ``ValueError``.

    >>> normalize_language("EN_us"), normalize_language("zh-hant-tw")
    ('en-US', 'zh-Hant-TW')
    """
    cleaned = tag.strip().replace("_", "-")
    if not is_language_tag(cleaned):
        raise ValueError(f"not a language tag: {tag!r}")
    parts = cleaned.split("-")
    out = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            out.append(part.title())
        elif len(part) == 2 and part.isalpha():
            out.append(part.upper())
        else:
            out.append(part.lower())
    return "-".join(out)


def read_catalog(
    data: object,
    *,
    language: str,
    source: str = "",
    origin: Origin = "inline",
    path: str | None = None,
) -> tuple[Catalog | None, list[CatalogIssue]]:
    """Turn a JSON value (already parsed) into a catalog.

    잘못된 항목은 건너뛰고 문제로 돌려준다(나머지는 쓴다). 최상위가 객체가 아니거나
    언어 코드가 틀리면 묶음 없이(``None``) 문제만 돌려준다. 모르는 최상위 키는 무시하고
    ``i18n.catalog_unknown_section``으로 남긴다.

    Args:
        data: ``json.loads`` 결과.
        language: 언어 코드(보통 파일 이름).
        source: 출처 이름(entry point 이름·폴더 경로).
        origin: 출처 종류.
        path: 문제에 적을 파일 위치.

    Returns:
        (묶음 또는 None, 문제 목록).
    """
    issues: list[CatalogIssue] = []

    def issue(code: str, message: str, **extra: Any) -> None:
        issues.append(
            CatalogIssue(
                code=code,
                message=message,
                source=source or None,
                language=language,
                path=path,
                **extra,
            )
        )

    try:
        lang = normalize_language(language)
    except ValueError:
        issue("i18n.language_invalid", f"'{language}' is not a BCP 47 language tag")
        return None, issues
    if not isinstance(data, Mapping):
        issue("i18n.catalog_invalid", "catalog file must be a JSON object")
        return None, issues
    for key in data:
        if key not in SECTIONS:
            issue(
                "i18n.catalog_unknown_section",
                f"unknown section '{key}' ignored (known: {', '.join(SECTIONS)})",
                section=str(key),
            )
    flat: dict[str, dict[str, str]] = {}
    for name in (TEXT, CODES):
        flat[name] = _read_flat(data.get(name), name, issue)
    ns = _read_ns(data.get(NS), issue)
    catalog = Catalog(
        language=lang,
        text=flat[TEXT],
        codes=flat[CODES],
        ns=ns,
        source=source,
        origin=origin,
        sources=(source,) if source else (),
    )
    return catalog, issues


def _read_flat(value: object, section: str, issue: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        issue("i18n.catalog_invalid", f"section '{section}' must be an object", section=section)
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(item, str):
            out[str(key)] = item
        else:
            issue(
                "i18n.entry_invalid",
                f"value of '{key}' in '{section}' must be a string",
                section=section,
                key=str(key),
            )
    return out


def _read_ns(value: object, issue: Any) -> dict[str, Mapping[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        issue("i18n.catalog_invalid", "section 'ns' must be an object", section=NS)
        return {}
    out: dict[str, Mapping[str, Any]] = {}
    for name, body in value.items():
        if not isinstance(body, Mapping):
            issue(
                "i18n.entry_invalid",
                f"namespace '{name}' must be an object",
                section=NS,
                key=str(name),
            )
            continue
        out[str(name)] = _read_tree(body, str(name), issue)
    return out


def _read_tree(body: Mapping[str, Any], prefix: str, issue: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in body.items():
        dotted = f"{prefix}.{key}"
        if isinstance(item, str):
            out[str(key)] = item
        elif isinstance(item, Mapping):
            out[str(key)] = _read_tree(item, dotted, issue)
        else:
            issue(
                "i18n.entry_invalid",
                f"value of '{dotted}' must be a string or an object",
                section=NS,
                key=dotted,
            )
    return out


def _plain(value: Mapping[str, Any]) -> dict[str, Any]:
    return {k: _plain(v) if isinstance(v, Mapping) else v for k, v in value.items()}

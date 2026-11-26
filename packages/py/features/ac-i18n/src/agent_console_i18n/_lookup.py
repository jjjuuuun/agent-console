"""병합·언어 맞춤·조회(design §I18N.3 병합 순서, I-5 원문 키, I-6 코드 키, I-9 대체 언어).

병합은 뒤 출처가 이긴다. 호출자가 순서를 정한다(보통 패키지 묶음 이름 순 → 사용자 폴더 목록 순).
빈 문자열 값은 앞 출처 값을 지우지 않는다(아직 번역 안 함).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from agent_console_i18n._loading import CatalogLoad
from agent_console_i18n._model import Catalog, CatalogIssue, normalize_language

__all__ = [
    "CatalogSet",
    "Translator",
    "match_language",
    "merge_catalogs",
    "placeholders",
    "render",
]

_PLACEHOLDER: Final = re.compile(r"\{\s*([A-Za-z_][\w.]*)\s*(?:,\s*([\w.-]+)\s*)?\}")
"""``{name}`` 또는 ``{name, 서식}``. 서식 이름은 웹 서식 등록부가 쓴다(여기서는 값만 넣는다)."""


def placeholders(template: str) -> frozenset[str]:
    """틀 안 자리표시자 이름.

    >>> sorted(placeholders("{count} items in {label, particle.object}"))
    ['count', 'label']
    """
    return frozenset(m.group(1) for m in _PLACEHOLDER.finditer(template))


def render(template: str, values: Mapping[str, Any]) -> tuple[str, frozenset[str]]:
    """자리표시자를 값으로 채운다. 서식 이름은 무시하고 ``str(값)``을 넣는다.

    Returns:
        (채운 문자열, 값이 없어 그대로 둔 이름).

    >>> render("{name} failed ({code})", {"name": "pl"})
    ('pl failed ({code})', frozenset({'code'}))
    """
    missing: set[str] = set()

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in values:
            return str(values[name])
        missing.add(name)
        return match.group(0)

    return _PLACEHOLDER.sub(fill, template), frozenset(missing)


def match_language(requested: str, available: Iterable[str]) -> str | None:
    """요청 언어에 맞는 쓸 수 있는 언어(RFC 4647 lookup: 정확히 같음 → 뒤 하위 태그를 하나씩 뗌).

    대소문자·``_``는 가리지 않는다. 맞는 것이 없거나 요청이 언어 코드 모양이 아니면 None.

    >>> match_language("en-US", ["ko", "en"]), match_language("fr", ["ko"])
    ('en', None)
    """
    try:
        wanted = normalize_language(requested)
    except ValueError:
        return None
    pool: dict[str, str] = {}
    for item in available:
        try:
            pool.setdefault(normalize_language(item).lower(), item)
        except ValueError:
            continue
    parts = wanted.split("-")
    while parts:
        hit = pool.get("-".join(parts).lower())
        if hit is not None:
            return hit
        parts.pop()
    return None


def merge_catalogs(language: str, catalogs: Sequence[Catalog]) -> Catalog:
    """같은 언어의 묶음들을 순서대로 합친다.

    뒤가 이기고, ``ns``는 잎 단위로 깊게 합치고, 빈 값은 건너뛴다.
    """
    text: dict[str, str] = {}
    codes: dict[str, str] = {}
    ns: dict[str, dict[str, Any]] = {}
    sources: list[str] = []
    for catalog in catalogs:
        _update_flat(text, catalog.text)
        _update_flat(codes, catalog.codes)
        for name, tree in catalog.ns.items():
            _update_tree(ns.setdefault(name, {}), tree)
        for source in catalog.sources or ((catalog.source,) if catalog.source else ()):
            if source not in sources:
                sources.append(source)
    return Catalog(
        language=language,
        text=text,
        codes=codes,
        ns=ns,
        source="",
        origin="inline",
        sources=tuple(sources),
    )


def _update_flat(target: dict[str, str], values: Mapping[str, str]) -> None:
    for key, value in values.items():
        if value != "":
            target[key] = value


def _update_tree(target: dict[str, Any], values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        if isinstance(value, Mapping):
            current = target.get(key)
            if not isinstance(current, dict):
                current = {}
                target[key] = current
            _update_tree(current, value)
        elif value != "":
            target[key] = value


class Translator:
    """고른 언어 → 대체 언어 → 원문 순으로 찾는 조회기(I-9). ``CatalogSet.translator``가 만든다."""

    def __init__(self, chain: Sequence[Catalog]) -> None:
        """Args: chain — 찾을 순서대로 놓은 병합 묶음."""
        self._chain = tuple(chain)

    @property
    def languages(self) -> tuple[str, ...]:
        """찾는 언어 순서."""
        return tuple(c.language for c in self._chain)

    def text(self, original: str) -> str:
        """원문 키 조회. 어디에도 없으면 원문 그대로(I-5)."""
        for catalog in self._chain:
            value = catalog.text.get(original)
            if value:
                return value
        return original

    def template(self, code: str) -> str | None:
        """코드 틀(채우기 전). 없으면 None."""
        for catalog in self._chain:
            value = catalog.codes.get(code)
            if value:
                return value
        return None

    def code(
        self, code: str, details: Mapping[str, Any] | None = None, *, default: str | None = None
    ) -> str | None:
        """코드 키 조회 + ``details``로 채우기(I-6).

        틀이 없거나 ``details``에 자리표시자 값이 빠졌으면 ``default``(보통 서버 원문)를 돌려준다.
        ``default``가 None이면 빠진 자리표시자를 그대로 둔 문자열(틀이 없으면 None).
        """
        template = self.template(code)
        if template is None:
            return default
        rendered, missing = render(template, details or {})
        if missing and default is not None:
            return default
        return rendered

    def namespace(self, name: str) -> dict[str, Any]:
        """웹 네임스페이스 문구(대체 언어 위에 고른 언어를 덮은 것)."""
        out: dict[str, Any] = {}
        for catalog in reversed(self._chain):
            _update_tree(out, catalog.ns.get(name, {}))
        return out


class CatalogSet:
    """Catalogs collected per language. Insertion order is merge order (later wins).

    >>> from agent_console_i18n import Catalog
    >>> s = CatalogSet([Catalog("en", text={"저장": "Save"}, source="pkg"),
    ...                 Catalog("en", text={"저장": "Store"}, source="mine")])
    >>> s.translator("en-GB").text("저장"), s.sources("en")
    ('Store', ('pkg', 'mine'))
    """

    def __init__(
        self, catalogs: Iterable[Catalog] = (), *, issues: Iterable[CatalogIssue] = ()
    ) -> None:
        """Args: catalogs — 병합 순서대로 놓은 묶음, issues — 불러오기 문제(``issues``로 보인다)."""
        self._by_language: dict[str, list[Catalog]] = {}
        self._issues: list[CatalogIssue] = list(issues)
        self._merged: dict[str, Catalog] = {}
        for catalog in catalogs:
            self.add(catalog)

    @classmethod
    def from_load(cls, *loads: CatalogLoad) -> CatalogSet:
        """``package_catalogs``·``folder_catalogs`` 결과를 순서대로 모은다."""
        out = cls()
        for load in loads:
            for catalog in load.catalogs:
                out.add(catalog)
            out._issues.extend(load.issues)
        return out

    def add(self, catalog: Catalog) -> None:
        """묶음 하나를 맨 뒤(가장 우선)에 더한다."""
        self._by_language.setdefault(catalog.language, []).append(catalog)
        self._merged.pop(catalog.language, None)

    @property
    def issues(self) -> tuple[CatalogIssue, ...]:
        """불러오기에서 건너뛴 문제."""
        return tuple(self._issues)

    def languages(self) -> tuple[str, ...]:
        """묶음이 하나라도 있는 언어(이름 순)."""
        return tuple(sorted(self._by_language))

    def sources(self, language: str) -> tuple[str, ...]:
        """그 언어에 기여한 출처 이름(병합 순서)."""
        merged = self.catalog(language)
        return () if merged is None else merged.sources

    def parts(self, language: str) -> tuple[Catalog, ...]:
        """그 언어의 병합 전 묶음들(병합 순서)."""
        return tuple(self._by_language.get(language, ()))

    def match(self, requested: str) -> str | None:
        """요청 언어에 맞는 언어(``match_language``)."""
        return match_language(requested, self._by_language)

    def catalog(self, language: str) -> Catalog | None:
        """병합한 묶음. 요청 언어를 맞춰서 찾고(``en-US`` → ``en``), 없으면 None."""
        lang = self.match(language)
        if lang is None:
            return None
        merged = self._merged.get(lang)
        if merged is None:
            merged = merge_catalogs(lang, self._by_language[lang])
            self._merged[lang] = merged
        return merged

    def translator(self, language: str, *, fallback: str | None = None) -> Translator:
        """고른 언어 → 대체 언어 사슬 조회기. 없는 언어는 사슬에서 빠진다(빈 사슬 = 늘 원문)."""
        chain: list[Catalog] = []
        for lang in (language, fallback):
            if lang is None:
                continue
            merged = self.catalog(lang)
            if merged is not None and all(c.language != merged.language for c in chain):
                chain.append(merged)
        return Translator(chain)

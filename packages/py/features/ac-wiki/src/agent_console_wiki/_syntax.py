"""위키 문법 데이터(X47): 패키지 기본 읽기, 층 병합(값마다 출처).

병합 규칙(design §7R.1.3 — `ac-sdd` `merge_syntax`와 같은 규칙):
    - 층 순서는 패키지 기본 → 사용자 설정 `wiki.syntax` → 위키 규칙 `syntax`(위키의 규칙 순서). 뒤
      층이 이긴다.
    - None은 "상속"(아래 층을 따름), 빈 목록은 "이 층에서는 없음"으로 아래 층을 덮는다.
    - 첫 단계 키 중 객체 값(`front_matter`·`lint`, 모르는 객체 키도)은 그 안의 키 단위로 합치고, 그
      아래 값(목록·`roles` 같은 매핑)과 객체가 아닌 첫 단계 값(`links`·`title_sources` 등)은 통째로
      바꾼다. 모르는 키는 보존한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import cache
from importlib import resources
from typing import Any

from ruamel.yaml import YAML

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    EffectiveWikiSyntax,
    KnownWikiSyntaxSources,
    WikiIssue,
    WikiSettings,
    WikiSyntax,
)

__all__ = [
    "DEFAULT_SYNTAX_RESOURCE",
    "SyntaxLayer",
    "effective_syntax",
    "load_default_syntax",
    "merge_syntax",
    "rules_source",
]

DEFAULT_SYNTAX_RESOURCE = "data/default_syntax.yaml"
"""패키지 기본 문법 데이터의 패키지 안 위치."""

type SyntaxLayer = tuple[str, WikiSyntax | Mapping[str, Any] | None]
"""병합 층 하나: (출처 이름, 문법). 출처 이름은 열린 문자열(`KnownWikiSyntaxSources`)."""


@cache
def _default_document() -> Mapping[str, Any]:
    text = (resources.files("agent_console_wiki") / DEFAULT_SYNTAX_RESOURCE).read_text(
        encoding="utf-8"
    )
    data = YAML(typ="safe").load(text)
    return data if isinstance(data, dict) else {}


def load_default_syntax() -> WikiSyntax:
    """패키지 기본 위키 문법(`data/default_syntax.yaml`)을 읽는다.

    Returns:
        새 `WikiSyntax`(고쳐도 다음 호출에 영향이 없다).

    Raises:
        pydantic.ValidationError: 패키지 데이터가 계약 모양이 아닐 때(설치가 깨진 경우).
    """
    return WikiSyntax.model_validate(_default_document())


def rules_source(rule_id: str) -> str:
    """위키 규칙 층의 출처 이름(`rules:<규칙 id>`)."""
    return f"{KnownWikiSyntaxSources.RULES_PREFIX}{rule_id}"


def _as_document(value: WikiSyntax | Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, WikiSyntax):
        dumped: dict[str, Any] = value.model_dump(mode="json", by_alias=True, exclude_none=True)
        return dumped
    # 매핑은 계약 모양으로 한 번 검사한 뒤 같은 방식으로 직렬화한다(None 제거 규칙을 같게).
    return _as_document(WikiSyntax.model_validate(dict(value)))


def merge_syntax(*layers: SyntaxLayer) -> EffectiveWikiSyntax:
    """문법 층을 순서대로 합쳐 유효 문법과 값마다 출처를 만든다.

    Args:
        layers: (출처 이름, 문법) 목록. 앞이 아래 층, 뒤가 위 층이다. 문법이 None이면 그 층은
            아무것도 바꾸지 않는다. 기본 문법을 끄려면 그 층을 빼면 된다.

    Returns:
        `EffectiveWikiSyntax` — `sources` 키는 문법 문서 기준 위치(`/links`·`/front_matter/roles`),
        `empty`는 링크 규칙이 하나도 없는지, `issues`는 비었을 때 `wiki.syntax_missing`(정보). 패턴
        컴파일 이슈는 `compile_syntax`가 더한다.

    Raises:
        pydantic.ValidationError: 매핑으로 준 층이 계약 모양이 아닐 때.
    """
    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for source, value in layers:
        for section, content in _as_document(value).items():
            if isinstance(content, dict):
                target = merged.get(section)
                if not isinstance(target, dict):
                    target = merged[section] = {}
                    # 객체가 아닌 값을 객체로 덮으면 옛 출처 표시를 지운다.
                    sources.pop(f"/{section}", None)
                for key, item in content.items():
                    target[key] = item
                    sources[f"/{section}/{key}"] = source
            else:
                merged[section] = content
                for key in [k for k in sources if k.startswith(f"/{section}/")]:
                    del sources[key]
                sources[f"/{section}"] = source
    syntax = WikiSyntax.model_validate(merged)
    empty = not syntax.links
    issues: list[WikiIssue] = []
    if empty:
        issues.append(
            WikiIssue(
                severity="info",
                code=KnownIssueCodes.WIKI_SYNTAX_MISSING,
                message="링크 규칙이 없어 링크·백링크·그래프를 만들지 않습니다.",
                path="/links",
            )
        )
    return EffectiveWikiSyntax(syntax=syntax, sources=sources, empty=empty, issues=issues)


def effective_syntax(
    settings: WikiSettings | None = None,
    rules: Sequence[tuple[str, WikiSyntax | Mapping[str, Any] | None]] = (),
    *,
    default: WikiSyntax | None = None,
) -> EffectiveWikiSyntax:
    """사용자 설정·위키 규칙·패키지 기본에서 유효 문법을 만든다(설계의 세 층 그대로).

    Args:
        settings: 사용자 설정 섹션 `wiki`. None이면 기본값(기본 문법 켜짐, 설정 문법 없음).
        rules: (위키 규칙 id, 그 규칙의 `syntax`) 목록 — 위키의 규칙 순서대로. 출처는 `rules:<id>`.
        default: 패키지 기본 대신 쓸 문법(테스트·다른 기본 데이터용). None이면 패키지 기본을 읽는다.
            `settings.include_default_syntax`가 거짓이면 쓰지 않는다.

    Returns:
        `merge_syntax` 결과.
    """
    settings = settings or WikiSettings()
    layers: list[SyntaxLayer] = []
    if settings.include_default_syntax:
        layers.append((KnownWikiSyntaxSources.DEFAULT, default or load_default_syntax()))
    layers.append((KnownWikiSyntaxSources.SETTINGS, settings.syntax))
    layers.extend((rules_source(rule_id), syntax) for rule_id, syntax in rules)
    return merge_syntax(*layers)

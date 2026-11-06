"""작업 문법 데이터: 패키지 기본 읽기, 층 병합(값마다 출처), 풀린 상태 라벨.

병합 규칙(design §6R.1.3, 계약 0.13.0):
    - 층 순서는 패키지 기본 → 사용자 설정 `sdd.syntax` → 스펙 `rules.syntax` → 스펙
      `rules.task_statuses`(작업 상태만). 뒤 층이 이긴다.
    - None은 "상속"(아래 층을 따름)이다. 빈 목록은 "이 층에서는 없음"으로 아래 층을 덮는다.
    - 문법 문서의 첫 단계(`task`·`requirement`·`stage`, 모르는 단계 키도)는 키 단위로 합치고,
      그 아래 값(목록·`roles` 같은 매핑 포함)은 통째로 바꾼다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from importlib import resources
from typing import Any

from ruamel.yaml import YAML

from agent_console_contracts.sdd import (
    DocumentStateInfo,
    DocumentStateSpec,
    EffectiveSyntax,
    KnownSyntaxSources,
    SddSettings,
    SpecRules,
    SpecSyntax,
    TaskStatusInfo,
    TaskStatusSpec,
)

__all__ = [
    "DEFAULT_SYNTAX_RESOURCE",
    "SyntaxLayer",
    "document_state_infos",
    "effective_syntax",
    "load_default_syntax",
    "merge_syntax",
    "status_infos",
]

DEFAULT_SYNTAX_RESOURCE = "data/default_syntax.yaml"
"""패키지 기본 문법 데이터의 패키지 안 위치."""

type SyntaxLayer = tuple[str, SpecSyntax | Mapping[str, Any] | None]
"""병합 층 하나: (출처 이름, 문법). 출처 이름은 열린 문자열(알려진 값 `KnownSyntaxSources`)."""


def _read_default_text() -> str:
    return (resources.files("agent_console_sdd") / DEFAULT_SYNTAX_RESOURCE).read_text(
        encoding="utf-8"
    )


@cache
def _default_document() -> Mapping[str, Any]:
    data = YAML(typ="safe").load(_read_default_text())
    return data if isinstance(data, dict) else {}


def load_default_syntax() -> SpecSyntax:
    """패키지 기본 작업 문법(`data/default_syntax.yaml`)을 읽는다.

    Returns:
        새 `SpecSyntax`(호출자가 고쳐도 다음 호출에 영향이 없다).

    Raises:
        pydantic.ValidationError: 패키지 데이터가 계약 모양이 아닐 때(설치가 깨진 경우).
    """
    return SpecSyntax.model_validate(_default_document())


def _as_document(value: SpecSyntax | Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, SpecSyntax):
        dumped = value.model_dump(mode="json", by_alias=True, exclude_none=True)
        return dumped
    # 매핑은 계약 모양으로 한 번 검사한 뒤 같은 방식으로 직렬화한다(None 제거 규칙을 같게).
    return _as_document(SpecSyntax.model_validate(dict(value)))


def merge_syntax(
    *layers: SyntaxLayer,
    task_statuses: tuple[str, Sequence[TaskStatusSpec] | None] | None = None,
) -> EffectiveSyntax:
    """문법 층을 순서대로 합쳐 유효 문법과 값마다 출처를 만든다.

    Args:
        layers: (출처 이름, 문법) 목록. 앞이 아래 층, 뒤가 위 층이다. 문법이 None이면 그 층은
            아무것도 바꾸지 않는다. 기본 문법을 끄려면 그 층을 빼면 된다.
        task_statuses: (출처 이름, 작업 상태 목록) — 스펙 규칙 `task_statuses`처럼 문법 밖에서
            작업 상태만 덮는 층. 목록이 None이면 덮지 않는다.

    Returns:
        `EffectiveSyntax` — `sources` 키는 문법 문서 기준 위치(`/task/id_pattern`), `statuses`는
        라벨을 푼 작업 상태, `empty`는 작업 줄을 읽을 수 없는 상태(작업 단계·작업 줄 모양·작업
        상태 중 하나라도 없음)인지.

    Raises:
        pydantic.ValidationError: 매핑으로 준 층이 계약 모양이 아닐 때.
    """
    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for source, value in layers:
        for section, content in _as_document(value).items():
            if isinstance(content, dict):
                target = merged.setdefault(section, {})
                if not isinstance(target, dict):
                    target = merged[section] = {}
                for key, item in content.items():
                    target[key] = item
                    sources[f"/{section}/{key}"] = source
            else:
                merged[section] = content
                sources[f"/{section}"] = source
    if task_statuses is not None and task_statuses[1] is not None:
        source, statuses = task_statuses
        task = merged.setdefault("task", {})
        task["statuses"] = [
            s.model_dump(mode="json", by_alias=True, exclude_none=True) for s in statuses or ()
        ]
        sources["/task/statuses"] = source
    syntax = SpecSyntax.model_validate(merged)
    infos = status_infos(syntax.task.statuses if syntax.task else None)
    task_syntax = syntax.task
    empty = task_syntax is None or not task_syntax.list_item or not infos
    return EffectiveSyntax(syntax=syntax, sources=sources, statuses=infos, empty=empty)


def effective_syntax(
    rules: SpecRules | None = None,
    settings: SddSettings | None = None,
    *,
    default: SpecSyntax | None = None,
) -> EffectiveSyntax:
    """스펙 규칙·사용자 설정·패키지 기본에서 유효 문법을 만든다(설계의 세 층 그대로).

    Args:
        rules: 스펙(또는 문서 틀) 규칙. None이면 스펙 층 없음.
        settings: 사용자 설정 섹션 `sdd`. None이면 기본값(기본 문법 켜짐, 설정 문법 없음).
        default: 기본 문법 대신 쓸 문법(테스트·다른 기본 데이터용). None이면 패키지 기본을 읽는다.
            `settings.include_default_syntax`가 거짓이면 쓰지 않는다.

    Returns:
        `merge_syntax` 결과.
    """
    settings = settings or SddSettings()
    layers: list[SyntaxLayer] = []
    if settings.include_default_syntax:
        layers.append((KnownSyntaxSources.DEFAULT, default or load_default_syntax()))
    layers.append((KnownSyntaxSources.SETTINGS, settings.syntax))
    layers.append((KnownSyntaxSources.SPEC, rules.syntax if rules else None))
    statuses = rules.task_statuses if rules else None
    return merge_syntax(*layers, task_statuses=(KnownSyntaxSources.SPEC, statuses))


def _markers(marker: str | list[str]) -> list[str]:
    return [marker] if isinstance(marker, str) else list(marker)


def status_infos(statuses: Iterable[TaskStatusSpec] | None) -> list[TaskStatusInfo]:
    """작업 상태 데이터를 보기용으로 푼다(라벨이 비면 id, 표시 문자는 늘 목록).

    같은 id가 둘 이상이면 처음 것만 남긴다.
    """
    seen: set[str] = set()
    out: list[TaskStatusInfo] = []
    for spec in statuses or ():
        if spec.id in seen:
            continue
        seen.add(spec.id)
        out.append(
            TaskStatusInfo(
                id=spec.id,
                label=spec.label or spec.id,
                markers=_markers(spec.marker),
                done=spec.done,
                tone=spec.tone,
            )
        )
    return out


def document_state_infos(states: Iterable[DocumentStateSpec] | None) -> list[DocumentStateInfo]:
    """문서 상태 데이터를 보기용으로 푼다(라벨이 비면 id). 같은 id는 처음 것만."""
    seen: set[str] = set()
    out: list[DocumentStateInfo] = []
    for spec in states or ():
        if spec.id in seen:
            continue
        seen.add(spec.id)
        out.append(DocumentStateInfo(id=spec.id, label=spec.label or spec.id, tone=spec.tone))
    return out

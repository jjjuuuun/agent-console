"""층 목록 → 유효 값 + 위치별 출처(`resolve_layers`)."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_settings._pointer import join_pointer
from agent_console_settings._schema import schema_annotation
from agent_console_settings._strategies import (
    DEFAULT_STRATEGIES,
    MergeContext,
    MergeIssue,
    MergeStrategy,
)
from agent_console_settings._traced import TracedValue

__all__ = ["MERGE_ANNOTATION", "Layer", "LayerInfo", "Resolved", "resolve_layers", "rule_for"]

MERGE_ANNOTATION = "x-merge"
"""스키마에서 필드별 기본 병합 전략 이름을 적는 주석 키."""

_DEFAULT_OBJECT = "merge"
_DEFAULT_OTHER = "replace"


@dataclass(frozen=True, slots=True)
class Layer:
    """설정 층 하나. 목록 앞쪽이 위 층(먼저 적용), 뒤쪽이 아래 층(나중에 덮어씀).

    - `id`: 출처로 쓰는 층 id(목록 안에서 유일).
    - `label`: 화면 표시 이름.
    - `value`: 이 층이 지정한 값(객체). 키를 생략하면 상속, 값이 있으면(`null`·빈 목록 포함) 지정.
      `None`이면 이 층은 아무것도 지정하지 않는다.
    - `source`: 선택. 이 층 값이 온 곳(파일 경로, 정의 id 등) — 표시용.
    """

    id: str
    label: str = ""
    value: Mapping[str, Any] | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class LayerInfo:
    """결과에 남기는 층 정보(값 제외)."""

    id: str
    label: str
    source: str | None


@dataclass(frozen=True, slots=True)
class Resolved:
    """병합 결과.

    - `value`: 유효 값(복사본).
    - `provenance`: `{JSON Pointer: 층 id}` — 결과에 있는 모든 위치(루트 제외).
      한 층이 통째로 정한 값은 그 아래 모든 위치가 그 층이다. 여러 층이 합쳐 만든 컨테이너
      (객체 병합, 목록 이어 붙이기 등)는 마지막으로 기여한 층이고, 잎·원소는 각자의 층이다.
    - `layers`: 적용 순서대로의 층 정보.
    - `issues`: 병합 중 문제(모르는 전략 이름, 형태 불일치). 병합은 대체 동작으로 계속했다.
    """

    value: dict[str, Any]
    provenance: Mapping[str, str]
    layers: tuple[LayerInfo, ...] = ()
    issues: tuple[MergeIssue, ...] = field(default=())

    def source_of(self, pointer: str) -> str | None:
        """`pointer` 위치 값을 정한 층 id. 결과에 없는 위치면 `None`."""
        return self.provenance.get(pointer)

    def layers_under(self, pointer: str) -> list[str]:
        """`pointer`와 그 아래 위치에 값을 준 층 id들(층 순서). 섞인 객체의 배지에 쓴다."""
        prefix = pointer + "/"
        found = {
            layer
            for at, layer in self.provenance.items()
            if at == pointer or at.startswith(prefix) or pointer == ""
        }
        return [info.id for info in self.layers if info.id in found]

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화용 `{value, provenance, layers, issues}`."""
        return {
            "value": copy.deepcopy(self.value),
            "provenance": dict(self.provenance),
            "layers": [{"id": i.id, "label": i.label, "source": i.source} for i in self.layers],
            "issues": [
                {"code": i.code, "pointer": i.pointer, "layer": i.layer, "message": i.message}
                for i in self.issues
            ],
        }


def rule_for(
    pointer: str,
    incoming: Any,
    *,
    schema: Mapping[str, Any] | None = None,
    rules: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """`pointer` 위치에 쓸 전략 이름과 그 근거(`"rules"`·`"schema"`·`"default"`).

    우선순위: 사용자 규칙(`rules`, 예: `settings_merge`) > 스키마 `x-merge` > 기본
    (이 층 값이 객체면 `merge`, 아니면 `replace`).
    """
    if rules and pointer in rules:
        return rules[pointer], "rules"
    annotated = schema_annotation(schema, pointer, MERGE_ANNOTATION)
    if isinstance(annotated, str):
        return annotated, "schema"
    return (_DEFAULT_OBJECT if isinstance(incoming, Mapping) else _DEFAULT_OTHER), "default"


def resolve_layers(
    layers: Iterable[Layer],
    *,
    schema: Mapping[str, Any] | None = None,
    rules: Mapping[str, str] | None = None,
    strategies: Mapping[str, MergeStrategy] = DEFAULT_STRATEGIES,
) -> Resolved:
    """층들을 순서대로 병합해 유효 값과 위치별 출처를 만든다.

    Args:
        layers: 위 층부터 아래 층 순서. 개수·필드 이름은 자유다.
        schema: 선택. JSON Schema. 필드별 기본 전략을 `x-merge` 주석으로 읽는다.
        rules: 선택. `{JSON Pointer: 전략 이름}` — 스키마 주석보다 우선
            (사용자 설정 `settings_merge`).
        strategies: 전략 표(기본 `DEFAULT_STRATEGIES`). 사용자 전략은 새 표에 등록해 넘긴다.

    Returns:
        `Resolved`. 모르는 전략 이름은 기본 규칙으로 대체하고 `issues`에 남긴다.

    Raises:
        ValueError: 층 id가 비었거나 겹칠 때.
    """
    layer_list = list(layers)
    ids = [layer.id for layer in layer_list]
    if any(not i for i in ids):
        raise ValueError("층 id가 비었습니다")
    if len(set(ids)) != len(ids):
        raise ValueError(f"층 id가 겹칩니다: {ids}")

    issues: list[MergeIssue] = []

    def merge_at(pointer: str, base: TracedValue | None, incoming: Any, layer: str) -> TracedValue:
        name, origin = rule_for(pointer, incoming, schema=schema, rules=rules)
        strategy = strategies.get(name)
        if strategy is None:
            fallback, _ = rule_for(pointer, incoming)
            issues.append(
                MergeIssue(
                    "unknown_strategy",
                    pointer,
                    layer,
                    f"모르는 병합 전략 {name!r}({origin}) — 기본 '{fallback}'로 대체했습니다",
                )
            )
            strategy = strategies.get(fallback) or DEFAULT_STRATEGIES[fallback]
        ctx = MergeContext(
            layer=layer,
            pointer=pointer,
            _merge_child=lambda key, b, v: merge_at(join_pointer(pointer, key), b, v, layer),
            _report=issues.append,
        )
        return strategy(base, incoming, ctx)

    traced: TracedValue | None = None
    for layer in layer_list:
        if layer.value is None:
            continue
        traced = merge_at("", traced, layer.value, layer.id)

    value: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    if traced is not None and isinstance(traced.value, dict):
        value = copy.deepcopy(traced.value)
        provenance = traced.provenance()
        provenance.pop("", None)
    elif traced is not None:
        issues.append(
            MergeIssue("type_mismatch", "", traced.source, "루트 결과가 객체가 아니어서 버렸습니다")
        )
    return Resolved(
        value=value,
        provenance=provenance,
        layers=tuple(LayerInfo(lay.id, lay.label, lay.source) for lay in layer_list),
        issues=tuple(issues),
    )

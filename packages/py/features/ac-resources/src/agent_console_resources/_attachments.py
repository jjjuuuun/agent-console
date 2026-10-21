"""첨부 목록의 층 병합 전략 `keyed_attachments`(design §R12.1, 계약 `x-merge`).

`ac-settings`의 전략 표에 이름으로 등록해 쓴다. 필드 이름(`resources`)은 이 모듈에 없다 —
어느 필드에 쓸지는 스키마 주석 `x-merge: keyed_attachments` 또는 사용자 규칙이 정한다.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Hashable, Mapping
from typing import Any

from pydantic import BaseModel

from agent_console_registry import Registry, UnknownExtensionError
from agent_console_settings import (
    MergeContext,
    MergeStrategy,
    StrategyTable,
    TracedValue,
    default_strategies,
    replace,
)

from ._interfaces import ResourceLookup, ResourceType

__all__ = [
    "ATTACHMENT_STRATEGY",
    "PREPEND_STRATEGY",
    "AttachmentKeyFn",
    "attachment_slot_key",
    "keyed_attachments_strategy",
    "prepend",
    "register_resource_strategies",
    "resource_strategies",
]

ATTACHMENT_STRATEGY = "keyed_attachments"
"""첨부 병합 전략 이름. 계약 `AgentSettings.resources`의 `x-merge` 값과 같다."""

PREPEND_STRATEGY = "prepend"
"""앞에 붙이기 전략 이름(지침을 위 층 지침보다 앞에 둘 때)."""

type AttachmentKeyFn = Callable[[Mapping[str, Any]], Hashable | None]
"""첨부(객체) → 슬롯 키. `None`이면 슬롯 키가 없다(같은 리소스 id끼리만 바꾼다)."""


def _as_mapping(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, BaseModel):
        return raw.model_dump(mode="json", exclude_unset=True)
    if isinstance(raw, Mapping):
        return dict(raw)
    return None


def _hashable(value: Any) -> Hashable:
    if isinstance(value, Hashable):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def attachment_slot_key(
    types: Registry[ResourceType], resources: ResourceLookup
) -> AttachmentKeyFn:
    """종류 디스크립터의 `slot_key`로 첨부의 슬롯 키를 계산하는 함수를 만든다.

    키 = `(종류 id, slot_key, 값)`. 값은 첨부의 `config_override`가 리소스 config보다 우선한다.
    리소스·종류를 찾지 못하거나 종류에 `slot_key`가 없거나 값이 없으면 `None`.
    """

    def key_of(att: Mapping[str, Any]) -> Hashable | None:
        ref = att.get("ref")
        resource = resources.get_resource(ref) if isinstance(ref, str) else None
        if resource is None:
            return None
        try:
            slot_key = types.get(resource.type).descriptor.slot_key
        except UnknownExtensionError:
            return None
        if not slot_key:
            return None
        override = att.get("config_override")
        value = (
            override[slot_key]
            if isinstance(override, Mapping) and slot_key in override
            else resource.config.get(slot_key)
        )
        if value is None:
            return None
        return (resource.type, slot_key, _hashable(value))

    return key_of


def keyed_attachments_strategy(slot_key_of: AttachmentKeyFn | None = None) -> MergeStrategy:
    """첨부 목록 병합 전략을 만든다.

    층의 첨부를 순서대로 적용한다.
    - `add`(기본): 뒤에 붙인다.
    - `replace`: 위 층 첨부 중 같은 리소스 id **또는** 같은 슬롯 키(`slot_key_of`)를 가진 것을
      첫 자리에서 바꾸고 나머지 같은 것은 뺀다. 바꿀 것이 없으면 뒤에 붙이고
      `resource.replace_unmatched`를 남긴다.
    - `remove`: 위 층의 같은 리소스 id 첨부를 뺀다. 뺄 것이 없으면 `resource.remove_unmatched`.

    원소마다 출처(층 id)가 남는다. 목록이 아닌 값은 교체로 대체한다(`type_mismatch`).
    """

    def keyed_attachments(
        base: TracedValue | None, incoming: Any, ctx: MergeContext, /
    ) -> TracedValue:
        if isinstance(incoming, str | bytes) or not isinstance(incoming, list | tuple):
            if incoming is not None:
                ctx.report("type_mismatch", "첨부 목록이 아니어서 교체로 대체했습니다")
            return replace(base, incoming, ctx)
        items = list(base.items()) if base is not None and base.is_array else []
        for raw in incoming:
            att = _as_mapping(raw)
            ref = att.get("ref") if att is not None else None
            if att is None or not isinstance(ref, str) or not ref:
                ctx.report(
                    "resource.invalid_attachment", f"첨부 형식이 아닙니다({type(raw).__name__})"
                )
                continue
            mode = att.get("mode", "add")
            if mode == "remove":
                kept = [t for t in items if t.value.get("ref") != ref]
                if len(kept) == len(items):
                    ctx.report("resource.remove_unmatched", f"뺄 위 층 첨부가 없습니다: {ref}")
                items = kept
                continue
            new = TracedValue.stamp(att, ctx.layer)
            if mode == "replace":
                key = slot_key_of(att) if slot_key_of is not None else None
                same = [
                    i
                    for i, t in enumerate(items)
                    if t.value.get("ref") == ref
                    or (key is not None and slot_key_of is not None and slot_key_of(t.value) == key)
                ]
                if same:
                    items[same[0]] = new
                    drop = set(same[1:])
                    items = [t for i, t in enumerate(items) if i not in drop]
                    continue
                ctx.report("resource.replace_unmatched", f"바꿀 첨부가 없어 더했습니다: {ref}")
            items.append(new)
        return TracedValue.array(items, ctx.layer)

    return keyed_attachments


def prepend(base: TracedValue | None, incoming: Any, ctx: MergeContext, /) -> TracedValue:
    """앞에 붙이기: 이 층 목록을 위 층 목록 앞에 둔다. 목록이 아니면 교체."""
    if isinstance(incoming, str | bytes) or not isinstance(incoming, list | tuple):
        if incoming is not None:
            ctx.report("type_mismatch", "'prepend' 전략은 목록이 필요해 교체로 대체했습니다")
        return replace(base, incoming, ctx)
    base_items = base.items() if base is not None and base.is_array else ()
    new = [TracedValue.stamp(v, ctx.layer) for v in incoming]
    return TracedValue.array([*new, *base_items], ctx.layer)


def register_resource_strategies(
    table: StrategyTable, *, slot_key_of: AttachmentKeyFn | None = None
) -> StrategyTable:
    """`table`에 `keyed_attachments`(이미 있으면 바꿈)와 `prepend`(없을 때만)를 등록한다.

    Returns:
        같은 `table`.

    Raises:
        RuntimeError: 얼린 표일 때.
    """
    table.register(ATTACHMENT_STRATEGY, keyed_attachments_strategy(slot_key_of), replace=True)
    if PREPEND_STRATEGY not in table:
        table.register(PREPEND_STRATEGY, prepend)
    return table


def resource_strategies(*, slot_key_of: AttachmentKeyFn | None = None) -> StrategyTable:
    """기본 전략 5개 + `keyed_attachments` + `prepend`가 든 새 표."""
    return register_resource_strategies(default_strategies(), slot_key_of=slot_key_of)

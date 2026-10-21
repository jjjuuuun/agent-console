"""실행 묶음 조립 `compose_bundle`(design §R12.4).

1. 층(공통 → 팀 구성 → 에이전트 → 노드 등)의 첨부를 `keyed_attachments`로 병합한다.
2. 남은 첨부마다 리소스 정의를 찾고 config 덮어쓰기를 반영해 종류의
   `validate`·`contribute`를 부른다.
3. 칸별로 기여를 종류의 `combine` 전략으로 합치고 출처(`BundleSource`)를 남긴다.

종류 이름·칸 이름은 이 모듈에 없다. 파일 쓰기·비밀 해석도 하지 않는다.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import (
    BundleSource,
    Issue,
    IssueSeverity,
    ResourceAttachment,
    ResourceBundle,
)
from agent_console_registry import Registry, UnknownExtensionError
from agent_console_settings import (
    DEFAULT_STRATEGIES,
    Layer,
    MergeContext,
    MergeIssue,
    Resolved,
    TracedValue,
    join_pointer,
    resolve_layers,
    rule_for,
)

from ._attachments import ATTACHMENT_STRATEGY, attachment_slot_key, resource_strategies
from ._base import effective_resource
from ._interfaces import (
    Content,
    ContributeContext,
    Contribution,
    FileContentLookup,
    ResourceLookup,
    ResourceType,
)

__all__ = [
    "AttachmentLayer",
    "ComposedBundle",
    "PlacedAttachment",
    "build_bundle",
    "compose_bundle",
    "placed_from_resolved",
    "resolve_attachments",
    "unsupported_slots",
]

SLOT_UNSUPPORTED = "resource.slot_unsupported"
"""백엔드가 받지 않는 칸(`KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED`와 같은 값)."""
SLOT_FALLBACK = "resource.slot_fallback"
"""받지 않는 칸 대신 기여의 대체 칸(`Contribution.fallback`)을 썼다(info)."""

_FIELD = "resources"
"""층 병합 때 첨부 목록을 담는 임시 필드 이름(내부용, 결과에는 나오지 않는다)."""


@dataclass(frozen=True, slots=True)
class AttachmentLayer:
    """첨부 층 하나. 목록 앞쪽이 위 층.

    - `id`: 층 id(출처). `label`: 화면 이름.
    - `attachments`: 이 층 첨부(`ResourceAttachment` 또는 같은 모양의 객체). `None` = 지정 안 함.
    """

    id: str
    attachments: Sequence[ResourceAttachment | Mapping[str, Any]] | None = None
    label: str = ""


@dataclass(frozen=True, slots=True)
class PlacedAttachment:
    """층 병합 후 남은 첨부와 그 첨부가 들어온 층 id."""

    attachment: ResourceAttachment
    layer: str | None = None


@dataclass(frozen=True, slots=True)
class ComposedBundle:
    """`compose_bundle` 결과.

    - `bundle`: 실행 묶음(`slots`, `sources`).
    - `attachments`: 병합 후 적용 순서의 첨부(화면 "리소스" 탭 목록).
    - `issues`: 찾지 못한 리소스·종류, 설정 오류, 받지 못하는 칸 등. 오류가 있는 첨부는 빠졌다.
    """

    bundle: ResourceBundle
    attachments: tuple[PlacedAttachment, ...] = ()
    issues: tuple[Issue, ...] = ()


def _issue(severity: IssueSeverity, code: str, message: str, **details: Any) -> Issue:
    return Issue(
        severity=severity,
        code=code,
        message=message,
        details={k: v for k, v in details.items() if v is not None},
    )


def _merge_issue(issue: MergeIssue) -> Issue:
    severity: IssueSeverity = "warning"
    if issue.code in ("resource.replace_unmatched", "resource.remove_unmatched"):
        severity = "info"
    code = issue.code if issue.code.startswith("resource.") else f"resource.merge.{issue.code}"
    return _issue(severity, code, issue.message, layer=issue.layer or None, pointer=issue.pointer)


def placed_from_resolved(resolved: Resolved, pointer: str = "/" + _FIELD) -> list[PlacedAttachment]:
    """`resolve_layers` 결과(예: 유효 `AgentSettings`)의 첨부 목록 → `PlacedAttachment` 목록.

    `pointer` 위치의 목록 원소마다 출처 층을 붙인다. 계약 모양이 아닌 원소는 건너뛴다.
    """
    node: Any = resolved.value
    for part in [p for p in pointer.split("/")[1:] if p]:
        node = node.get(part) if isinstance(node, Mapping) else None
    if not isinstance(node, list):
        return []
    out: list[PlacedAttachment] = []
    for index, raw in enumerate(node):
        try:
            att = ResourceAttachment.model_validate(raw)
        except ValidationError:
            continue
        out.append(PlacedAttachment(att, resolved.source_of(join_pointer(pointer, index))))
    return out


def resolve_attachments(
    layers: Iterable[AttachmentLayer],
    *,
    types: Registry[ResourceType] | None = None,
    resources: ResourceLookup | None = None,
    strategies: Mapping[str, Any] | None = None,
) -> tuple[list[PlacedAttachment], list[Issue]]:
    """층들의 첨부를 `keyed_attachments`로 병합한다.

    Args:
        layers: 위 층부터. 층 id는 겹치면 안 된다.
        types, resources: 주면 `replace`가 종류의 슬롯 키로 같은 자리를 찾는다(없으면 id만).
        strategies: 선택. 전략 표(기본 `resource_strategies(...)`).

    Raises:
        ValueError: 층 id가 비었거나 겹칠 때.
    """
    if strategies is None:
        key_of = (
            attachment_slot_key(types, resources)
            if types is not None and resources is not None
            else None
        )
        strategies = resource_strategies(slot_key_of=key_of)
    resolved = resolve_layers(
        [
            Layer(
                layer.id,
                layer.label,
                None if layer.attachments is None else {_FIELD: list(layer.attachments)},
            )
            for layer in layers
        ],
        rules={"/" + _FIELD: ATTACHMENT_STRATEGY},
        strategies=strategies,
    )
    return placed_from_resolved(resolved), [_merge_issue(i) for i in resolved.issues]


class _Folder:
    """칸 하나에 기여를 차례로 합친다(전략 표 사용)."""

    def __init__(self, strategies: Mapping[str, Any], issues: list[Issue]) -> None:
        self._strategies = strategies
        self._issues = issues

    def _report(self, issue: MergeIssue) -> None:
        self._issues.append(_merge_issue(issue))

    def fold(
        self, name: str, base: TracedValue | None, value: Any, tag: str, pointer: str
    ) -> TracedValue:
        strategy = self._strategies.get(name)
        if strategy is None:
            fallback = "append" if isinstance(value, list) else rule_for(pointer, value)[0]
            self._report(
                MergeIssue(
                    "unknown_strategy",
                    pointer,
                    tag,
                    f"모르는 합치기 전략 {name!r} — '{fallback}'로 대체했습니다",
                )
            )
            strategy = self._strategies.get(fallback) or DEFAULT_STRATEGIES[fallback]

        def child(key: str, b: TracedValue | None, v: Any) -> TracedValue:
            at = join_pointer(pointer, key)
            return self.fold(rule_for(at, v)[0], b, v, tag, at)

        ctx = MergeContext(layer=tag, pointer=pointer, _merge_child=child, _report=self._report)
        result: TracedValue = strategy(base, value, ctx)
        return result


def _override_key(att: ResourceAttachment) -> str:
    return json.dumps(att.config_override or {}, sort_keys=True, default=str)


def _read_content(rtype: ResourceType, resource: Any, resources: ResourceLookup) -> Content:
    """종류가 여러 파일 본문이면 `FileContentLookup.read_files`, 아니면 `read_content`."""
    spec = rtype.descriptor.content
    if spec is not None and spec.multi_file:
        if isinstance(resources, FileContentLookup):
            return resources.read_files(resource)
        return None
    return resources.read_content(resource) if resource.content is not None else None


def _expects_content(rtype: ResourceType, resource: Any) -> bool:
    spec = rtype.descriptor.content
    return bool(spec is not None and spec.multi_file) or resource.content is not None


def _pick(
    contribution: Contribution, accepted: Collection[str] | None
) -> tuple[Contribution, bool]:
    """받지 않는 칸이면 받는 대체 기여로 바꾼다. (쓸 기여, 대체했는지)."""
    if accepted is None or contribution.slot in accepted:
        return contribution, False
    fallback = contribution.fallback
    while fallback is not None:
        if isinstance(fallback, Contribution) and fallback.slot in accepted:
            return fallback, True
        fallback = fallback.fallback if isinstance(fallback, Contribution) else None
    return contribution, False


def build_bundle(
    attachments: Iterable[PlacedAttachment],
    *,
    types: Registry[ResourceType],
    resources: ResourceLookup,
    accepted_slots: Collection[str] | None = None,
    strategies: Mapping[str, Any] | None = None,
    slot_notes: Mapping[str, str] | None = None,
) -> ComposedBundle:
    """이미 병합된 첨부 목록으로 실행 묶음을 만든다(층 병합은 호출자가 이미 했을 때).

    Args:
        attachments: 적용 순서의 첨부(`remove`는 이미 빠져 있어야 한다. 남아 있으면 무시).
        types: 리소스 종류 레지스트리(key = 정의의 `type`).
        resources: 리소스 정의·본문 조회.
        accepted_slots: 선택. 백엔드가 받는 칸(`capabilities.resource_slots`). 주면 받지 못하는
            칸마다 `resource.slot_unsupported` 경고(칸은 묶음에 남는다). 기여에 받는 대체 칸
            (`Contribution.fallback`)이 있으면 그 칸으로 바꾸고 info `resource.slot_fallback`.
        strategies: 선택. 합치기 전략 표(기본 `resource_strategies()`).
        slot_notes: 선택. 칸 → 백엔드 설명(`capabilities.slot_notes`). 받지 않는 칸 경고의
            `details.reason`과 문구에 붙인다.

    여러 파일 본문 종류(`descriptor.content.multi_file`)는 `resources`가 `FileContentLookup`이면
    `read_files`로 읽어 `contribute`에 `{경로: 바이트}`로 넘긴다.

    Returns:
        `ComposedBundle`. 예외 대신 이슈로 알린다(리소스·종류 없음, 설정 오류, 종류 구현 예외).
    """
    table: Mapping[str, Any] = strategies if strategies is not None else resource_strategies()
    issues: list[Issue] = []
    folder = _Folder(table, issues)
    traced: dict[str, TracedValue] = {}
    sources: dict[str, list[BundleSource]] = {}
    placed_list = [p for p in attachments if p.attachment.mode != "remove"]
    seen: set[tuple[str, str]] = set()

    for placed in placed_list:
        att, layer = placed.attachment, placed.layer
        where = {"resource": att.ref, "layer": layer}
        resource = resources.get_resource(att.ref)
        if resource is None:
            issues.append(_issue("warning", "resource.not_found", "리소스가 없습니다", **where))
            continue
        try:
            rtype = types.get(resource.type)
        except UnknownExtensionError:
            issues.append(
                _issue(
                    "warning",
                    "resource.unknown_type",
                    f"등록되지 않은 리소스 종류입니다: {resource.type}",
                    resource_type=resource.type,
                    **where,
                )
            )
            continue
        dedupe = (att.ref, _override_key(att))
        if dedupe in seen:
            issues.append(
                _issue(
                    "info", "resource.duplicate", "같은 첨부가 이미 있어 건너뛰었습니다", **where
                )
            )
            continue
        seen.add(dedupe)
        effective = effective_resource(resource, att)
        try:
            found = rtype.validate(effective)
            if any(i.severity == "error" for i in found):
                issues.extend(_with_layer(found, layer))
                continue
            issues.extend(_with_layer(found, layer))
            content = _read_content(rtype, effective, resources)
            if _expects_content(rtype, effective) and content is None:
                issues.append(
                    _issue(
                        "warning", "resource.content_unreadable", "본문을 읽지 못했습니다", **where
                    )
                )
            contributions = rtype.contribute(effective, content, ContributeContext(att, layer))
        except Exception as exc:
            issues.append(
                _issue(
                    "error",
                    "resource.type_failed",
                    f"리소스 종류 {resource.type!r} 처리 중 오류: {type(exc).__name__}",
                    resource_type=resource.type,
                    **where,
                )
            )
            continue
        default_combine = rtype.descriptor.combine
        tag = f"{layer or ''}:{att.ref}"
        for contribution in contributions:
            if not isinstance(contribution, Contribution) or not contribution.slot:
                issues.append(
                    _issue("warning", "resource.bad_contribution", "기여 형식이 아닙니다", **where)
                )
                continue
            original = contribution.slot
            contribution, replaced = _pick(contribution, accepted_slots)
            if replaced:
                issues.append(
                    _issue(
                        "info",
                        SLOT_FALLBACK,
                        "실행 백엔드가 받지 않는 칸이라 대체 칸으로 전달합니다",
                        slot=original,
                        fallback=contribution.slot,
                        **where,
                    )
                )
            slot = contribution.slot
            name = contribution.combine or default_combine
            traced[slot] = folder.fold(
                name, traced.get(slot), contribution.value, tag, join_pointer("", slot)
            )
            sources.setdefault(slot, []).append(
                BundleSource(ref=att.ref, layer=layer, mode=att.mode, resource_type=resource.type)
            )

    bundle = ResourceBundle(slots={k: v.value for k, v in traced.items()}, sources=sources)
    if accepted_slots is not None:
        notes = slot_notes or {}
        for slot in unsupported_slots(bundle, accepted_slots):
            reason = notes.get(slot)
            message = f"이 백엔드는 '{slot}' 칸을 적용하지 않습니다"
            issues.append(
                _issue(
                    "warning",
                    SLOT_UNSUPPORTED,
                    f"{message}: {reason}" if reason else message,
                    slot=slot,
                    reason=reason,
                    resources=[s.ref for s in sources.get(slot, [])],
                )
            )
    return ComposedBundle(bundle, tuple(placed_list), tuple(issues))


def _with_layer(issues: Iterable[Issue], layer: str | None) -> list[Issue]:
    if layer is None:
        return list(issues)
    return [i.model_copy(update={"details": {**i.details, "layer": layer}}) for i in issues]


def compose_bundle(
    layers: Iterable[AttachmentLayer],
    *,
    types: Registry[ResourceType],
    resources: ResourceLookup,
    accepted_slots: Collection[str] | None = None,
    strategies: Mapping[str, Any] | None = None,
    slot_notes: Mapping[str, str] | None = None,
) -> ComposedBundle:
    """층별 첨부 → 실행 묶음. `resolve_attachments` + `build_bundle`.

    Args:
        layers: 위 층부터(예: 공통 → 팀 구성 → 에이전트 → 노드). 층 목록은 호출자 데이터.
        types, resources, accepted_slots, strategies, slot_notes: `build_bundle`과 같다.
            `strategies`를 주면 첨부 병합에도 같은 표를 쓴다(그 표에 `keyed_attachments`가
            있어야 한다).

    Raises:
        ValueError: 층 id가 비었거나 겹칠 때.
    """
    table = (
        strategies
        if strategies is not None
        else resource_strategies(slot_key_of=attachment_slot_key(types, resources))
    )
    placed, merge_issues = resolve_attachments(layers, strategies=table)
    result = build_bundle(
        placed,
        types=types,
        resources=resources,
        accepted_slots=accepted_slots,
        strategies=table,
        slot_notes=slot_notes,
    )
    return ComposedBundle(result.bundle, result.attachments, (*merge_issues, *result.issues))


def unsupported_slots(bundle: ResourceBundle, accepted: Collection[str]) -> list[str]:
    """묶음의 칸 중 `accepted`에 없는 칸 이름(정렬)."""
    return sorted(slot for slot in bundle.slots if slot not in accepted)

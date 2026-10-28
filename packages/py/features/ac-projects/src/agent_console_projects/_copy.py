"""공간 사이 복사(design §PI.4.2 K33-6·K33-17): 계획 → 적용 판정 → 이름 바꾸기.

모두 순수 함수다. 저장소를 모르고 문서·버전 해시 목록만 받는다. 실제 읽기·쓰기(리소스 본문 파일,
비밀 검사, 대상 첫 버전 메시지)는 부르는 쪽(`ac-mod-projects`)이 한다.

- `copy_plan`: 요청 항목 + 참조 닫힘(`references` 주입, X25), 항목마다 대상 상태(`absent`·
  `identical`·`different`)와 기본 동작(copy·reuse·없음).
- `apply_decisions`: 사용자가 고른 동작을 지금 버전과 맞춰 항목별 결과(충돌 항목만 `conflict`).
- `apply_renames`: rename 항목의 id를 바꾸고 묶음 안 참조를 새 id로 고친다
  (`rewrite_references` 주입).
- `skip_warnings`: 빼는(skip) 참조 항목 때문에 실행 전에 막힐 정의 경고.

정의 종류 이름을 모른다. 사본에 원본 id·버전·시각을 쓰지 않는다(완전 독립, 결정 B) — 이 모듈은
문서에 아무 메타도 더하지 않는다.
"""

from __future__ import annotations

import copy
import string
from collections import deque
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agent_console_contracts import (
    CopyApplyItem,
    CopyApplyItemResult,
    CopyPlan,
    CopyPlanItem,
    DefinitionKey,
    Issue,
    IssueSeverity,
    KnownCopyActions,
    KnownCopyStatuses,
    KnownCopyTargetStates,
    KnownIssueCodes,
)

from ._model import DefinitionId, References

__all__ = [
    "CODE_COPY_CONFLICT",
    "CODE_COPY_KIND_NOT_PORTABLE",
    "CODE_COPY_REFERENCE_CYCLE",
    "CODE_COPY_REFERENCE_MISSING",
    "CODE_COPY_SKIP_BREAKS_REFERENCE",
    "CODE_COPY_SOURCE_MISSING",
    "CODE_COPY_UNKNOWN_ACTION",
    "DEFAULT_COPY_MESSAGES",
    "CopyDecision",
    "RewriteReferences",
    "SourceDefinition",
    "apply_decisions",
    "apply_renames",
    "copy_plan",
    "renames_of",
    "skip_warnings",
]

CODE_COPY_CONFLICT: Final = KnownIssueCodes.PROJECT_COPY_CONFLICT
"""항목 결과 conflict의 이유(`details.reason`: source_changed·source_missing·target_changed·
target_exists·rename_taken·duplicate)."""
CODE_COPY_SOURCE_MISSING: Final = "project.copy_source_missing"
"""요청한 항목이 원본 공간에 없다(warning, 계획에서 뺌)."""
CODE_COPY_REFERENCE_MISSING: Final = "project.copy_reference_missing"
"""참조한 항목이 원본에도 대상에도 없다(warning) — 복사해도 실행 전에 막힌다."""
CODE_COPY_REFERENCE_CYCLE: Final = "project.copy_reference_cycle"
"""계획 안 정의끼리 서로 참조한다(info). 복사는 된다."""
CODE_COPY_KIND_NOT_PORTABLE: Final = "project.copy_kind_not_portable"
"""대상 공간에 둘 수 없는 종류(warning, 계획에서 뺌)."""
CODE_COPY_SKIP_BREAKS_REFERENCE: Final = "project.copy_skip_breaks_reference"
"""빼는 참조 항목이 대상에 없어 그것을 쓰는 정의가 실행 전에 막힌다(warning)."""
CODE_COPY_UNKNOWN_ACTION: Final = "project.copy_unknown_action"
"""모르는 동작(항목 결과 skipped)."""

DEFAULT_COPY_MESSAGES: Mapping[str, str] = {
    CODE_COPY_SOURCE_MISSING: "${item}이(가) 원본에 없어 계획에서 뺐습니다.",
    CODE_COPY_REFERENCE_MISSING: (
        "${source}이(가) 쓰는 ${ref}이(가) 원본에도 대상에도 없습니다. 복사해도 실행 전에 막힙니다."
    ),
    CODE_COPY_REFERENCE_CYCLE: "서로 참조하는 정의가 있습니다: ${cycle}. 함께 복사합니다.",
    CODE_COPY_KIND_NOT_PORTABLE: "${item}은(는) 프로젝트로 옮길 수 없는 종류라 뺐습니다.",
    CODE_COPY_SKIP_BREAKS_REFERENCE: "${source}은(는) ${ref}이(가) 없어 실행 전에 막힙니다.",
    CODE_COPY_CONFLICT: "${item}이(가) 계획 뒤에 바뀌어 적용하지 않았습니다(${reason}).",
    CODE_COPY_UNKNOWN_ACTION: "${item}: 알 수 없는 동작 ${action}이라 건너뜁니다.",
    KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE: (
        "참조를 알 수 없어 함께 가져올 항목을 찾지 못했습니다. 고른 항목만 복사합니다."
    ),
}
"""기본 문구(코드 → `string.Template`). 변수 item·source·ref·cycle·reason·action.
`messages=`로 바꾼다."""

type RewriteReferences = Callable[
    [str, Mapping[str, Any], Mapping[DefinitionId, str]], Mapping[str, Any]
]
"""참조 고치기 `rewrite(kind, document, renames) -> new_document`(주입, `references`의 짝).

`renames`는 (종류, 옛 id) → 새 id. 문서 안에서 그 정의를 가리키는 참조를 새 id로 바꾼 **새 문서**를
돌려준다(입력을 바꾸지 않는다). 모르는 종류면 문서를 그대로 돌려준다."""


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """원본 공간의 정의 하나.

    Attributes:
        document: 정의 문서(참조 추출에 넘긴다).
        version: 버전 해시(원본·대상 공간이 같은 해시 함수를 써야 `identical`을 알 수 있다).
        name: 표시 이름(비면 문서의 `name`).
    """

    document: Mapping[str, Any]
    version: str
    name: str = ""


def _label(key: DefinitionId) -> str:
    return f"{key[0]}/{key[1]}"


def _say(messages: Mapping[str, str] | None, code: str, **values: str) -> str:
    text = (messages or {}).get(code) or DEFAULT_COPY_MESSAGES.get(code, code)
    return string.Template(text).safe_substitute(values)


def _issue(
    messages: Mapping[str, str] | None,
    code: str,
    severity: IssueSeverity,
    details: dict[str, Any],
    **values: str,
) -> Issue:
    return Issue(
        severity=severity, code=code, message=_say(messages, code, **values), details=details
    )


def _key_of(item: DefinitionId | DefinitionKey | Mapping[str, Any]) -> DefinitionId:
    if isinstance(item, tuple):
        return (item[0], item[1])
    if isinstance(item, DefinitionKey):
        return (item.kind, item.id)
    return (str(item["kind"]), str(item["id"]))


def _dedup(refs: Iterable[tuple[str, str]]) -> list[DefinitionId]:
    seen: set[DefinitionId] = set()
    out: list[DefinitionId] = []
    for kind, ref_id in refs:
        key = (kind, ref_id)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _cycles(
    order: Sequence[DefinitionId], edges: Mapping[DefinitionId, list[DefinitionId]]
) -> list[list[DefinitionId]]:
    """계획 안 순환(강한 연결 요소 크기 2 이상 또는 자기 참조), 계획 순서대로."""
    nodes = set(order)
    graph = {k: [r for r in edges.get(k, []) if r in nodes] for k in order}
    reverse: dict[DefinitionId, list[DefinitionId]] = {k: [] for k in order}
    for k, refs in graph.items():
        for r in refs:
            reverse[r].append(k)
    finished: list[DefinitionId] = []
    seen: set[DefinitionId] = set()
    for start in order:
        if start in seen:
            continue
        seen.add(start)
        stack: list[tuple[DefinitionId, int]] = [(start, 0)]
        while stack:
            node, i = stack.pop()
            refs = graph[node]
            if i < len(refs):
                stack.append((node, i + 1))
                nxt = refs[i]
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append((nxt, 0))
            else:
                finished.append(node)
    rank = {k: i for i, k in enumerate(order)}
    assigned: set[DefinitionId] = set()
    out: list[list[DefinitionId]] = []
    for start in reversed(finished):
        if start in assigned:
            continue
        comp: list[DefinitionId] = []
        todo = [start]
        assigned.add(start)
        while todo:
            node = todo.pop()
            comp.append(node)
            for prev in reverse[node]:
                if prev not in assigned:
                    assigned.add(prev)
                    todo.append(prev)
        if len(comp) > 1 or start in graph[start]:
            out.append(sorted(comp, key=rank.__getitem__))
    out.sort(key=lambda c: rank[c[0]])
    return out


def copy_plan(
    requested: Iterable[DefinitionId | DefinitionKey | Mapping[str, Any]],
    source_docs: Mapping[DefinitionId, SourceDefinition],
    target_index: Mapping[DefinitionId, str],
    *,
    references: References | None,
    include_references: bool = True,
    kinds: Collection[str] | None = None,
    messages: Mapping[str, str] | None = None,
) -> CopyPlan:
    """복사 계획(아무것도 쓰지 않음, `POST /projects/copy/plan`).

    Args:
        requested: 고른 정의(종류, id). 같은 항목이 여러 번 와도 한 번.
        source_docs: 원본 공간의 정의(키 = (종류, id)). 필요한 키만 있는 지연 매핑이어도 된다.
        target_index: 대상 공간의 (종류, id) → 버전 해시.
        references: 참조 추출(X25). None이면 참조 닫힘·참조 관계를 보지 않고 정보 이슈 하나.
        include_references: 참조 닫힘(팀이 쓰는 에이전트·리소스·중첩 팀)을 계획에 넣는다. 거짓이면
            요청한 것만 넣고, 빠진 참조가 대상에도 없으면 skip과 같은 경고를 낸다.
        kinds: 대상 공간에 둘 수 있는 종류(옮길 수 있는 종류). None = 거르지 않음.
        messages: 문구 바꾸기(코드 → 틀).

    Returns:
        `CopyPlan` — 항목 순서는 요청 순 → 참조로 들어온 순(너비 우선). 항목마다 `reason`
        (requested·referenced), `referenced_by`(계획 안에서 이 항목을 쓰는 정의), `target_state`,
        `target_version`, `default_action`(absent → copy, identical → reuse, different → None).

    >>> docs = {("graph", "team"): SourceDefinition({"id": "team", "uses": ["a"]}, "g1"),
    ...         ("agent", "a"): SourceDefinition({"id": "a", "name": "에이"}, "a1")}
    >>> refs = lambda kind, doc: [("agent", x) for x in doc.get("uses", [])]
    >>> plan = copy_plan([("graph", "team")], docs, {("agent", "a"): "a0"}, references=refs)
    >>> [(i.id, i.reason, i.target_state, i.default_action) for i in plan.items]
    [('team', 'requested', 'absent', 'copy'), ('a', 'referenced', 'different', None)]
    """
    warnings: list[Issue] = []
    reason: dict[DefinitionId, str] = {}
    order: list[DefinitionId] = []
    edges: dict[DefinitionId, list[DefinitionId]] = {}
    queue: deque[DefinitionId] = deque()
    warned: set[tuple[str, DefinitionId]] = set()

    def warn_once(code: str, key: DefinitionId, issue: Issue) -> None:
        if (code, key) not in warned:
            warned.add((code, key))
            warnings.append(issue)

    def admit(key: DefinitionId, why: str) -> bool:
        if kinds is not None and key[0] not in kinds:
            warn_once(
                CODE_COPY_KIND_NOT_PORTABLE,
                key,
                _issue(
                    messages,
                    CODE_COPY_KIND_NOT_PORTABLE,
                    "warning",
                    {"kind": key[0], "id": key[1]},
                    item=_label(key),
                ),
            )
            return False
        reason[key] = why
        order.append(key)
        queue.append(key)
        return True

    for item in requested:
        key = _key_of(item)
        if key in reason:
            continue
        if key not in source_docs:
            warn_once(
                CODE_COPY_SOURCE_MISSING,
                key,
                _issue(
                    messages,
                    CODE_COPY_SOURCE_MISSING,
                    "warning",
                    {"kind": key[0], "id": key[1]},
                    item=_label(key),
                ),
            )
            continue
        admit(key, "requested")

    if references is None:
        warnings.append(
            _issue(messages, KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE, "info", {})
        )
    while queue:
        key = queue.popleft()
        if references is None:
            edges[key] = []
            continue
        refs = _dedup(references(key[0], source_docs[key].document))
        edges[key] = refs
        for ref in refs:
            if ref in reason:
                continue
            details = {"kind": ref[0], "id": ref[1], "source_kind": key[0], "source_id": key[1]}
            if not include_references:
                if ref not in target_index:
                    warn_once(
                        CODE_COPY_SKIP_BREAKS_REFERENCE,
                        ref,
                        _issue(
                            messages,
                            CODE_COPY_SKIP_BREAKS_REFERENCE,
                            "warning",
                            details,
                            source=_label(key),
                            ref=_label(ref),
                        ),
                    )
                continue
            if ref not in source_docs:
                if ref not in target_index:
                    warn_once(
                        CODE_COPY_REFERENCE_MISSING,
                        ref,
                        _issue(
                            messages,
                            CODE_COPY_REFERENCE_MISSING,
                            "warning",
                            details,
                            source=_label(key),
                            ref=_label(ref),
                        ),
                    )
                continue
            admit(ref, "referenced")

    referenced_by: dict[DefinitionId, list[DefinitionId]] = {k: [] for k in order}
    for k in order:
        for ref in edges.get(k, []):
            if ref in referenced_by and k not in referenced_by[ref]:
                referenced_by[ref].append(k)

    for cycle in _cycles(order, edges):
        warnings.append(
            _issue(
                messages,
                CODE_COPY_REFERENCE_CYCLE,
                "info",
                {"cycle": [{"kind": k, "id": i} for k, i in cycle]},
                cycle=" → ".join(_label(k) for k in cycle),
            )
        )

    items: list[CopyPlanItem] = []
    for key in order:
        src = source_docs[key]
        name = src.name or src.document.get("name") or ""
        target_version = target_index.get(key)
        if target_version is None:
            state, action = KnownCopyTargetStates.ABSENT, KnownCopyActions.COPY
        elif target_version == src.version:
            state, action = KnownCopyTargetStates.IDENTICAL, KnownCopyActions.REUSE
        else:
            state, action = KnownCopyTargetStates.DIFFERENT, None
        items.append(
            CopyPlanItem(
                kind=key[0],
                id=key[1],
                name=name if isinstance(name, str) else "",
                reason=reason[key],
                referenced_by=[DefinitionKey(kind=k, id=i) for k, i in referenced_by[key]],
                source_version=src.version,
                target_state=state,
                target_version=target_version,
                default_action=action,
            )
        )
    return CopyPlan(items=items, warnings=warnings)


def skip_warnings(
    plan: CopyPlan,
    actions: Mapping[DefinitionId, str],
    *,
    target_index: Mapping[DefinitionId, str],
    messages: Mapping[str, str] | None = None,
) -> list[Issue]:
    """빼는(skip) 항목 때문에 실행 전에 막힐 정의 경고(계획 대화상자의 즉시 경고).

    skip한 항목이 대상에 없고, 그것을 쓰는 계획 항목이 skip이 아니면 경고 하나씩.

    >>> plan = CopyPlan(items=[
    ...     CopyPlanItem(kind="graph", id="t", reason="requested", source_version="1",
    ...                  target_state="absent"),
    ...     CopyPlanItem(kind="agent", id="a", reason="referenced", source_version="2",
    ...                  target_state="absent",
    ...                  referenced_by=[DefinitionKey(kind="graph", id="t")])])
    >>> [i.message for i in skip_warnings(plan, {("agent", "a"): "skip"}, target_index={})]
    ['graph/t은(는) agent/a이(가) 없어 실행 전에 막힙니다.']
    """
    out: list[Issue] = []
    for item in plan.items:
        key = (item.kind, item.id)
        if actions.get(key) != KnownCopyActions.SKIP or key in target_index:
            continue
        for user in item.referenced_by:
            ukey = (user.kind, user.id)
            if actions.get(ukey, KnownCopyActions.COPY) == KnownCopyActions.SKIP:
                continue
            out.append(
                _issue(
                    messages,
                    CODE_COPY_SKIP_BREAKS_REFERENCE,
                    "warning",
                    {"kind": key[0], "id": key[1], "source_kind": ukey[0], "source_id": ukey[1]},
                    source=_label(ukey),
                    ref=_label(key),
                )
            )
    return out


@dataclass(frozen=True, slots=True)
class CopyDecision:
    """적용 항목 하나의 판정(쓰기 전).

    Attributes:
        kind: 종류.
        id: 원본 id.
        action: 요청 동작.
        target_id: 대상에 쓸 id(rename이면 새 id).
        status: `KnownCopyStatuses` 값. copied·overwritten·renamed면 부르는 쪽이 쓴다.
        issue: conflict·skipped 이유.
    """

    kind: str
    id: str
    action: str
    target_id: str
    status: str
    issue: Issue | None = None

    @property
    def key(self) -> DefinitionId:
        return (self.kind, self.id)

    @property
    def writes(self) -> bool:
        """대상에 써야 하나(copied·overwritten·renamed)."""
        return self.status in (
            KnownCopyStatuses.COPIED,
            KnownCopyStatuses.OVERWRITTEN,
            KnownCopyStatuses.RENAMED,
        )

    def result(self) -> CopyApplyItemResult:
        """응답 항목."""
        return CopyApplyItemResult(
            kind=self.kind,
            id=self.id,
            new_id=self.target_id if self.action == KnownCopyActions.RENAME else None,
            status=self.status,
            issue=self.issue,
        )


_WRITE_STATUS: Final = {
    KnownCopyActions.COPY: KnownCopyStatuses.COPIED,
    KnownCopyActions.OVERWRITE: KnownCopyStatuses.OVERWRITTEN,
    KnownCopyActions.RENAME: KnownCopyStatuses.RENAMED,
}


def apply_decisions(
    items: Iterable[CopyApplyItem | Mapping[str, Any]],
    *,
    source_index: Mapping[DefinitionId, str],
    target_index: Mapping[DefinitionId, str],
    messages: Mapping[str, str] | None = None,
) -> list[CopyDecision]:
    """고른 동작 → 항목별 판정(`POST /projects/copy/apply`의 쓰기 전 단계).

    지금 원본·대상 버전을 계획 때 값과 맞춘다. 맞지 않는 항목만 `conflict`(이슈
    `project.copy_conflict`, `details.reason`)이고 나머지는 판정대로 적용한다.

    - 원본: 없어짐 `source_missing`, 버전 다름 `source_changed`(skip 제외 전부).
    - copy: 대상에 그새 생김 `target_exists`. overwrite·reuse: 대상 버전이 계획 때와 다름
      `target_changed`(If-Match). rename: 새 id가 대상에 있음 `rename_taken`.
    - 같은 대상 키에 두 번 쓰면 뒤의 것 `duplicate`.

    Args:
        items: 적용 항목(`CopyApplyItem` 또는 같은 키 dict).
        source_index: 원본 공간의 지금 (종류, id) → 버전.
        target_index: 대상 공간의 지금 (종류, id) → 버전.

    >>> d = apply_decisions(
    ...     [{"kind": "agent", "id": "a", "action": "copy", "source_version": "1"},
    ...      {"kind": "agent", "id": "b", "action": "overwrite", "source_version": "2",
    ...       "target_version": "old"}],
    ...     source_index={("agent", "a"): "1", ("agent", "b"): "2"},
    ...     target_index={("agent", "b"): "new"})
    >>> [(x.id, x.status, x.issue.details["reason"] if x.issue else None) for x in d]
    [('a', 'copied', None), ('b', 'conflict', 'target_changed')]
    """
    out: list[CopyDecision] = []
    claimed: set[DefinitionId] = set()
    for raw in items:
        item = raw if isinstance(raw, CopyApplyItem) else CopyApplyItem.model_validate(raw)
        key = (item.kind, item.id)
        target_id = (
            item.new_id if item.action == KnownCopyActions.RENAME and item.new_id else item.id
        )

        def conflict(
            reason: str, item: CopyApplyItem = item, target_id: str = target_id
        ) -> CopyDecision:
            return CopyDecision(
                kind=item.kind,
                id=item.id,
                action=item.action,
                target_id=target_id,
                status=KnownCopyStatuses.CONFLICT,
                issue=_issue(
                    messages,
                    CODE_COPY_CONFLICT,
                    "warning",
                    {"kind": item.kind, "id": item.id, "reason": reason},
                    item=f"{item.kind}/{item.id}",
                    reason=reason,
                ),
            )

        if item.action == KnownCopyActions.SKIP:
            out.append(
                CopyDecision(item.kind, item.id, item.action, item.id, KnownCopyStatuses.SKIPPED)
            )
            continue
        if item.action not in (*_WRITE_STATUS, KnownCopyActions.REUSE):
            out.append(
                CopyDecision(
                    item.kind,
                    item.id,
                    item.action,
                    item.id,
                    KnownCopyStatuses.SKIPPED,
                    _issue(
                        messages,
                        CODE_COPY_UNKNOWN_ACTION,
                        "warning",
                        {"kind": item.kind, "id": item.id, "action": item.action},
                        item=f"{item.kind}/{item.id}",
                        action=item.action,
                    ),
                )
            )
            continue
        current_source = source_index.get(key)
        if current_source is None:
            out.append(conflict("source_missing"))
            continue
        if current_source != item.source_version:
            out.append(conflict("source_changed"))
            continue
        tkey = (item.kind, target_id)
        current_target = target_index.get(tkey)
        if item.action == KnownCopyActions.REUSE:
            if current_target is None or current_target != item.target_version:
                out.append(conflict("target_changed"))
            else:
                out.append(
                    CopyDecision(
                        item.kind, item.id, item.action, target_id, KnownCopyStatuses.REUSED
                    )
                )
            continue
        if tkey in claimed:
            out.append(conflict("duplicate"))
            continue
        if item.action == KnownCopyActions.COPY and current_target is not None:
            out.append(conflict("target_exists"))
            continue
        if item.action == KnownCopyActions.OVERWRITE and current_target != item.target_version:
            out.append(conflict("target_changed"))
            continue
        if item.action == KnownCopyActions.RENAME and current_target is not None:
            out.append(conflict("rename_taken"))
            continue
        claimed.add(tkey)
        out.append(
            CopyDecision(item.kind, item.id, item.action, target_id, _WRITE_STATUS[item.action])
        )
    return out


def renames_of(decisions: Iterable[CopyDecision]) -> dict[DefinitionId, str]:
    """적용할 rename 판정 → (종류, 옛 id) → 새 id(`apply_renames` 입력)."""
    return {
        d.key: d.target_id
        for d in decisions
        if d.status == KnownCopyStatuses.RENAMED and d.target_id != d.id
    }


def apply_renames(
    docs: Mapping[DefinitionId, Mapping[str, Any]],
    renames: Mapping[DefinitionId, str],
    *,
    rewrite_references: RewriteReferences,
) -> dict[DefinitionId, dict[str, Any]]:
    """이름 바꾸기: rename 항목의 `id`를 새 id로, 묶음 안 모든 문서의 참조를 새 id로 고친다.

    입력 문서는 바꾸지 않는다(깊은 복사). 결과 키는 새 (종류, id).

    Raises:
        ValueError: 두 문서가 같은 새 키가 됨.

    >>> def rewrite(kind, doc, renames):
    ...     return {**doc, "uses": [renames.get(("agent", u), u) for u in doc.get("uses", [])]}
    >>> docs = {("graph", "t"): {"id": "t", "uses": ["a"]}, ("agent", "a"): {"id": "a"}}
    >>> out = apply_renames(docs,
    ...                     {("agent", "a"): "a-copy"}, rewrite_references=rewrite)
    >>> sorted(out), out[("graph", "t")]["uses"]
    ([('agent', 'a-copy'), ('graph', 't')], ['a-copy'])
    """
    out: dict[DefinitionId, dict[str, Any]] = {}
    for key, doc in docs.items():
        new_doc = copy.deepcopy(dict(doc))
        new_key = key
        if key in renames:
            new_key = (key[0], renames[key])
            new_doc["id"] = renames[key]
        if renames:
            new_doc = copy.deepcopy(dict(rewrite_references(key[0], new_doc, renames)))
        if new_key in out:
            raise ValueError(f"이름을 바꾼 뒤 같은 정의가 둘입니다: {_label(new_key)}")
        out[new_key] = new_doc
    return out

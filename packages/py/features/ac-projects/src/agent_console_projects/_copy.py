"""공간 사이 복사(design §PI.4.2 K33-6·K33-17): 계획 → 적용 판정 → 이름 바꾸기.

모두 순수 함수다. 저장소를 모르고 문서·버전 해시 목록만 받는다. 실제 읽기·쓰기(리소스 본문 파일,
비밀 검사, 대상 첫 버전 메시지)는 부르는 쪽(`ac-mod-projects`)이 한다.

- `copy_plan`: 요청 항목 + 참조 닫힘(`references` 주입, X25), 항목마다 대상 상태(`absent`·
  `identical`·`different`)와 기본 동작(copy·reuse·없음).
- `apply_decisions`: 사용자가 고른 동작을 지금 버전과 맞춰 항목별 결과(충돌 항목만 `conflict`).
- `apply_renames`: rename 항목의 id를 바꾸고 묶음 안 참조를 새 id로 고친다
  (`rewrite_references` 주입).
- `reserved_target_issues`: 적용 요청에서 대상에 쓸 id(copy·overwrite = 원본 id, rename = 새 id)가
  그 종류의 예약어인 항목(적용 전에 요청 전체를 거절할 근거).
- `skip_warnings`: 빼는(skip) 참조 항목 때문에 실행 전에 막힐 정의 경고.
- `copy_target_label`: 문구의 `${target}`(대상 공간 표시 이름 — 공용 구성 / 따옴표 친
  프로젝트 이름).

정의 종류 이름을 모른다. 사본에 원본 id·버전·시각을 쓰지 않는다(완전 독립, 결정 B) — 이 모듈은
문서에 아무 메타도 더하지 않는다.
"""

from __future__ import annotations

import copy
import string
from collections import deque
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

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

from ._identity import registration_id
from ._model import DefinitionId, References

__all__ = [
    "CODE_COPY_CONFLICT",
    "CODE_COPY_KIND_NOT_PORTABLE",
    "CODE_COPY_REFERENCE_CYCLE",
    "CODE_COPY_REFERENCE_MISSING",
    "CODE_COPY_RESERVED_ID",
    "CODE_COPY_SKIP_BREAKS_REFERENCE",
    "CODE_COPY_SOURCE_MISSING",
    "CODE_COPY_UNKNOWN_ACTION",
    "CODE_SECRET_PLAIN_FOUND",
    "COPY_RESERVED_RENAME",
    "COPY_RESERVED_WRITE",
    "COPY_TARGET_LIBRARY",
    "COPY_TARGET_PROJECT",
    "DEFAULT_COPY_MESSAGES",
    "DEFAULT_TARGET_LABEL",
    "CopyDecision",
    "PlainFinding",
    "PlainSecretCheck",
    "RewriteReferences",
    "SourceDefinition",
    "apply_decisions",
    "apply_renames",
    "copy_plan",
    "copy_target_label",
    "renames_of",
    "reserved_target_issues",
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
CODE_COPY_RESERVED_ID: Final = "project.copy_reserved_id"
"""항목 id가 그 종류의 예약어(`reserved_ids`, 예: 같은 깊이의 고정 REST 경로)라 대상 공간에서 그
id로 열 수 없다(warning). `details{kind, id, reserved, suggested_id}`, 쓰는 항목의 기본 동작은
rename(대상에 없음) 또는 고르기(내용이 다름)다."""
COPY_RESERVED_RENAME: Final = "project.copy_reserved_id.rename"
"""문구 표 키: 적용 요청의 rename 새 id가 예약어일 때(`reserved_target_issues`, 이슈 코드는
`project.copy_reserved_id` 그대로). 변수 item·id(새 id)·suggested·target."""
COPY_RESERVED_WRITE: Final = "project.copy_reserved_id.write"
"""문구 표 키: 적용 요청이 예약어인 원본 id를 그대로(copy·overwrite) 쓰려 할 때
(`reserved_target_issues`). 변수 item·id·suggested·target."""
CODE_COPY_UNKNOWN_ACTION: Final = "project.copy_unknown_action"
"""모르는 동작(항목 결과 skipped)."""
CODE_SECRET_PLAIN_FOUND: Final = KnownIssueCodes.SECRET_PLAIN_FOUND
"""대상 공간이 거절할 평문 비밀(항목 error, 값 없음). 그 항목은 막힘(`blocked`)이다."""
COPY_TARGET_LIBRARY: Final = "project.copy_target.library"
"""문구 표 키: 대상이 공용 구성(라이브러리)일 때 `${target}`."""
COPY_TARGET_PROJECT: Final = "project.copy_target.project"
"""문구 표 키: 대상이 프로젝트일 때 `${target}`(변수 `name` = 프로젝트 이름)."""
DEFAULT_TARGET_LABEL: Final = "대상 공간"
"""`copy_plan`의 `target_label` 기본값(부르는 쪽이 대상을 알려 주지 않을 때)."""

DEFAULT_COPY_MESSAGES: Mapping[str, str] = {
    CODE_COPY_SOURCE_MISSING: "${item}이(가) 원본에 없어 계획에서 뺐습니다.",
    CODE_COPY_REFERENCE_MISSING: (
        "${source}이(가) 쓰는 ${ref}이(가) 원본에도 대상에도 없습니다. 복사해도 실행 전에 막힙니다."
    ),
    CODE_COPY_REFERENCE_CYCLE: "서로 참조하는 정의가 있습니다: ${cycle}. 함께 복사합니다.",
    CODE_COPY_KIND_NOT_PORTABLE: "${item}은(는) ${target}에 둘 수 없는 종류라 뺐습니다.",
    CODE_SECRET_PLAIN_FOUND: (
        "${item}의 ${path}에 비밀처럼 보이는 평문이 있어 ${target}에 둘 수 없습니다. "
        "비밀 저장소에 넣고 secret:// 참조로 바꾸세요."
    ),
    CODE_COPY_SKIP_BREAKS_REFERENCE: "${source}은(는) ${ref}이(가) 없어 실행 전에 막힙니다.",
    CODE_COPY_CONFLICT: "${item}이(가) 계획 뒤에 바뀌어 적용하지 않았습니다(${reason}).",
    CODE_COPY_UNKNOWN_ACTION: "${item}: 알 수 없는 동작 ${action}이라 건너뜁니다.",
    CODE_COPY_RESERVED_ID: (
        "${item}의 id \u2018${id}\u2019는 이 종류의 경로 이름과 겹쳐 ${target}에서 열 수 없습니다. "
        "새 id \u2018${suggested}\u2019로 바꿔 복사하세요."
    ),
    COPY_RESERVED_RENAME: (
        "${item}의 새 id \u2018${id}\u2019는 이 종류의 경로 이름과 겹쳐 ${target}에서 열 수 "
        "없습니다. 다른 id(예: \u2018${suggested}\u2019)를 쓰세요."
    ),
    COPY_RESERVED_WRITE: (
        "${item}의 id \u2018${id}\u2019는 이 종류의 경로 이름과 겹쳐 ${target}에서 열 수 없어 "
        "그대로 쓸 수 없습니다. 새 id(예: \u2018${suggested}\u2019)로 이름을 바꿔 복사하세요."
    ),
    KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE: (
        "참조를 알 수 없어 함께 가져올 항목을 찾지 못했습니다. 고른 항목만 복사합니다."
    ),
    COPY_TARGET_LIBRARY: "공용 구성",
    COPY_TARGET_PROJECT: "프로젝트 \u2018${name}\u2019",
}
"""기본 문구(코드 → `string.Template`). 변수 item·source·ref·cycle·reason·action·target·path·
id·suggested, 대상 이름 틀(`COPY_TARGET_*`)은 name. `messages=`로 바꾼다."""


class PlainFinding(Protocol):
    """평문 비밀 의심 위치 하나(값 없음). `agent_console_secret_rules.Finding`이 만족한다."""

    @property
    def path(self) -> str: ...

    @property
    def reason(self) -> str: ...


type PlainSecretCheck = Callable[[str, Mapping[str, Any]], Iterable[PlainFinding]]
"""대상 공간이 쓸 때 거절할 평문 비밀 위치 `check(kind, document) -> [위치]`(주입).

부르는 쪽은 대상 공간의 쓰기 검사와 **같은 판정**을 넣는다(예: `scan_secrets(rules, doc)`).
`path`는 정의 문서 기준 JSON Pointer다."""


def copy_target_label(
    project_name: str | None, *, messages: Mapping[str, str] | None = None
) -> str:
    """문구의 `${target}`: None이면 공용 구성, 아니면 따옴표 친 프로젝트 이름(문구 표 데이터).

    >>> copy_target_label(None)
    '공용 구성'
    >>> copy_target_label("결제") == "프로젝트 \u2018결제\u2019"
    True
    >>> copy_target_label("결제", messages={COPY_TARGET_PROJECT: "${name} 폴더"})
    '결제 폴더'
    """
    if project_name is None:
        return _say(messages, COPY_TARGET_LIBRARY)
    return _say(messages, COPY_TARGET_PROJECT, name=project_name)


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
    target_label: str = DEFAULT_TARGET_LABEL,
    plain_secrets: PlainSecretCheck | None = None,
    reserved_ids: Mapping[str, Collection[str]] | None = None,
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
        target_label: 문구의 `${target}`(대상 공간 표시 이름, `copy_target_label`로 만든다).
        plain_secrets: 대상 공간이 거절할 평문 비밀 판정(`PlainSecretCheck`). 걸린 항목은 막힘
            (`blocked`, `default_action` skip, 위치마다 error `secret.plain_found`
            `details{kind, id, path, reason}` — 값 없음). None = 보지 않음.
        reserved_ids: 종류 → 그 종류 id로 쓰면 안 되는 말(대소문자 무시, 정의 종류 데이터
            `DefinitionKind.reserved_ids`). 대상에 그 id로 쓰게 되는 항목(대상에 없음·내용이 다름)은
            `warnings`에 `project.copy_reserved_id`(`details.suggested_id` = 대상·예약어·다른 제안과
            겹치지 않는 `<id>-2`…)를 더하고, 대상에 없으면 기본 동작을 rename으로 한다. None = 보지
            않음.

    Returns:
        `CopyPlan` — 항목 순서는 요청 순 → 참조로 들어온 순(너비 우선). 항목마다 `reason`
        (requested·referenced), `referenced_by`(계획 안에서 이 항목을 쓰는 정의), `target_state`,
        `target_version`, `default_action`(absent → copy, identical → reuse, different → None,
        막힘 → skip). 막힌 항목 때문에 그것을 쓰는 정의가 실행 전에 막히면 `warnings`에
        `project.copy_skip_breaks_reference`를 더한다.

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
                    target=target_label,
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

    reserved = {
        kind: {w.casefold() for w in words} for kind, words in (reserved_ids or {}).items() if words
    }
    suggested: dict[DefinitionId, str] = {}
    items: list[CopyPlanItem] = []
    for key in order:
        src = source_docs[key]
        name = src.name or src.document.get("name") or ""
        target_version = target_index.get(key)
        action: str | None
        if target_version is None:
            state, action = KnownCopyTargetStates.ABSENT, KnownCopyActions.COPY
        elif target_version == src.version:
            state, action = KnownCopyTargetStates.IDENTICAL, KnownCopyActions.REUSE
        else:
            state, action = KnownCopyTargetStates.DIFFERENT, None
        blocking = _plain_issues(key, src.document, plain_secrets, messages, target_label)
        words = reserved.get(key[0], set())
        if key[1].casefold() in words and state != KnownCopyTargetStates.IDENTICAL:
            taken = [i for k, i in target_index if k == key[0]]
            taken += [i for (k, _), i in suggested.items() if k == key[0]]
            new_id = registration_id(key[1], [*taken, *words])
            suggested[key] = new_id
            warnings.append(
                _issue(
                    messages,
                    CODE_COPY_RESERVED_ID,
                    "warning",
                    {
                        "kind": key[0],
                        "id": key[1],
                        "reserved": sorted(reserved_ids[key[0]] if reserved_ids else ()),
                        "suggested_id": new_id,
                    },
                    item=_label(key),
                    id=key[1],
                    suggested=new_id,
                    target=target_label,
                )
            )
            if state == KnownCopyTargetStates.ABSENT:
                action = KnownCopyActions.RENAME
        if blocking:
            action = KnownCopyActions.SKIP
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
                blocked=bool(blocking),
                issues=blocking,
            )
        )
    plan = CopyPlan(items=items, warnings=warnings)
    blocked = {(i.kind, i.id): KnownCopyActions.SKIP for i in items if i.blocked}
    if blocked:
        plan.warnings.extend(
            skip_warnings(plan, blocked, target_index=target_index, messages=messages)
        )
    return plan


def _plain_issues(
    key: DefinitionId,
    document: Mapping[str, Any],
    check: PlainSecretCheck | None,
    messages: Mapping[str, str] | None,
    target_label: str,
) -> list[Issue]:
    """항목 하나의 막힘 이슈(위치마다 error `secret.plain_found`, 값 없음)."""
    if check is None:
        return []
    out: list[Issue] = []
    seen: set[str] = set()
    for finding in check(key[0], document):
        if finding.path in seen:
            continue
        seen.add(finding.path)
        out.append(
            Issue(
                severity="error",
                code=CODE_SECRET_PLAIN_FOUND,
                message=_say(
                    messages,
                    CODE_SECRET_PLAIN_FOUND,
                    item=_label(key),
                    path=finding.path or "/",
                    target=target_label,
                ),
                path=finding.path or None,
                details={
                    "kind": key[0],
                    "id": key[1],
                    "path": finding.path,
                    "reason": finding.reason,
                },
            )
        )
    return out


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
        target_id = _target_id(item)

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


def _target_id(item: CopyApplyItem) -> str:
    """대상에 쓸 id(`apply_decisions`와 같은 규칙: rename이고 새 id가 있으면 새 id)."""
    return item.new_id if item.action == KnownCopyActions.RENAME and item.new_id else item.id


_RESERVED_CHECKED: Final = (
    KnownCopyActions.COPY,
    KnownCopyActions.OVERWRITE,
    KnownCopyActions.RENAME,
)
"""대상에 그 id로 쓰는 동작(reuse·skip은 쓰지 않으므로 보지 않는다)."""


def reserved_target_issues(
    items: Iterable[CopyApplyItem | Mapping[str, Any]],
    reserved_ids: Mapping[str, Collection[str]] | None,
    *,
    target_index: Mapping[DefinitionId, str] | None = None,
    messages: Mapping[str, str] | None = None,
    target_label: str = DEFAULT_TARGET_LABEL,
) -> list[Issue]:
    """대상에 쓸 id가 그 종류의 예약어(대소문자 무시)인 항목마다 error 이슈 하나.

    copy·overwrite는 원본 id, rename은 새 id를 본다(`apply_decisions`와 같은 대상 id). 계획의
    `suggested_id`는 이미 예약어를 피하므로, 걸리는 것은 사용자가 직접 넣은 새 id이거나 계획
    경고(`project.copy_reserved_id`)를 두고 예약어 id를 그대로 쓰려는 항목이다. 부르는 쪽은 이슈가
    하나라도 있으면 아무것도 쓰지 않고 요청을 거절한다(422). reuse·skip은 쓰지 않으므로 보지 않는다.

    Args:
        items: 적용 항목(`CopyApplyItem` 또는 같은 키 dict).
        reserved_ids: 종류 → 예약어(정의 종류 데이터 `DefinitionKind.reserved_ids`).
            None = 보지 않음.
        target_index: 대상 공간의 (종류, id) → 버전. 제안 id(`details.suggested_id`)가 대상에 있는
            id·예약어·요청의 다른 대상 id와 겹치지 않게 쓴다.
        messages: 문구 바꾸기(rename은 키 `COPY_RESERVED_RENAME`, copy·overwrite는
            `COPY_RESERVED_WRITE`).
        target_label: 문구의 `${target}`.

    Returns:
        error `project.copy_reserved_id` 이슈 목록(요청 순). `details{kind, id, action, target_id,
        reserved, suggested_id}`(rename이면 `new_id`도), `path`는 rename `/items/<n>/new_id`,
        그 밖 `/items/<n>/id`.

    >>> issues = reserved_target_issues(
    ...     [{"kind": "tpl", "id": "a", "action": "rename", "new_id": "Check",
    ...       "source_version": "1"},
    ...      {"kind": "tpl", "id": "variables", "action": "copy", "source_version": "1"}],
    ...     {"tpl": ("variables", "check")})
    >>> [(i.details["action"], i.details["target_id"], i.details["suggested_id"]) for i in issues]
    [('rename', 'Check', 'Check-2'), ('copy', 'variables', 'variables-2')]
    """
    reserved = {
        kind: {w.casefold() for w in words} for kind, words in (reserved_ids or {}).items() if words
    }
    if not reserved:
        return []
    parsed = [
        raw if isinstance(raw, CopyApplyItem) else CopyApplyItem.model_validate(raw)
        for raw in items
    ]
    wanted = [(i.kind, _target_id(i)) for i in parsed if i.action in _RESERVED_CHECKED]
    out: list[Issue] = []
    suggested: list[DefinitionId] = []
    for index, item in enumerate(parsed):
        if item.action not in _RESERVED_CHECKED:
            continue
        target_id = _target_id(item)
        words = reserved.get(item.kind)
        if not words or target_id.casefold() not in words:
            continue
        taken = [i for k, i in (target_index or {}) if k == item.kind]
        taken += [i for k, i in (*wanted, *suggested) if k == item.kind]
        suggestion = registration_id(target_id, [*taken, *words])
        suggested.append((item.kind, suggestion))
        renaming = item.action == KnownCopyActions.RENAME
        key = (item.kind, item.id)
        out.append(
            Issue(
                severity="error",
                code=CODE_COPY_RESERVED_ID,
                message=_say(
                    messages,
                    COPY_RESERVED_RENAME if renaming else COPY_RESERVED_WRITE,
                    item=_label(key),
                    id=target_id,
                    suggested=suggestion,
                    target=target_label,
                ),
                path=f"/items/{index}/{'new_id' if renaming else 'id'}",
                details={
                    "kind": item.kind,
                    "id": item.id,
                    "action": item.action,
                    "target_id": target_id,
                    **({"new_id": target_id} if renaming else {}),
                    "reserved": sorted((reserved_ids or {})[item.kind]),
                    "suggested_id": suggestion,
                },
            )
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

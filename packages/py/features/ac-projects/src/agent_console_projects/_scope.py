"""범위 규칙: 보이는지(`visible`), 범위 검사(`scope_issues`), 옮기기·삭제 계획(design §UX-P.2).

- 범위는 두 가지다: 공용(``None``) / 프로젝트 전용(프로젝트 id).
- 프로젝트 P를 고른 화면에 보이는 정의 = 공용 + P 전용. "모든 프로젝트"(``None``)는 전부.
- 참조 규칙은 **경고**다(저장·실행을 막지 않음). 공용 정의는 공용만, P 전용 정의는 공용 + P 전용을
  쓴다. 없는 프로젝트를 가리키는 정의는 정보 이슈를 내고 공용으로 본다.
"""

from __future__ import annotations

import string
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from agent_console_contracts import (
    DefinitionKey,
    DefinitionMove,
    DeletePlan,
    GraphPatch,
    Issue,
    IssueSeverity,
    IssueSuggestion,
    KnownIssueCodes,
    KnownSuggestionIds,
    MovePlan,
    Project,
)

from ._model import (
    DefinitionId,
    References,
    ScopedDefinition,
    effective_scope,
    known_project_ids,
)

__all__ = [
    "CODE_CROSS_PROJECT",
    "CODE_REFERENCES_UNAVAILABLE",
    "CODE_SHARED_USES_PROJECT",
    "CODE_UNKNOWN",
    "DEFAULT_MESSAGES",
    "MOVE_TO_SHARED_SUGGESTION",
    "UnknownDefinitionError",
    "delete_plan",
    "move_plan",
    "scope_issues",
    "visible",
]

CODE_SHARED_USES_PROJECT: Final = KnownIssueCodes.PROJECT_SHARED_USES_PROJECT
CODE_CROSS_PROJECT: Final = KnownIssueCodes.PROJECT_CROSS_PROJECT
CODE_UNKNOWN: Final = KnownIssueCodes.PROJECT_UNKNOWN
CODE_REFERENCES_UNAVAILABLE: Final = KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE
"""참조 추출이 주입되지 않아 참조 규칙을 보지 못했다(info). 예: 정의 모듈이 꺼짐(design §UX-P.5)."""

MOVE_TO_SHARED_SUGGESTION: Final = KnownSuggestionIds.PROJECT_MOVE_TO_SHARED
"""[공용으로 옮기기] 제안 id. 옮길 정의는 이슈 `details`의 `kind`·`id`(`details.move`에도 같음)."""

DEFAULT_MESSAGES: Mapping[str, str] = {
    CODE_SHARED_USES_PROJECT: (
        "공용 ${source}이(가) 프로젝트 ${ref_project} 전용 ${ref}을(를) 씁니다. "
        "다른 프로젝트에서는 ${ref}이(가) 보이지 않습니다."
    ),
    CODE_CROSS_PROJECT: (
        "프로젝트 ${source_project} 전용 ${source}이(가) 다른 프로젝트 ${ref_project} 전용 "
        "${ref}을(를) 씁니다."
    ),
    CODE_UNKNOWN: (
        "${source}이(가) 없는 프로젝트 ${source_project}을(를) 가리킵니다. 공용으로 봅니다."
    ),
    CODE_REFERENCES_UNAVAILABLE: "참조를 알 수 없어 프로젝트 범위 검사를 하지 못했습니다.",
    MOVE_TO_SHARED_SUGGESTION: "${ref}을(를) 공용으로 옮기기",
}
"""기본 문구(코드 → `string.Template`). 변수 source·source_kind·source_id·source_project·ref·
ref_kind·ref_id·ref_project. 호출자가 `messages=`로 일부·전부를 바꾼다(없는 키는 기본값)."""


class UnknownDefinitionError(LookupError):
    """옮기려는 정의가 주어진 정의 목록에 없다."""


def visible(
    scope: str | None, project_id: str | None, *, known: Collection[str] | None = None
) -> bool:
    """프로젝트 `project_id`를 고른 화면에 범위 `scope`인 정의가 보이는지.

    Args:
        scope: 정의의 `project` 값(``None`` = 공용).
        project_id: 고른 프로젝트(``None`` = 모든 프로젝트, 거르지 않음).
        known: 있는 프로젝트 id. 주면 없는 프로젝트를 가리키는 정의를 공용으로 본다.

    >>> visible(None, "app"), visible("app", "app"), visible("web", "app"), visible("web", None)
    (True, True, False, True)
    """
    if project_id is None:
        return True
    eff = effective_scope(scope, known)
    return eff is None or eff == project_id


# ---------------------------------------------------------------- 범위 검사


@dataclass(frozen=True, slots=True)
class _Found:
    issue: Issue
    source: DefinitionId
    ref: DefinitionId | None


def _render(messages: Mapping[str, str] | None, code: str, values: Mapping[str, str]) -> str:
    template = (messages or {}).get(code) or DEFAULT_MESSAGES.get(code, code)
    return string.Template(template).safe_substitute(values)


def _values(source: ScopedDefinition, ref: ScopedDefinition | None) -> dict[str, str]:
    v = {
        "source": source.label,
        "source_kind": source.kind,
        "source_id": source.id,
        "source_project": source.project or "",
    }
    if ref is not None:
        v |= {
            "ref": ref.label,
            "ref_kind": ref.kind,
            "ref_id": ref.id,
            "ref_project": ref.project or "",
        }
    return v


def _scope_detail(d: ScopedDefinition) -> dict[str, Any]:
    return {"kind": d.kind, "id": d.id, "project": d.project}


def _ref_issue(
    code: str,
    source: ScopedDefinition,
    ref: ScopedDefinition,
    messages: Mapping[str, str] | None,
) -> Issue:
    values = _values(source, ref)
    return Issue(
        severity="warning",
        code=code,
        message=_render(messages, code, values),
        # 계약 문서(KnownIssueCodes): details.kind·id·project = 참조된 정의.
        details={
            **_scope_detail(ref),
            "source": _scope_detail(source),
            "move": {"kind": ref.kind, "id": ref.id, "to": None},
        },
        suggestions=[
            IssueSuggestion(
                id=MOVE_TO_SHARED_SUGGESTION,
                label=_render(messages, MOVE_TO_SHARED_SUGGESTION, values),
                patch=GraphPatch(),
            )
        ],
    )


def _info(
    code: str,
    messages: Mapping[str, str] | None,
    source: ScopedDefinition | None = None,
    severity: IssueSeverity = "info",
) -> Issue:
    if source is None:
        return Issue(severity=severity, code=code, message=_render(messages, code, {}))
    return Issue(
        severity=severity,
        code=code,
        message=_render(messages, code, _values(source, None)),
        path="/project",
        details=_scope_detail(source),
    )


def _unique_refs(d: ScopedDefinition, references: References) -> list[DefinitionId]:
    if d.document is None:
        return []
    seen: dict[DefinitionId, None] = {}
    for kind, ref_id in references(d.kind, d.document):
        key = (kind, ref_id)
        if key != d.key:
            seen.setdefault(key, None)
    return list(seen)


def _find(
    defs: Sequence[ScopedDefinition],
    known: Collection[str] | None,
    references: References | None,
    messages: Mapping[str, str] | None,
) -> list[_Found]:
    index = {d.key: d for d in defs}
    out: list[_Found] = []
    if known is not None:
        for d in defs:
            if d.project is not None and d.project not in known:
                out.append(_Found(_info(CODE_UNKNOWN, messages, d), d.key, None))
    if references is None:
        out.append(_Found(_info(CODE_REFERENCES_UNAVAILABLE, messages), ("", ""), None))
        return out
    for d in defs:
        mine = effective_scope(d.project, known)
        for key in _unique_refs(d, references):
            ref = index.get(key)
            if ref is None:
                continue  # 없는 참조는 다른 검사(그래프 검증 등)의 몫이다.
            theirs = effective_scope(ref.project, known)
            if theirs is None or theirs == mine:
                continue
            code = CODE_SHARED_USES_PROJECT if mine is None else CODE_CROSS_PROJECT
            out.append(_Found(_ref_issue(code, d, ref, messages), d.key, ref.key))
    return out


def scope_issues(
    defs: Iterable[ScopedDefinition],
    projects: Iterable[str | Project | Mapping[str, Any]] | None,
    *,
    references: References | None,
    messages: Mapping[str, str] | None = None,
) -> list[Issue]:
    """정의 목록의 프로젝트 범위 이슈(경고·정보, 저장·실행을 막지 않음).

    Args:
        defs: 검사할 정의(참조를 따라갈 정의는 `document`가 있어야 한다). 참조 대상도 이 목록에서
            찾는다(목록에 없는 대상은 건너뛴다).
        projects: 있는 프로젝트(id·`Project`·dict). ``None``이면 존재를 따지지 않는다.
        references: 참조 추출(주입). ``None``이면 참조 규칙 대신 `project.references_unavailable`
            정보 하나를 낸다.
        messages: 문구 바꾸기(`DEFAULT_MESSAGES`와 같은 키).

    Returns:
        `project.unknown`(info) → 참조 규칙(`project.shared_uses_project`·`project.cross_project`,
        warning, 제안 [공용으로 옮기기]) 순서. 같은 (참조하는 쪽, 참조 대상) 쌍은 한 번만.
    """
    known = None if projects is None else known_project_ids(projects)
    return [f.issue for f in _find(list(defs), known, references, messages)]


# ---------------------------------------------------------------- 옮기기·삭제 계획


def _key_of(target: DefinitionKey | ScopedDefinition | tuple[str, str]) -> DefinitionId:
    if isinstance(target, tuple):
        return target
    return (target.kind, target.id)


def _move(d: ScopedDefinition, to: str | None, *, required: bool) -> DefinitionMove:
    return DefinitionMove.model_validate(
        {
            "kind": d.kind,
            "id": d.id,
            "name": d.name,
            "from": d.project,
            "to": to,
            "required": required,
        }
    )


def move_plan(
    target: DefinitionKey | ScopedDefinition | tuple[str, str],
    to: str | None,
    defs: Iterable[ScopedDefinition],
    *,
    references: References | None,
    projects: Iterable[str | Project | Mapping[str, Any]] | None = None,
    messages: Mapping[str, str] | None = None,
) -> MovePlan:
    """정의 하나를 범위 `to`로 옮길 때의 계획(저장하지 않음, design §UX-P.2).

    - 첫 항목 = 옮기려는 정의(`required=True`). 이미 그 범위면 `moves`가 비어 있다.
    - 프로젝트 P 전용 → 공용: 그 정의가 (참조를 따라) 쓰는 P 전용 정의 전부(참조 닫힘)를
      `required=False`로 더한다(화면은 [함께 옮기기]를 기본 선택).
    - `warnings`: 모든 `moves`를 적용했다고 보고 다시 검사했을 때, 옮기는 정의가 참조하거나
      참조되는 범위 이슈(예: 공용 → P 전용이면 그 정의를 쓰는 공용·다른 프로젝트 정의). 막지 않는다.

    Args:
        target: 옮길 정의(키·`ScopedDefinition`·(종류, id)).
        to: 옮길 범위(프로젝트 id, ``None`` = 공용).
        defs: 전체 정의(참조 대상·참조하는 쪽을 여기서 찾는다).
        references: 참조 추출(주입). ``None``이면 옮기려는 정의만 넣고 정보 이슈를 단다.
        projects: 있는 프로젝트. ``None``이면 존재를 따지지 않는다.
        messages: 문구 바꾸기.

    Raises:
        UnknownDefinitionError: `target`이 `defs`에 없을 때.
    """
    items = list(defs)
    index = {d.key: d for d in items}
    key = _key_of(target)
    origin = index.get(key)
    if origin is None:
        raise UnknownDefinitionError(f"정의를 찾을 수 없습니다: {key[0]}/{key[1]}")
    known = None if projects is None else known_project_ids(projects)
    target_key = origin.to_key()
    if origin.project == to:
        return MovePlan(target=target_key, to=to)
    moves = [_move(origin, to, required=True)]
    if references is None:
        return MovePlan(
            target=target_key,
            to=to,
            moves=moves,
            warnings=[_info(CODE_REFERENCES_UNAVAILABLE, messages)],
        )
    if to is None and origin.project is not None:
        seen = {origin.key}
        queue = [origin]
        while queue:
            cur = queue.pop(0)
            for ref_key in _unique_refs(cur, references):
                ref = index.get(ref_key)
                if ref is None or ref.key in seen or ref.project != origin.project:
                    continue
                seen.add(ref.key)
                moves.append(_move(ref, None, required=False))
                queue.append(ref)
    moved = {(m.kind, m.id): m.to for m in moves}
    after = [replace(d, project=moved[d.key]) if d.key in moved else d for d in items]
    warnings = [
        f.issue
        for f in _find(after, known, references, messages)
        if f.source in moved or (f.ref is not None and f.ref in moved)
    ]
    return MovePlan(target=target_key, to=to, moves=moves, warnings=warnings)


def delete_plan(project_id: str, defs: Iterable[ScopedDefinition]) -> DeletePlan:
    """프로젝트를 지울 때 영향받는 정의(그 프로젝트 전용 정의, 저장하지 않음).

    기본 처리는 공용으로 옮기기(`move_to_shared`)다. 실행·대화의 `project_id`는 그대로 남는다.
    """
    return DeletePlan(
        project_id=project_id,
        definitions=[d.to_key() for d in defs if d.project == project_id],
    )

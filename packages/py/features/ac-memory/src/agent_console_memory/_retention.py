"""정리 규칙(design §5.7R.1.4): 조건(`ConditionSpec`, X22) → 보관·표시 삭제.

규칙은 전부 사용자 데이터다. 패키지 기본 규칙은 없다(빈 규칙 = 계획 0건, 아무것도 정리하지 않음).

- 판단 대상(subject)은 항목 하나를 JSON 객체로 본 것이다(`RETENTION_SUBJECT_FIELDS`):
  `scope{kind, id}`·`key`·`tags`·`pinned`·`archived`·`bytes`·`version`·`age_days`(만든 뒤)·
  `idle_days`(마지막 쓰기 뒤)·`last_read_days`(도구로 읽은 기록이 있을 때만 키가 있다)·
  `author_kind`(마지막으로 쓴 주체 종류)·`created_by`·`updated_by`(쓴 주체 객체). 일 수는 실수다.
- 고정(`pinned`) 항목은 정리하지 않는다(규칙에 맞으면 계획의 `excluded_pinned`로만 센다).
  지운 항목은 판단하지 않는다.
- 계획 항목에는 판단한 때의 마지막 쓰기 시각·본문 크기(`updated_at`·`bytes`)를 싣는다(화면이 목록을
  다시 읽지 않게).
- 여러 규칙이 맞으면 선언 순서의 첫 규칙 하나만 쓴다. 그 규칙의 동작이 이미 된 상태(보관된 항목을
  보관)면 계획에 넣지 않는다(뒤 규칙도 보지 않는다).
- 조건은 `ac-conditions` 컴파일 경로(`compile_conditions`)로 판정하고, 규칙이 읽는 판단 대상 키만
  만든다(`condition_keys`). 판정 결과를 값별로 기억하지는 않는다 — 컴파일한 항목 판정이 기억
  찾기(열쇠 만들기 + 사전 찾기)보다 싸다(측정, design §5.7R.10 `[5.7R.10 구현·측정]`).
- 적용은 계획을 만든 때의 버전으로만 바꾼다(`if_version`). 그 사이 바뀌었거나 고정됐으면 건너뛴다.
  적용 결과는 버전(쓴 주체 `system`, `label` = 규칙 id)으로 남아 되돌릴 수 있다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from operator import attrgetter
from typing import Any, Final

from pydantic import ValidationError

from agent_console_conditions import (
    CompiledConditions,
    ConditionIssueCodes,
    ConditionOperator,
    compile_conditions,
    condition_issues,
    condition_keys,
)
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.definitions import Issue
from agent_console_contracts.memory import (
    KnownMemoryAuthorKinds,
    MemoryAuthor,
    MemoryRetentionPlan,
    MemoryRetentionPlanItem,
    MemoryRetentionResult,
    MemoryRetentionRule,
    MemoryScopeRef,
)

from ._errors import EntryNotFoundError, VersionConflictError
from ._scan import DEFAULT_SCAN_PAGE, ScannedEntry, SearchableStore, iter_entries
from ._store import MemoryStore

SECONDS_PER_DAY: Final = 86_400.0

DEFAULT_RULES_PATH: Final = "/retention/rules"
"""규칙 검사 이슈 경로의 기본 앞부분(사용자 설정 섹션 `memory` 기준)."""

type RetentionRuleInput = MemoryRetentionRule | Mapping[str, Any]
"""규칙 하나: 계약 모델 또는 같은 모양의 JSON 객체(저장 전 시험 규칙)."""


def _days(now: float, then: float) -> float:
    gap = now - then
    return gap / SECONDS_PER_DAY if gap > 0 else 0.0


def _author(author: Any) -> dict[str, Any]:
    data: dict[str, Any] = author.model_dump(mode="json")
    return data


_ABSENT: Final = object()

_SUBJECT: Final[dict[str, Callable[[ScannedEntry, float], Any]]] = {
    "scope": lambda e, _now: {"kind": e.scope.kind, "id": e.scope.id},
    "key": lambda e, _now: e.key,
    "tags": lambda e, _now: list(e.tags),
    "pinned": lambda e, _now: e.pinned,
    "archived": lambda e, _now: e.archived,
    "bytes": lambda e, _now: e.bytes,
    "version": lambda e, _now: e.version,
    "age_days": lambda e, now: _days(now, e.created_at),
    "idle_days": lambda e, now: _days(now, e.updated_at),
    "last_read_days": lambda e, now: (
        _ABSENT if e.last_read_at is None else _days(now, e.last_read_at)
    ),
    "author_kind": lambda e, _now: e.updated_by.kind,
    "created_by": lambda e, _now: _author(e.created_by),
    "updated_by": lambda e, _now: _author(e.updated_by),
}

_PLAIN: Final = ("key", "pinned", "archived", "bytes", "version")
"""항목 속성 값을 그대로 쓰는 키(한 번에 꺼낸다 — `attrgetter`)."""

RETENTION_SUBJECT_FIELDS: Final[tuple[str, ...]] = tuple(_SUBJECT)
"""판단 대상의 최상위 키(설정 화면의 경로 예 `examples` 재료)."""


def retention_subject(
    entry: ScannedEntry, *, now: float, keys: frozenset[str] | None = None
) -> dict[str, Any]:
    """항목 → 판단 대상(JSON 객체).

    Args:
        entry: 항목(요약·본문 포함 항목·머리 `EntryHead` — 본문은 보지 않는다).
        now: 지금(Unix epoch 초). 일 수 계산 기준.
        keys: 만들 키(None = 전부). 모르는 키는 무시한다.

    Returns:
        판단 대상. `last_read_days`는 읽은 기록이 있을 때만 있다.

    >>> from agent_console_memory.testing import sample_entry_summary
    >>> subject = retention_subject(sample_entry_summary(), now=86_400.0 * 3)
    >>> subject["idle_days"], "last_read_days" in subject
    (3.0, False)
    >>> sorted(retention_subject(sample_entry_summary(), now=0, keys=frozenset({"tags"})))
    ['tags']
    """
    return _subject_builder(keys)(entry, now)


def _subject_builder(
    keys: frozenset[str] | None,
) -> Callable[[ScannedEntry, float], dict[str, Any]]:
    """`keys`만 만드는 판단 대상 함수(키 고르기를 항목마다 하지 않게 한 번만).

    키 순서는 `_SUBJECT` 순서와 같다(그대로 쓰는 속성을 먼저 한 번에 꺼낸 뒤 다시 줄 세우지는
    않는다 — 판단 대상은 JSON 객체라 키 순서에 뜻이 없다).
    """
    wanted = [k for k in _SUBJECT if keys is None or k in keys]
    plain = tuple(k for k in wanted if k in _PLAIN)
    getters = tuple((k, _SUBJECT[k]) for k in wanted if k not in _PLAIN)
    pick = attrgetter(*plain) if len(plain) > 1 else None
    single = plain[0] if len(plain) == 1 else None

    def build(entry: ScannedEntry, now: float) -> dict[str, Any]:
        if pick is not None:
            out: dict[str, Any] = dict(zip(plain, pick(entry), strict=True))
        elif single is not None:
            out = {single: getattr(entry, single)}
        else:
            out = {}
        for name, get in getters:
            value = get(entry, now)
            if value is not _ABSENT:
                out[name] = value
        return out

    return build


@dataclass(frozen=True, slots=True)
class CompiledRetentionRule:
    """검사를 통과해 컴파일한 규칙 하나."""

    rule: MemoryRetentionRule
    holds: CompiledConditions


@dataclass(frozen=True, slots=True)
class RetentionRuleSet:
    """컴파일한 규칙 묶음(`compile_retention_rules`).

    Attributes:
        rules: 쓸 수 있는 규칙(선언 순서). 오류가 있는 규칙은 빠진다.
        issues: 규칙 검사 이슈(경고 포함).
        keys: 규칙들이 읽는 판단 대상 키(None = 전부).
    """

    rules: tuple[CompiledRetentionRule, ...]
    issues: tuple[Issue, ...]
    keys: frozenset[str] | None


def _rule_issue(path: str, message: str, **details: Any) -> Issue:
    return Issue(
        severity="error",
        code=KnownIssueCodes.MEMORY_SETTINGS_INVALID,
        message=message,
        path=path,
        details=details,
    )


def _validation_issues(exc: ValidationError, where: str) -> list[Issue]:
    out: list[Issue] = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = "".join(f"/{part}" for part in err.get("loc", ()))
        out.append(_rule_issue(f"{where}{loc}", f"정리 규칙 형식이 틀렸다: {err.get('msg', '')}"))
    return out


def compile_retention_rules(
    rules: Sequence[RetentionRuleInput],
    operators: Mapping[str, ConditionOperator],
    *,
    base_path: str = DEFAULT_RULES_PATH,
) -> RetentionRuleSet:
    """정리 규칙을 검사하고 컴파일한다.

    검사: 규칙 형식(`memory.settings_invalid`), 겹치는 규칙 id(뒤의 것이 빠짐, error), 조건
    검사(`condition_issues` — 모르는 연산자 warning, 값 오류 error). 조건이 비면(항상 참) 정리에서는
    모든 항목을 고르게 되므로 **error**로 올리고 그 규칙을 뺀다.

    Args:
        rules: 규칙 목록(모델 또는 JSON 객체).
        operators: 조건 연산자 id → 연산자.
        base_path: 이슈 경로 앞부분(기본 `/retention/rules`, 규칙 i의 조건은 `<base>/<i>/when`).

    Returns:
        `RetentionRuleSet`. error 이슈가 있는 규칙은 `rules`에서 빠진다.
    """
    compiled: list[CompiledRetentionRule] = []
    issues: list[Issue] = []
    seen: set[str] = set()
    keys: set[str] | None = set()
    for index, raw in enumerate(rules):
        where = f"{base_path}/{index}"
        if isinstance(raw, MemoryRetentionRule):
            rule = raw
        else:
            try:
                rule = MemoryRetentionRule.model_validate(raw)
            except ValidationError as exc:
                issues.extend(_validation_issues(exc, where))
                continue
        if rule.id in seen:
            issues.append(_rule_issue(f"{where}/id", "같은 규칙 id가 앞에 있다", rule=rule.id))
            continue
        seen.add(rule.id)
        found = condition_issues(rule.when, operators, base_path=f"{where}/when")
        found = [
            issue.model_copy(update={"severity": "error"})
            if issue.code == ConditionIssueCodes.EMPTY
            else issue
            for issue in found
        ]
        issues.extend(found)
        if any(issue.severity == "error" for issue in found):
            continue
        compiled.append(CompiledRetentionRule(rule, compile_conditions(rule.when, operators)))
        rule_keys = condition_keys(rule.when)
        if rule_keys is None or keys is None:
            keys = None
        else:
            keys |= rule_keys
    return RetentionRuleSet(
        rules=tuple(compiled),
        issues=tuple(issues),
        keys=None if keys is None else frozenset(keys),
    )


def retention_issues(
    rules: Sequence[RetentionRuleInput],
    operators: Mapping[str, ConditionOperator],
    *,
    base_path: str = DEFAULT_RULES_PATH,
) -> list[Issue]:
    """규칙 검사 이슈만(설정 저장 전 검사). `compile_retention_rules(...).issues`와 같다."""
    return list(compile_retention_rules(rules, operators, base_path=base_path).issues)


def _no_op(entry: ScannedEntry, action: str) -> bool:
    return action == "archive" and entry.archived


def retention_plan(
    store: SearchableStore,
    rules: Sequence[RetentionRuleInput] | RetentionRuleSet,
    *,
    now: float,
    operators: Mapping[str, ConditionOperator] | None = None,
    limit: int | None = None,
    scopes: Sequence[MemoryScopeRef] | None = None,
    page_size: int = DEFAULT_SCAN_PAGE,
) -> MemoryRetentionPlan:
    """정리 미리보기(dry run): 어느 항목에 어느 규칙이 무엇을 할지. 저장소를 바꾸지 않는다.

    Args:
        store: 저장소(`search`, 선택 능력 `scan_heads`·`scan_entries` — `iter_entries`).
        rules: 규칙 목록 또는 미리 컴파일한 `RetentionRuleSet`. 빈 목록이면 계획 0건.
        now: 지금(Unix epoch 초).
        operators: 조건 연산자(규칙 목록을 줄 때 필요).
        limit: `items` 최대 수(None = 전부). `count`는 늘 전체 수.
        scopes: 판단할 범위(None = 모든 범위).
        page_size: 저장소에서 한 번에 읽는 수.

    Returns:
        `MemoryRetentionPlan`(항목 순서는 저장소가 낸 순서 — `iter_entries`). 규칙에 맞은 고정
        항목은 `items`·`count`에 넣지 않고 `excluded_pinned`로 센다.

    Raises:
        ValueError: 규칙 목록을 주면서 `operators`가 없을 때.
    """
    if isinstance(rules, RetentionRuleSet):
        rule_set = rules
    else:
        if operators is None:
            raise ValueError("규칙 목록을 줄 때는 operators가 필요하다")
        rule_set = compile_retention_rules(rules, operators)
    items: list[MemoryRetentionPlanItem] = []
    count = 0
    pinned = 0
    compiled = rule_set.rules
    if compiled:
        subject_of = _subject_builder(rule_set.keys)
        for entry in iter_entries(store, scopes=scopes, page_size=page_size, with_content=False):
            subject = subject_of(entry, now)
            for candidate in compiled:
                if not candidate.holds.predicate(subject):
                    continue
                action = candidate.rule.action
                if _no_op(entry, action):
                    break
                if entry.pinned:
                    pinned += 1
                    break
                count += 1
                if limit is None or len(items) < limit:
                    items.append(
                        MemoryRetentionPlanItem(
                            entry_id=entry.id,
                            scope=entry.scope,
                            key=entry.key,
                            version=entry.version,
                            rule=candidate.rule.id,
                            action=action,
                            updated_at=entry.updated_at,
                            bytes=entry.bytes,
                        )
                    )
                break
    return MemoryRetentionPlan(
        items=items,
        count=count,
        truncated=count > len(items),
        excluded_pinned=pinned,
        issues=list(rule_set.issues),
    )


def retention_author(rule_id: str) -> MemoryAuthor:
    """정리 적용 버전의 쓴 주체(`system`, `label` = 규칙 id).

    >>> retention_author("stale").model_dump(exclude_defaults=True)
    {'kind': 'system', 'label': 'stale'}
    """
    return MemoryAuthor(kind=KnownMemoryAuthorKinds.SYSTEM, label=rule_id)


def apply_retention(
    store: MemoryStore,
    plan: MemoryRetentionPlan | Sequence[MemoryRetentionPlanItem],
) -> MemoryRetentionResult:
    """계획을 적용한다(보관·표시 삭제). 계획 뒤 바뀐(버전 다름·고정됨·없어짐) 항목은 건너뛴다.

    Args:
        store: 저장소.
        plan: `retention_plan` 결과(잘리지 않은 것) 또는 항목 목록.

    Returns:
        `MemoryRetentionResult`(계획의 이슈를 그대로 싣는다).

    Raises:
        ValueError: `limit`으로 잘린 계획(일부만 정리하게 되므로 받지 않는다).
    """
    if isinstance(plan, MemoryRetentionPlan):
        if plan.truncated:
            raise ValueError("잘린 계획은 적용하지 않는다(limit 없이 다시 계획한다)")
        items: Sequence[MemoryRetentionPlanItem] = plan.items
        issues = list(plan.issues)
    else:
        items, issues = plan, []
    archived = deleted = skipped = 0
    for item in items:
        current = store.get(item.entry_id)
        if current is None or current.pinned or current.version != item.version:
            skipped += 1
            continue
        author = retention_author(item.rule)
        try:
            if item.action == "archive":
                if current.archived:
                    skipped += 1
                    continue
                store.archive(item.entry_id, author=author, if_version=item.version)
                archived += 1
            else:
                store.delete(item.entry_id, author=author, if_version=item.version)
                deleted += 1
        except (VersionConflictError, EntryNotFoundError):
            skipped += 1
    return MemoryRetentionResult(archived=archived, deleted=deleted, skipped=skipped, issues=issues)

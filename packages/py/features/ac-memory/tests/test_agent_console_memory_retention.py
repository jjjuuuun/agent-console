"""정리 규칙(design §5.7R.1.4, 5.7R.11).

빈 규칙 = 계획 0건, 규칙 조합·첫 규칙·고정 제외, 적용·되돌리기.
"""

from __future__ import annotations

import doctest
from importlib.resources import files
from types import ModuleType
from typing import Any

import pytest

from agent_console_conditions import ConditionOperator, builtin_operators
from agent_console_contracts.memory import (
    MemoryRetentionPlan,
    MemoryRetentionRule,
    MemoryRetentionSettings,
    MemoryScopeRef,
    MemorySettings,
)
from agent_console_memory import (
    RETENTION_SUBJECT_FIELDS,
    InMemoryMemoryStore,
    _retention,
    apply_retention,
    compile_retention_rules,
    retention_issues,
    retention_plan,
    retention_subject,
)
from agent_console_memory.testing import FakeClock, sample_entry_summary, user_author

DAY = 86_400.0
OPS: dict[str, ConditionOperator] = {op.descriptor.id: op for op in builtin_operators()}
NOTES = MemoryScopeRef(kind="notes", id="g1")
BOARD = MemoryScopeRef(kind="board", id="")


def _rule(rule_id: str, action: str, *items: dict[str, Any]) -> dict[str, Any]:
    return {"id": rule_id, "action": action, "when": {"all": list(items)}}


TEMP_OLD = _rule(
    "stale-temp",
    "archive",
    {"path": "/tags", "op": "contains", "value": "tmp"},
    {"path": "/idle_days", "op": "gte", "value": 30},
)
ARCHIVED_OLD = _rule(
    "drop-archived",
    "delete",
    {"path": "/archived", "op": "eq", "value": True},
    {"path": "/idle_days", "op": "gte", "value": 60},
)


def _store() -> tuple[InMemoryMemoryStore, FakeClock]:
    clock = FakeClock(0.0)
    return InMemoryMemoryStore(clock=clock), clock


def _write(
    store: InMemoryMemoryStore, key: str, *, scope: MemoryScopeRef = NOTES, **kw: Any
) -> str:
    return store.write(scope, key, f"본문 {key}", author=user_author(), **kw).entry.id


def _plan_keys(plan: MemoryRetentionPlan) -> list[tuple[str, str, str]]:
    return sorted((item.key, item.rule, item.action) for item in plan.items)


# ---- 빈 규칙·기본 데이터 없음 -------------------------------------------------------------------


def test_empty_rules_plan_nothing_and_no_default_rules_exist() -> None:
    store, clock = _store()
    for i in range(5):
        _write(store, f"k{i}", tags=["tmp"])
    clock.advance(1_000 * DAY)
    plan = retention_plan(store, [], now=clock(), operators=OPS)
    assert plan == MemoryRetentionPlan(items=[], count=0, truncated=False, issues=[])
    assert apply_retention(store, plan).model_dump() == {
        "archived": 0,
        "deleted": 0,
        "skipped": 0,
        "issues": [],
    }
    # 기본 데이터: 설정 기본값도 빈 목록이고, 패키지 데이터에 정리 규칙 파일이 없다.
    assert MemoryRetentionSettings().rules == []
    assert MemorySettings().retention.rules == []
    data_files = [p.name for p in files("agent_console_memory").joinpath("data").iterdir()]
    assert not [name for name in data_files if "retention" in name or "rule" in name]


# ---- 계획 ------------------------------------------------------------------------------------


def test_rules_combine_first_match_wins_and_pinned_is_skipped() -> None:
    store, clock = _store()
    _write(store, "a-temp-old", tags=["tmp"])
    _write(store, "b-pinned", tags=["tmp"], pinned=True)
    _write(store, "c-keep-old")
    archived_id = _write(store, "d-archived-old", tags=["tmp"])
    store.archive(archived_id, author=user_author())
    clock.advance(70 * DAY)
    _write(store, "e-temp-new", tags=["tmp"])
    clock.advance(1 * DAY)

    plan = retention_plan(store, [TEMP_OLD, ARCHIVED_OLD], now=clock(), operators=OPS)

    # d는 첫 규칙(보관)에도 맞지만 이미 보관됨 → 첫 맞는 규칙에서 멈추고 계획에 없다.
    assert _plan_keys(plan) == [("a-temp-old", "stale-temp", "archive")]
    assert plan.count == 1
    assert plan.issues == []

    # 규칙 순서를 바꾸면 d가 삭제 규칙에 먼저 걸린다.
    swapped = retention_plan(store, [ARCHIVED_OLD, TEMP_OLD], now=clock(), operators=OPS)
    assert _plan_keys(swapped) == [
        ("a-temp-old", "stale-temp", "archive"),
        ("d-archived-old", "drop-archived", "delete"),
    ]


def test_plan_items_carry_version_and_scope_and_honour_scope_filter() -> None:
    store, clock = _store()
    _write(store, "x", tags=["tmp"])
    _write(store, "y", scope=BOARD, tags=["tmp"])
    clock.advance(40 * DAY)
    plan = retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS)
    assert {(i.scope.kind, i.key, i.version) for i in plan.items} == {
        ("notes", "x", 1),
        ("board", "y", 1),
    }
    only = retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS, scopes=[BOARD])
    assert [i.key for i in only.items] == ["y"]


def test_limit_truncates_items_but_counts_all() -> None:
    store, clock = _store()
    for i in range(7):
        _write(store, f"k{i}", tags=["tmp"])
    clock.advance(31 * DAY)
    plan = retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS, limit=3)
    assert (len(plan.items), plan.count, plan.truncated) == (3, 7, True)
    with pytest.raises(ValueError, match="잘린"):
        apply_retention(store, plan)


def test_subject_fields_cover_design_list() -> None:
    assert set(RETENTION_SUBJECT_FIELDS) == {
        "scope",
        "key",
        "tags",
        "pinned",
        "archived",
        "bytes",
        "version",
        "age_days",
        "idle_days",
        "last_read_days",
        "author_kind",
        "created_by",
        "updated_by",
    }
    entry = sample_entry_summary(created_at=0.0, updated_at=DAY, last_read_at=2 * DAY)
    subject = retention_subject(entry, now=4 * DAY)
    assert subject["scope"] == {"kind": "sample", "id": "s1"}
    assert (subject["age_days"], subject["idle_days"], subject["last_read_days"]) == (4, 3, 2)
    assert subject["author_kind"] == "user"
    assert subject["created_by"]["kind"] == "user"
    assert "last_read_days" not in retention_subject(sample_entry_summary(), now=DAY)
    # 미래 시각(시계 차이)은 0일로 본다.
    assert retention_subject(sample_entry_summary(updated_at=9 * DAY), now=DAY)["idle_days"] == 0


def test_last_read_days_only_after_tool_read() -> None:
    store, clock = _store()
    read_id = _write(store, "read")
    _write(store, "never")
    clock.advance(10 * DAY)
    store.mark_read(read_id)
    clock.advance(5 * DAY)
    rule = _rule("cold", "archive", {"path": "/last_read_days", "op": "gte", "value": 5})
    never = {
        "id": "never-read",
        "action": "archive",
        "when": {"all": [{"path": "/last_read_days", "op": "exists"}], "negate": True},
    }
    plan = retention_plan(store, [rule, never], now=clock(), operators=OPS)
    assert _plan_keys(plan) == [("never", "never-read", "archive"), ("read", "cold", "archive")]


def test_conditions_on_authors_and_nested_paths() -> None:
    store, clock = _store()
    store.write(NOTES, "by-system", "x", author=user_author().model_copy(update={"kind": "system"}))
    _write(store, "by-user")
    rule = _rule("sys", "delete", {"path": "/updated_by/kind", "op": "eq", "value": "system"})
    by_kind = _rule("sys2", "delete", {"path": "/author_kind", "op": "eq", "value": "system"})
    in_scope = _rule("scope", "archive", {"path": "/scope/kind", "op": "eq", "value": "notes"})
    assert _plan_keys(retention_plan(store, [rule], now=clock(), operators=OPS)) == [
        ("by-system", "sys", "delete")
    ]
    assert [i.key for i in retention_plan(store, [by_kind], now=clock(), operators=OPS).items] == [
        "by-system"
    ]
    assert retention_plan(store, [in_scope], now=clock(), operators=OPS).count == 2


def test_rule_list_needs_operators_and_accepts_compiled_set() -> None:
    store, clock = _store()
    with pytest.raises(ValueError, match="operators"):
        retention_plan(store, [TEMP_OLD], now=clock())
    compiled = compile_retention_rules([TEMP_OLD], OPS)
    assert compiled.keys == frozenset({"tags", "idle_days"})
    assert retention_plan(store, compiled, now=clock()).count == 0


# ---- 규칙 검사 --------------------------------------------------------------------------------


def test_rule_issues_shape_duplicate_empty_unknown_and_bad_value() -> None:
    rules: list[dict[str, Any]] = [
        {"id": "no-when"},  # 형식 오류
        TEMP_OLD,
        {**TEMP_OLD, "action": "delete"},  # 같은 id
        {"id": "empty", "when": {}},  # 빈 조건 → 정리에서는 error
        _rule("unknown-op", "archive", {"path": "/key", "op": "no-such-op", "value": 1}),
        _rule("bad-value", "archive", {"path": "/key", "op": "matches", "value": "("}),
    ]
    compiled = compile_retention_rules(rules, OPS, base_path="/rules")
    by_path = {(i.path, i.severity, i.code) for i in compiled.issues}
    assert ("/rules/0/when", "error", "memory.settings_invalid") in by_path
    assert ("/rules/2/id", "error", "memory.settings_invalid") in by_path
    assert ("/rules/3/when", "error", "condition.empty") in by_path
    assert ("/rules/4/when/all/0/op", "warning", "condition.unknown_operator") in by_path
    assert any(p == "/rules/5/when/all/0/value" and s == "error" for p, s, _c in by_path), by_path
    # 오류가 있는 규칙은 빠지고, 경고만 있는 규칙(모르는 연산자 = 늘 거짓)은 남는다.
    assert [c.rule.id for c in compiled.rules] == ["stale-temp", "unknown-op"]
    assert retention_issues(rules, OPS, base_path="/rules") == list(compiled.issues)
    # 기본 경로는 설정 섹션 기준.
    assert retention_issues([{"id": "x"}], OPS)[0].path == "/retention/rules/0/when"


def test_invalid_rules_never_select_entries() -> None:
    store, clock = _store()
    _write(store, "k")
    plan = retention_plan(store, [{"id": "all", "when": {}}], now=clock(), operators=OPS)
    assert plan.count == 0
    assert [i.code for i in plan.issues] == ["condition.empty"]
    applied = apply_retention(store, plan)
    assert [i.code for i in applied.issues] == ["condition.empty"]


def test_model_rules_are_accepted_as_is() -> None:
    store, clock = _store()
    _write(store, "k", tags=["tmp"])
    clock.advance(31 * DAY)
    rule = MemoryRetentionRule.model_validate(TEMP_OLD)
    assert retention_plan(store, [rule], now=clock(), operators=OPS).count == 1


# ---- 적용·되돌리기 -----------------------------------------------------------------------------


def test_apply_records_system_versions_and_can_be_undone() -> None:
    store, clock = _store()
    temp_id = _write(store, "temp", tags=["tmp"])
    old_id = _write(store, "old")
    store.archive(old_id, author=user_author())
    clock.advance(90 * DAY)
    plan = retention_plan(store, [TEMP_OLD, ARCHIVED_OLD], now=clock(), operators=OPS)
    result = apply_retention(store, plan)
    assert (result.archived, result.deleted, result.skipped) == (1, 1, 0)

    temp = store.get(temp_id)
    assert temp is not None
    assert temp.archived
    assert temp.updated_by.kind == "system"
    assert temp.updated_by.label == "stale-temp"
    assert store.get(old_id) is None
    last = store.history(old_id)[-1]
    assert (last.op, last.author.kind, last.author.label) == ("delete", "system", "drop-archived")

    # 되돌리기: 보관 풀기·되살리기. 본문은 그대로다.
    store.archive(temp_id, author=user_author(), archived=False)
    restored = store.restore(old_id, author=user_author())
    assert restored.content == "본문 old"
    assert restored.deleted_at is None
    again = store.get(temp_id)
    assert again is not None
    assert not again.archived
    assert again.content == "본문 temp"


def test_apply_skips_entries_changed_after_plan() -> None:
    store, clock = _store()
    ids = {key: _write(store, key, tags=["tmp"]) for key in ("edited", "pinned", "gone", "ok")}
    clock.advance(31 * DAY)
    plan = retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS)
    assert plan.count == 4
    store.update(ids["edited"], author=user_author(), content="새 본문")
    store.update(ids["pinned"], author=user_author(), pinned=True)
    store.purge(ids["gone"])
    result = apply_retention(store, plan)
    assert (result.archived, result.skipped) == (1, 3)
    edited = store.get(ids["edited"])
    assert edited is not None
    assert not edited.archived


def test_apply_accepts_item_list() -> None:
    store, clock = _store()
    _write(store, "k", tags=["tmp"])
    clock.advance(31 * DAY)
    plan = retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS)
    assert apply_retention(store, plan.items).archived == 1
    # 두 번 적용하면 버전이 달라 건너뛴다.
    assert apply_retention(store, plan.items).skipped == 1


def test_rule_names_are_data_renamed_tags_and_scopes_give_same_plan() -> None:
    def scenario(tag: str, kind: str) -> list[tuple[str, str, str]]:
        store, clock = _store()
        scope = MemoryScopeRef(kind=kind, id="x")
        _write(store, "a", scope=scope, tags=[tag])
        _write(store, "b", scope=scope)
        clock.advance(31 * DAY)
        rule = _rule(
            "r",
            "archive",
            {"path": "/tags", "op": "contains", "value": tag},
            {"path": "/scope/kind", "op": "eq", "value": kind},
        )
        return _plan_keys(retention_plan(store, [rule], now=clock(), operators=OPS))

    assert scenario("tmp", "notes") == scenario("임시", "journal") == [("a", "r", "archive")]


@pytest.mark.parametrize("module", [_retention])
def test_module_doctests(module: ModuleType) -> None:
    result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
    assert result.attempted > 0
    assert result.failed == 0


class _SearchOnly:
    def __init__(self, store: InMemoryMemoryStore) -> None:
        self.search = store.search


def test_plan_is_the_same_with_and_without_entry_scanner() -> None:
    store, clock = _store()
    for i in range(30):
        _write(store, f"k{i}", tags=["tmp"] if i % 2 else [], pinned=i % 7 == 0)
        clock.advance(DAY)
    rules = [TEMP_OLD, ARCHIVED_OLD]
    fast = retention_plan(store, rules, now=clock() + 20 * DAY, operators=OPS)
    slow = retention_plan(
        _SearchOnly(store), rules, now=clock() + 20 * DAY, operators=OPS, page_size=4
    )
    assert fast.count == slow.count > 0
    assert sorted(fast.items, key=lambda i: i.key) == sorted(slow.items, key=lambda i: i.key)


# ---- 5.7R.28: 계획 항목 상세·고정 제외 수·판단 대상 경로 제안 -----------------------------


def test_plan_items_carry_updated_at_and_bytes_and_count_excluded_pinned() -> None:
    store, clock = _store()
    kept = store.write(NOTES, "a", "본문 가", author=user_author(), tags=["tmp"]).entry
    p1 = _write(store, "p1", tags=["tmp"], pinned=True)
    _write(store, "p2", tags=["tmp"], pinned=True)
    _write(store, "p-other", pinned=True)  # 규칙에 맞지 않는 고정 항목은 세지 않는다
    clock.advance(40 * DAY)

    plan = retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS)

    [item] = plan.items
    assert (item.key, item.updated_at, item.bytes) == ("a", kept.updated_at, kept.bytes)
    assert item.bytes == len("본문 가".encode())
    assert (plan.count, plan.excluded_pinned) == (1, 2)
    # 잘라도 고정 제외 수는 전체 기준이다.
    cut = retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS, limit=1)
    assert cut.excluded_pinned == 2
    # 적용은 고정 항목을 건드리지 않는다.
    assert apply_retention(store, plan).archived == 1
    assert store.get(kept.id).archived  # type: ignore[union-attr]
    assert not store.get(p1).archived  # type: ignore[union-attr]


def test_excluded_pinned_is_zero_without_rules_or_when_already_done() -> None:
    store, clock = _store()
    pid = _write(store, "p", tags=["tmp"], pinned=True)
    store.archive(pid, author=user_author())
    clock.advance(40 * DAY)
    assert retention_plan(store, [], now=clock(), operators=OPS).excluded_pinned == 0
    # 이미 보관된 고정 항목에 보관 규칙: 할 일이 없으니 제외로도 세지 않는다.
    assert retention_plan(store, [TEMP_OLD], now=clock(), operators=OPS).excluded_pinned == 0


def test_contract_subject_path_examples_match_subject_fields() -> None:
    """계약의 경로 제안(`MEMORY_RETENTION_SUBJECT_PATHS`)이 판단 대상 키와 어긋나지 않는다."""
    from agent_console_contracts.memory import MEMORY_RETENTION_SUBJECT_PATHS

    tops = {p.split("/")[1] for p in MEMORY_RETENTION_SUBJECT_PATHS}
    assert tops == set(RETENTION_SUBJECT_FIELDS)
    entry = sample_entry_summary(created_at=0.0, updated_at=DAY, last_read_at=2 * DAY)
    subject = retention_subject(entry, now=4 * DAY)
    for path in MEMORY_RETENTION_SUBJECT_PATHS:
        node: Any = subject
        for token in path.split("/")[1:]:
            assert isinstance(node, dict), path
            assert token in node, path
            node = node[token]
    # 규칙 스키마: 조건 항목 경로에 제안이 붙고, 검증·평가는 그대로다.
    schema = MemoryRetentionRule.model_json_schema()
    item = schema["$defs"]["MemoryRetentionConditionItem"]
    assert item["properties"]["path"]["examples"] == list(MEMORY_RETENTION_SUBJECT_PATHS)
    assert schema["properties"]["when"]["x-ui"]["widget"] == "condition-list"
    rule = MemoryRetentionRule.model_validate(TEMP_OLD)
    assert compile_retention_rules([rule], OPS).rules

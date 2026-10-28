"""5.7R.33e 공간 사이 복사(design §PI.4.2 K33-6): 계획·적용 판정·이름 바꾸기·옛 데이터."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from agent_console_contracts import CopyApplyItem, DefinitionKey
from agent_console_projects import (
    CODE_COPY_CONFLICT,
    CODE_COPY_KIND_NOT_PORTABLE,
    CODE_COPY_REFERENCE_CYCLE,
    CODE_COPY_REFERENCE_MISSING,
    CODE_COPY_SKIP_BREAKS_REFERENCE,
    CODE_COPY_SOURCE_MISSING,
    CODE_COPY_UNKNOWN_ACTION,
    CODE_REFERENCES_UNAVAILABLE,
    DefinitionId,
    ScopedDefinition,
    SourceDefinition,
    apply_decisions,
    apply_renames,
    copy_plan,
    legacy_counts,
    legacy_items,
    renames_of,
    skip_warnings,
    without_scope_field,
)

# 종류 이름은 테스트 데이터일 뿐이다. 아래 R0 테스트가 이름을 바꿔 같은 결과를 확인한다.
TEAM, AGENT, RES = "graph", "agent", "resource"


def _library(
    team: str = TEAM, agent: str = AGENT, res: str = RES
) -> dict[DefinitionId, SourceDefinition]:
    docs: dict[str, dict[str, Any]] = {
        f"{team}/review": {
            "id": "review",
            "name": "리뷰 팀",
            "uses": [f"{agent}/coder", f"{team}/sub"],
        },
        f"{team}/sub": {"id": "sub", "uses": [f"{agent}/tester", f"{res}/guide"]},
        f"{agent}/coder": {"id": "coder", "name": "코더", "uses": [f"{res}/guide"]},
        f"{agent}/tester": {"id": "tester", "uses": []},
        f"{res}/guide": {"id": "guide", "uses": []},
        f"{team}/loop-a": {"id": "loop-a", "uses": [f"{team}/loop-b"]},
        f"{team}/loop-b": {"id": "loop-b", "uses": [f"{team}/loop-a", f"{agent}/ghost"]},
    }
    out: dict[DefinitionId, SourceDefinition] = {}
    for path, doc in docs.items():
        kind, _, def_id = path.partition("/")
        out[(kind, def_id)] = SourceDefinition(document=doc, version=f"v-{def_id}")
    return out


def refs(kind: str, doc: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    for ref in doc.get("uses", []):
        k, _, i = ref.partition("/")
        yield (k, i)


def rewrite(
    kind: str, doc: Mapping[str, Any], renames: Mapping[DefinitionId, str]
) -> Mapping[str, Any]:
    uses = []
    for ref in doc.get("uses", []):
        k, _, i = ref.partition("/")
        uses.append(f"{k}/{renames.get((k, i), i)}")
    return {**doc, "uses": uses}


def _rows(plan: Any) -> list[tuple[str, str, str, str, str | None]]:
    return [(i.kind, i.id, i.reason, i.target_state, i.default_action) for i in plan.items]


def test_nested_team_closure_and_target_states() -> None:
    target = {(AGENT, "coder"): "v-coder", (RES, "guide"): "changed-here"}
    plan = copy_plan([(TEAM, "review")], _library(), target, references=refs)
    assert _rows(plan) == [
        (TEAM, "review", "requested", "absent", "copy"),
        (AGENT, "coder", "referenced", "identical", "reuse"),
        (TEAM, "sub", "referenced", "absent", "copy"),
        (RES, "guide", "referenced", "different", None),
        (AGENT, "tester", "referenced", "absent", "copy"),
    ]
    by = {(i.kind, i.id): [(k.kind, k.id) for k in i.referenced_by] for i in plan.items}
    assert by[(RES, "guide")] == [(AGENT, "coder"), (TEAM, "sub")]
    assert by[(TEAM, "review")] == []
    guide = next(i for i in plan.items if i.id == "guide")
    assert (guide.source_version, guide.target_version) == ("v-guide", "changed-here")
    assert plan.items[0].name == "리뷰 팀"
    assert plan.warnings == []


def test_cycle_terminates_and_warns_missing_reference() -> None:
    plan = copy_plan([(TEAM, "loop-a")], _library(), {}, references=refs)
    assert [i.id for i in plan.items] == ["loop-a", "loop-b"]
    codes = [w.code for w in plan.warnings]
    assert codes == [CODE_COPY_REFERENCE_MISSING, CODE_COPY_REFERENCE_CYCLE]
    cycle = plan.warnings[1].details["cycle"]
    assert [c["id"] for c in cycle] == ["loop-a", "loop-b"]
    # 대상에 이미 있으면 빠진 참조 경고를 내지 않는다
    plan2 = copy_plan([(TEAM, "loop-a")], _library(), {(AGENT, "ghost"): "x"}, references=refs)
    assert [w.code for w in plan2.warnings] == [CODE_COPY_REFERENCE_CYCLE]


def test_self_reference_is_a_cycle() -> None:
    lib = {(TEAM, "me"): SourceDefinition({"id": "me", "uses": [f"{TEAM}/me"]}, "1")}
    plan = copy_plan([(TEAM, "me")], lib, {}, references=refs)
    assert [w.code for w in plan.warnings] == [CODE_COPY_REFERENCE_CYCLE]
    assert plan.items[0].referenced_by == [DefinitionKey(kind=TEAM, id="me")]


def test_requested_missing_duplicates_and_kind_filter() -> None:
    plan = copy_plan(
        [(TEAM, "review"), DefinitionKey(kind=TEAM, id="review"), {"kind": AGENT, "id": "nope"}],
        _library(),
        {},
        references=refs,
        kinds={TEAM, AGENT},  # 리소스 종류는 대상에 둘 수 없다고 가정
    )
    assert [i.id for i in plan.items] == ["review", "coder", "sub", "tester"]
    assert [w.code for w in plan.warnings] == [
        CODE_COPY_SOURCE_MISSING,
        CODE_COPY_KIND_NOT_PORTABLE,
    ]


def test_without_references_only_requested_and_skip_warning() -> None:
    plan = copy_plan([(AGENT, "coder")], _library(), {}, references=refs, include_references=False)
    assert [i.id for i in plan.items] == ["coder"]
    assert [w.code for w in plan.warnings] == [CODE_COPY_SKIP_BREAKS_REFERENCE]
    none = copy_plan([(TEAM, "review")], _library(), {}, references=None)
    assert [i.id for i in none.items] == ["review"]
    assert [w.code for w in none.warnings] == [CODE_REFERENCES_UNAVAILABLE]


def test_skip_warnings() -> None:
    plan = copy_plan([(TEAM, "review")], _library(), {}, references=refs)
    actions = {(i.kind, i.id): "copy" for i in plan.items}
    actions[(AGENT, "tester")] = "skip"
    warnings = skip_warnings(plan, actions, target_index={})
    assert [(w.code, w.details["source_id"], w.details["id"]) for w in warnings] == [
        (CODE_COPY_SKIP_BREAKS_REFERENCE, "sub", "tester")
    ]
    assert "graph/sub" in warnings[0].message
    assert "agent/tester" in warnings[0].message
    # 대상에 이미 있으면 경고 없음, 쓰는 쪽도 skip이면 경고 없음
    assert skip_warnings(plan, actions, target_index={(AGENT, "tester"): "x"}) == []
    actions[(TEAM, "sub")] = "skip"
    assert [w.details["source_id"] for w in skip_warnings(plan, actions, target_index={})] == [
        "review"
    ]


def test_kind_names_are_data_r0() -> None:
    """종류 이름을 바꿔도 같은 계획(코드에 종류 이름 없음)."""
    a = copy_plan([(TEAM, "review")], _library(), {}, references=refs)
    b = copy_plan([("crew", "review")], _library("crew", "worker", "doc"), {}, references=refs)
    rename = {TEAM: "crew", AGENT: "worker", RES: "doc"}
    assert [(rename[k], i, r, s, d) for k, i, r, s, d in _rows(a)] == _rows(b)


# ---------------------------------------------------------------- 적용 판정


def _item(**kw: Any) -> CopyApplyItem:
    return CopyApplyItem.model_validate({"kind": AGENT, "source_version": "1", **kw})


def test_apply_decisions_table() -> None:
    source = {(AGENT, x): "1" for x in "abcdefgh"}
    source[(AGENT, "changed")] = "2"
    target = {(AGENT, "c"): "t1", (AGENT, "d"): "t1", (AGENT, "e"): "t1", (AGENT, "taken"): "t"}
    items = [
        _item(id="a", action="copy"),
        _item(id="b", action="skip"),
        _item(id="c", action="overwrite", target_version="t1"),
        _item(id="d", action="overwrite", target_version="t0"),
        _item(id="e", action="reuse", target_version="t1"),
        _item(id="f", action="rename", new_id="taken"),
        _item(id="g", action="rename", new_id="g2"),
        _item(id="h", action="copy"),
        _item(id="c", action="copy"),
        _item(id="changed", action="copy"),
        _item(id="gone", action="copy"),
        _item(id="a", action="frobnicate"),
        _item(id="a", action="copy"),
    ]
    target[(AGENT, "h")] = "appeared"
    decisions = apply_decisions(items, source_index=source, target_index=target)
    got = [(d.id, d.status, d.issue.details.get("reason") if d.issue else None) for d in decisions]
    assert got == [
        ("a", "copied", None),
        ("b", "skipped", None),
        ("c", "overwritten", None),
        ("d", "conflict", "target_changed"),
        ("e", "reused", None),
        ("f", "conflict", "rename_taken"),
        ("g", "renamed", None),
        ("h", "conflict", "target_exists"),
        ("c", "conflict", "duplicate"),
        ("changed", "conflict", "source_changed"),
        ("gone", "conflict", "source_missing"),
        ("a", "skipped", None),
        ("a", "conflict", "duplicate"),
    ]
    assert decisions[3].issue is not None
    assert decisions[3].issue.code == CODE_COPY_CONFLICT
    assert decisions[11].issue is not None
    assert decisions[11].issue.code == CODE_COPY_UNKNOWN_ACTION
    assert [d.writes for d in decisions[:3]] == [True, False, True]
    assert decisions[6].result().new_id == "g2"
    assert decisions[0].result().new_id is None
    assert renames_of(decisions) == {(AGENT, "g"): "g2"}


def test_rename_then_references_fixed() -> None:
    lib = _library()
    plan = copy_plan([(TEAM, "review")], lib, {(AGENT, "coder"): "other"}, references=refs)
    items = [
        {
            "kind": i.kind,
            "id": i.id,
            "action": "rename" if i.id == "coder" else (i.default_action or "copy"),
            "new_id": "coder-copy" if i.id == "coder" else None,
            "source_version": i.source_version,
            "target_version": i.target_version,
        }
        for i in plan.items
    ]
    decisions = apply_decisions(
        items,
        source_index={k: v.version for k, v in lib.items()},
        target_index={(AGENT, "coder"): "other"},
    )
    assert all(d.writes for d in decisions)
    docs = {d.key: lib[d.key].document for d in decisions}
    out = apply_renames(docs, renames_of(decisions), rewrite_references=rewrite)
    assert (AGENT, "coder-copy") in out
    assert (AGENT, "coder") not in out
    assert out[(AGENT, "coder-copy")]["id"] == "coder-copy"
    assert out[(TEAM, "review")]["uses"] == [f"{AGENT}/coder-copy", f"{TEAM}/sub"]
    # 입력은 그대로
    assert lib[(TEAM, "review")].document["uses"][0] == f"{AGENT}/coder"
    # 원본 메타를 더하지 않는다(완전 독립)
    assert set(out[(TEAM, "review")]) == {"id", "name", "uses"}


def test_apply_renames_collision() -> None:
    docs = {(AGENT, "a"): {"id": "a"}, (AGENT, "b"): {"id": "b"}}
    with pytest.raises(ValueError, match="agent/b"):
        apply_renames(docs, {(AGENT, "a"): "b"}, rewrite_references=rewrite)


# ---------------------------------------------------------------- 옛 프로젝트 전용 정의(§PI.8)


def test_legacy_items_feed_copy_plan() -> None:
    defs = [
        ScopedDefinition.from_document(TEAM, {"id": "review", "project": "app"}),
        ScopedDefinition.from_document(AGENT, {"id": "coder"}),
        ScopedDefinition.from_document(AGENT, {"id": "tester", "project": "web"}),
    ]
    keys = legacy_items(defs, "app")
    assert [(k.kind, k.id) for k in keys] == [(TEAM, "review")]
    assert legacy_counts(defs) == {"app": 1, "web": 1}
    plan = copy_plan(keys, _library(), {}, references=refs)
    assert plan.items[0].id == "review"
    assert len(plan.items) == 5
    doc = {"id": "review", "project": "app"}
    assert without_scope_field(doc) == {"id": "review"}
    assert doc["project"] == "app"

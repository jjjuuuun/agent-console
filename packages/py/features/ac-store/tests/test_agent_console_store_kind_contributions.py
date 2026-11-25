"""6R.5: `DefinitionKind.library`·`with_summary_fields`·`contributed_kinds`(X44 기여 → 종류)."""

from __future__ import annotations

from dataclasses import dataclass

from agent_console_store import (
    DEFAULT_KINDS,
    GRAPH_KIND,
    DefinitionKind,
    contributed_kinds,
)


@dataclass(frozen=True)
class Contribution:
    kind: object
    summary_fields: tuple[str, ...] = ()


NOTE = DefinitionKind(name="note", directory="notes", library=False)
TEMPLATE = DefinitionKind(name="note-template", directory="note-templates")


def test_library_defaults_true_for_builtin_kinds() -> None:
    assert all(k.library for k in DEFAULT_KINDS)
    assert NOTE.library is False
    assert NOTE.is_portable


def test_with_summary_fields_adds_once() -> None:
    assert GRAPH_KIND.with_summary_fields() is GRAPH_KIND
    assert GRAPH_KIND.with_summary_fields("project") is GRAPH_KIND
    kind = GRAPH_KIND.with_summary_fields("status", "status", "owner")
    assert kind.summary_fields == ("project", "status", "owner")
    assert GRAPH_KIND.summary_fields == ("project",)


def test_contributed_kinds_filters_and_reports() -> None:
    skipped: list[tuple[str, str]] = []
    items = [
        Contribution(TEMPLATE, ("title",)),
        Contribution(NOTE),
        Contribution(DefinitionKind(name="note-template", directory="x")),
        Contribution(DefinitionKind(name="graph", directory="other")),
        Contribution("not a kind"),
    ]
    found = contributed_kinds(
        items,
        reserved=[k.name for k in DEFAULT_KINDS],
        on_skip=lambda name, why: skipped.append((name, why)),
    )
    assert [(k.name, k.summary_fields) for k in found] == [
        ("note-template", ("title",)),
        ("note", ()),
    ]
    assert skipped == [
        ("note-template", "duplicate"),
        ("graph", "reserved"),
        ("'not a kind'", "not_a_kind"),
    ]


def test_contributed_kinds_library_only() -> None:
    skipped: list[tuple[str, str]] = []
    found = contributed_kinds(
        [Contribution(TEMPLATE), Contribution(NOTE)],
        library_only=True,
        on_skip=lambda name, why: skipped.append((name, why)),
    )
    assert [k.name for k in found] == ["note-template"]
    assert skipped == [("note", "not_library")]


def test_no_contributions_is_empty() -> None:
    assert contributed_kinds([]) == []


def test_builtin_kinds_have_titles_fu18() -> None:
    """FU.18: 기본 종류는 종류 데이터에 표시 이름을 둔다(사본·요약 필드 사본에도 남는다)."""
    assert all(k.title for k in DEFAULT_KINDS)
    assert GRAPH_KIND.with_summary_fields("status").title == GRAPH_KIND.title
    assert NOTE.title is None  # 주지 않으면 None(화면은 종류 이름)
    titled = DefinitionKind(name="memo", directory="memos", title="메모")
    assert [k.title for k in contributed_kinds([Contribution(titled)])] == ["메모"]

"""프로필 문서·병합(기본 → 플러그인 → 사용자, id 단위 바꾸기·null 지우기·origin)과 프로필 0개."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from agent_console_architecture import (
    DEFAULT_PROFILES_RESOURCE,
    ProfileDocumentError,
    ProfileSource,
    load_default_profiles,
    merge_profiles,
    parse_profiles_document,
    project_architecture,
)
from agent_console_contracts.architecture import ArchitectureProfile, ArchitectureSettings


def _p(title: str) -> ArchitectureProfile:
    return ArchitectureProfile(title=title)


def test_package_default_data_has_one_profile() -> None:
    # 패키지 기본 데이터(5.5R.8): 프로필 하나. 내용 검사·골든은 test_..._default_profile.py.
    data = resources.files("agent_console_architecture").joinpath(DEFAULT_PROFILES_RESOURCE)
    assert data.is_file()
    assert list(load_default_profiles()) == ["agent-architecture"]


def test_missing_default_file_is_empty(tmp_path: Path) -> None:
    assert load_default_profiles(tmp_path / "none.yaml") == {}


def test_parse_document_and_errors() -> None:
    found = parse_profiles_document(
        "version: 1\nprofiles:\n  a: {title: A, cells: {x: {}}}\n  gone: null\n"
    )
    assert list(found) == ["a"]
    assert list(found["a"].cells) == ["x"]
    assert parse_profiles_document("") == {}
    for bad in ["[1, 2]", "profiles: [1]", "profiles: {a: {cells: 3}}", "a: [b"]:
        with pytest.raises(ProfileDocumentError):
            parse_profiles_document(bad)


def test_unknown_keys_survive() -> None:
    found = parse_profiles_document("profiles:\n  a: {title: A, my_note: keep}\n")
    assert found["a"].model_dump()["my_note"] == "keep"


def test_merge_order_origin_overrides_and_delete() -> None:
    defaults = {"base": _p("기본"), "other": _p("다른 기본")}
    plugin = ProfileSource(origin="plugin:pkg-x", profiles={"base": _p("플러그인"), "px": _p("PX")})
    user = ArchitectureSettings.model_validate(
        {
            "default_profile": "mine",
            "profiles": {"other": None, "mine": {"title": "내 것"}, "px": {"title": "PX2"}},
        }
    )
    catalog = merge_profiles(defaults, [plugin], user)
    assert catalog.ids() == ["base", "px", "mine"]
    base, px, mine = (catalog.entries[i] for i in ("base", "px", "mine"))
    assert (base.title, base.origin, base.overrides) == ("플러그인", "plugin:pkg-x", "default")
    assert (px.title, px.origin, px.overrides) == ("PX2", "user", "plugin:pkg-x")
    assert (mine.origin, mine.overrides) == ("user", None)
    assert [(d.id, d.origin, d.overrides, d.disabled) for d in catalog.disabled] == [
        ("other", "user", "default", True)
    ]
    assert catalog.default_profile == "mine"
    info = base.info(issues=2)
    assert (info.id, info.title, info.origin, info.issues, info.cells, info.edges) == (
        "base",
        "플러그인",
        "plugin:pkg-x",
        2,
        0,
        0,
    )
    assert catalog.disabled[0].info().disabled is True


def test_include_defaults_false() -> None:
    defaults = {"base": _p("기본")}
    user = ArchitectureSettings(include_defaults=False)
    catalog = merge_profiles(defaults, [], user)
    assert len(catalog) == 0
    assert catalog.include_defaults is False
    assert merge_profiles(defaults, [], None, include_defaults=False).ids() == []
    assert merge_profiles(defaults, [], user, include_defaults=True).ids() == ["base"]


def test_default_profile_falls_back_to_first() -> None:
    catalog = merge_profiles(
        {"a": _p("A"), "b": _p("B")}, [], ArchitectureSettings(default_profile="gone")
    )
    assert catalog.default_profile == "a"
    entry, note = catalog.pick("missing")
    assert entry is not None
    assert entry.id == "a"
    assert note is not None
    assert note.details == {"requested": "missing", "used": "a"}
    entry, note = catalog.pick("b")
    assert (entry.id if entry else None, note) == ("b", None)
    entry, note = catalog.pick()
    assert (entry.id if entry else None, note) == ("a", None)


def test_zero_profiles_never_raise() -> None:
    for catalog in (
        merge_profiles({}, [], None),
        merge_profiles({"a": _p("A")}, [], ArchitectureSettings(include_defaults=False)),
        merge_profiles(
            {"a": _p("A")}, [], ArchitectureSettings.model_validate({"profiles": {"a": None}})
        ),
    ):
        assert len(catalog) == 0
        assert catalog.default_profile is None
        assert catalog.pick() == (None, None)
        assert catalog.pick("a") == (None, None)
        assert catalog.get("a") is None


def test_empty_profile_projects() -> None:
    catalog = merge_profiles({"empty": ArchitectureProfile()}, [], None)
    entry, _ = catalog.pick()
    assert entry is not None
    view = project_architecture([], entry.profile, profile_id=entry.id, operators={})
    assert (view.profile, view.cells, view.edges, view.event_total) == ("empty", [], [], 0)

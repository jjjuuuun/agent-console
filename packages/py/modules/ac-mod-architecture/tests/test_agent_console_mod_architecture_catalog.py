"""카탈로그 서비스(포트 ``architecture.catalog``).

병합 순서·끄기·재계산·형식 문제·검사·투영·상한.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from agent_console_architecture import ProfileSource
from agent_console_conditions import ConditionOperator, default_operators
from agent_console_contracts import WorkspaceSettings
from agent_console_contracts.architecture import (
    ArchitectureProfile,
    ArchitectureProfileCheckRequest,
    ArchitectureProjectRequest,
    KnownArchitectureIssueCodes,
    KnownArchitectureNoteCodes,
)
from agent_console_contracts.logs import LogEvent
from agent_console_mod_architecture import (
    INLINE_PROFILE_ID,
    SETTINGS_INVALID,
    ArchitectureCatalog,
    ArchitectureCatalogService,
    ProfileNotFoundError,
    ScopeTooLargeError,
    parse_user_settings,
    section_of,
)

Make = Callable[[dict[str, Any]], ArchitectureProfile]


@pytest.fixture(scope="module")
def operators() -> dict[str, ConditionOperator]:
    found, _ = default_operators()
    return found


def _service(
    operators: dict[str, ConditionOperator],
    *,
    defaults: dict[str, ArchitectureProfile] | None = None,
    plugins: list[ProfileSource] | None = None,
    settings: Callable[[], Any] | None = None,
    **kwargs: Any,
) -> ArchitectureCatalogService:
    return ArchitectureCatalogService(
        defaults=lambda: dict(defaults or {}),
        plugins=lambda: list(plugins or []),
        settings=settings,
        operators=lambda: operators,
        **kwargs,
    )


def test_service_matches_port_protocol(operators: dict[str, ConditionOperator]) -> None:
    assert isinstance(_service(operators), ArchitectureCatalog)


def test_merge_order_origin_override_and_disabled(
    operators: dict[str, ConditionOperator], flow: dict[str, Any], as_profile: Make
) -> None:
    base = as_profile(flow)
    plugin = ProfileSource(origin="plugin:demo-dist", profiles={"plug": base, "shared": base})
    user = {"profiles": {"shared": {**flow, "title": "내 것"}, "gone": None, "mine": flow}}
    service = _service(
        operators,
        defaults={"gone": base, "dflt": base},
        plugins=[plugin],
        settings=lambda: user,
    )
    listing = service.profile_list()
    rows = [(p.id, p.origin, p.overrides, p.disabled) for p in listing.profiles]
    assert rows == [
        ("dflt", "default", None, False),
        ("plug", "plugin:demo-dist", None, False),
        ("shared", "user", "plugin:demo-dist", False),
        ("mine", "user", None, False),
        ("gone", "user", "default", True),  # 끈 프로필은 뒤에(화면의 "끈 프로필 n")
    ]
    assert listing.default_profile == "dflt"
    assert listing.include_defaults is True
    assert all(p.issues == 0 and p.cells == 2 and p.edges == 1 for p in listing.profiles)
    detail = service.profile_detail("gone")
    assert detail.disabled is True
    assert detail.problems == []
    assert service.profile_detail("shared").title == "내 것"


def test_no_profiles_is_empty_list_not_error(
    operators: dict[str, ConditionOperator], flow: dict[str, Any], as_profile: Make
) -> None:
    """``include_defaults: false``·프로필 0개 → 빈 목록(R0.1 (3), 완료 기준)."""
    service = _service(
        operators,
        defaults={"dflt": as_profile(flow)},
        settings=lambda: {"include_defaults": False, "default_profile": "dflt"},
    )
    listing = service.profile_list()
    assert listing.profiles == []
    assert listing.default_profile is None
    assert listing.include_defaults is False
    with pytest.raises(ProfileNotFoundError):
        service.pick()
    with pytest.raises(ProfileNotFoundError) as caught:
        service.profile_detail("dflt")
    assert caught.value.profile == "dflt"


def test_state_is_recomputed_only_when_settings_change(
    operators: dict[str, ConditionOperator], flow: dict[str, Any]
) -> None:
    current: dict[str, Any] = {"profiles": {"a": flow}}
    calls = {"defaults": 0}

    def defaults() -> dict[str, ArchitectureProfile]:
        calls["defaults"] += 1
        return {}

    service = ArchitectureCatalogService(
        defaults=defaults, settings=lambda: current, operators=lambda: operators
    )
    first = service.state()
    assert service.state() is first  # 같은 입력이면 다시 계산하지 않는다
    assert first.catalog.ids() == ["a"]
    current = {"profiles": {"a": flow, "b": flow}, "default_profile": "b"}
    second = service.state()
    assert second is not first
    assert second.catalog.ids() == ["a", "b"]
    assert second.catalog.default_profile == "b"
    assert calls["defaults"] == 1  # 패키지 기본 데이터는 한 번만 읽는다


def test_invalid_user_parts_are_dropped_with_warnings(
    operators: dict[str, ConditionOperator], flow: dict[str, Any], as_profile: Make
) -> None:
    raw = {
        "include_defaults": "아마도",
        "profiles": {"dflt": {"cells": 3}, "ok": flow},
    }
    service = _service(operators, defaults={"dflt": as_profile(flow)}, settings=lambda: raw)
    listing = service.profile_list()
    # 깨진 사용자 프로필은 빼고, 같은 id의 기본 프로필은 그대로 남는다. 틀린 스위치는 기본값.
    assert [(p.id, p.origin) for p in listing.profiles] == [("dflt", "default"), ("ok", "user")]
    warnings = service.warnings()
    assert {(w.code, w.path) for w in warnings} == {
        (SETTINGS_INVALID, "/architecture/include_defaults"),
        (SETTINGS_INVALID, "/architecture/profiles/dflt"),
    }
    assert all(w.severity == "warning" for w in warnings)
    assert "아마도" not in " ".join(w.message for w in warnings)  # 값 원문을 싣지 않는다


def test_parse_user_settings_shapes() -> None:
    settings, issues = parse_user_settings(None)
    assert (settings.include_defaults, issues) == (True, [])
    settings, issues = parse_user_settings(["not", "a", "map"])
    assert settings.profiles == {}
    assert [i.path for i in issues] == ["/architecture"]
    settings, issues = parse_user_settings({"profiles": 3})
    assert [i.path for i in issues] == ["/architecture/profiles"]


def test_section_of_reads_unknown_key_of_workspace_settings(flow: dict[str, Any]) -> None:
    """공통 설정 모델은 ``architecture``를 모르는 키로 보존한다(design §5.5R.2.4 구현 메모)."""
    doc = WorkspaceSettings.model_validate({"architecture": {"profiles": {"a": flow}}})
    section = section_of(doc)
    assert isinstance(section, dict)
    assert list(section["profiles"]) == ["a"]
    assert section_of(WorkspaceSettings()) is None
    assert section_of({"architecture": {"include_defaults": False}}) == {"include_defaults": False}
    assert section_of(None) is None


def test_issue_counts_and_check(
    operators: dict[str, ConditionOperator], broken: dict[str, Any], flow: dict[str, Any]
) -> None:
    service = _service(operators, settings=lambda: {"profiles": {"bad": broken}})
    [info] = service.profile_list().profiles
    detail = service.profile_detail("bad")
    assert info.issues == len(detail.problems) >= 2
    codes = {p.code for p in detail.problems}
    assert KnownArchitectureIssueCodes.UNKNOWN_CELL in codes
    # 검사: 형식 오류도 예외가 아니라 문제로
    shape = service.check(ArchitectureProfileCheckRequest(profile={"cells": 3}))
    assert [i.code for i in shape.issues] == [KnownArchitectureIssueCodes.INVALID]
    bad_id = service.check(ArchitectureProfileCheckRequest(id="a:b", profile=flow))
    assert [i.code for i in bad_id.issues] == [KnownArchitectureIssueCodes.BAD_ID]
    assert service.check(ArchitectureProfileCheckRequest(id="ok", profile=flow)).issues == []


def test_project_by_id_fallback_inline_and_limits(
    operators: dict[str, ConditionOperator],
    flow: dict[str, Any],
    events: list[LogEvent],
    as_profile: Make,
) -> None:
    service = _service(operators, settings=lambda: {"profiles": {"flow": flow}})
    view = service.project(events, profile="flow")
    counts = {c.id: c.metrics["count"].value for c in view.cells}
    assert counts == {"ask": 1.0, "work": 2.0}
    assert view.notes == []
    fallback = service.project(events, profile="nope")
    assert fallback.profile == "flow"
    assert [n.code for n in fallback.notes] == [KnownArchitectureNoteCodes.PROFILE_FALLBACK]
    inline = service.project(events, inline=as_profile(flow))
    assert inline.profile == INLINE_PROFILE_ID
    assert inline.cells[0].selector.arch.startswith(f"{INLINE_PROFILE_ID}:")
    named = service.project(events, inline=as_profile(flow), inline_id="draft")
    assert named.profile == "draft"
    with pytest.raises(ScopeTooLargeError) as caught:
        service.project(events, profile="flow", limit=3)
    assert (caught.value.events, caught.value.limit) == (4, 3)
    service.ensure_within(3, 3)  # 같으면 통과


def test_project_request_uses_request_limit(
    operators: dict[str, ConditionOperator], flow: dict[str, Any], event_rows: list[dict[str, Any]]
) -> None:
    service = _service(
        operators, settings=lambda: {"profiles": {"flow": flow}}, max_request_events=2
    )
    request = ArchitectureProjectRequest.model_validate({"events": event_rows[:2]})
    assert service.project_request(request).event_total == 2
    with pytest.raises(ScopeTooLargeError):
        service.project_request(ArchitectureProjectRequest.model_validate({"events": event_rows}))


def test_project_without_any_profile_is_not_found(
    operators: dict[str, ConditionOperator],
    events: list[LogEvent],
    flow: dict[str, Any],
    as_profile: Make,
) -> None:
    service = _service(operators)
    with pytest.raises(ProfileNotFoundError):
        service.project(events)
    # 인라인 본문이면 프로필이 없어도 그린다(설정 미리보기)
    assert service.project([], inline=as_profile(flow)).event_total == 0

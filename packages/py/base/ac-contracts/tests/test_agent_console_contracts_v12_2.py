"""계약 0.12.2(5.7R.34·5.7R.38): 디스크립터 화면 속성, 이슈 `hint`·`group`, `unset_node_fields`.

더하기만 한다: 0.12.1 응답(새 필드 없음)이 그대로 읽히고, 지정하지 않은 새 필드는 저장 형식
(`exclude_unset`)과 이슈 전송 형식에 나타나지 않는다.
"""

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    DelegationStrategyDescriptor,
    EdgeTypeDescriptor,
    GraphPatch,
    Issue,
    IssueGroup,
    IssueSuggestion,
    KnownDelegationBackends,
    KnownDelegationSessions,
    NodeFieldRef,
    NodeTypeDescriptor,
    build_schema,
)


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_12_2() -> None:
    """0.12.2에서 정한 버전 이상이다(정확한 지금 값은 0.13.0 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 12, 2)
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0122 = {
        "common": "1.7.0",
        "resources": "1.1.0",
        "logs": "1.1.0",
        "definitions": "1.5.0",
        "runs": "1.6.0",
        "usage": "1.1.0",
        "projects": "3.1.0",
        "chat": "1.2.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "modules": "1.3.0",
    }
    for sub, version in v0122.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub
    assert constants["KNOWN_DELEGATION_SESSIONS"] == {"SAME": "same", "SEPARATE": "separate"}
    assert constants["KNOWN_DELEGATION_BACKENDS"] == {"DELEGATOR": "delegator", "TARGET": "target"}


def test_new_models_live_in_their_submodules() -> None:
    grouped = build_schema()["x-modules"]
    assert {"IssueGroup", "NodeFieldRef"} <= set(grouped["definitions"])


# ---------------------------------------------------------------- 위임 방식 화면 속성


def _strategy(**extra: object) -> DelegationStrategyDescriptor:
    data: dict[str, object] = {"id": "s", "title": "t", "member_fields": [], "max_depth": None}
    data.update(extra)
    return DelegationStrategyDescriptor.model_validate(data)


def test_session_and_nestable_are_filled_from_engine_attributes() -> None:
    same = _strategy(max_depth=1)  # shares_session 기본 true
    assert same.session == KnownDelegationSessions.SAME
    assert same.nestable is False
    separate = _strategy(shares_session=False)
    assert separate.session == KnownDelegationSessions.SEPARATE
    assert separate.nestable is True  # max_depth null = 제한 없음
    assert _strategy(max_depth=2).nestable is True
    assert same.backend is None  # 채우지 않는다(표시하지 않음)


def test_filled_values_are_not_stored_fields() -> None:
    desc = _strategy(max_depth=1)
    assert "session" not in desc.model_dump(mode="json", exclude_unset=True)
    assert "nestable" not in desc.model_dump(mode="json", exclude_unset=True)
    full = desc.model_dump(mode="json")
    assert full["session"] == "same"
    assert full["nestable"] is False
    # 다시 읽어도 같다(응답 왕복)
    assert DelegationStrategyDescriptor.model_validate(full) == desc


def test_explicit_values_are_kept_and_open_strings_allowed() -> None:
    desc = _strategy(
        shares_session=False,
        session="separate",
        backend=KnownDelegationBackends.TARGET,
        nestable=True,
    )
    assert (desc.session, desc.backend, desc.nestable) == ("separate", "target", True)
    other = _strategy(session="pooled", backend="shared-pool")  # 모르는 값도 받는다(R0)
    assert (other.session, other.backend) == ("pooled", "shared-pool")


@pytest.mark.parametrize(
    "extra",
    [
        {"shares_session": True, "session": "separate"},
        {"shares_session": False, "session": "same"},
        {"max_depth": 1, "nestable": True},
        {"max_depth": None, "nestable": False},
    ],
)
def test_known_values_must_match_engine_attributes(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _strategy(**extra)


def test_edge_and_node_type_attributes_are_optional() -> None:
    edge = EdgeTypeDescriptor.model_validate({"id": "e", "title": "t"})
    assert edge.session is None
    assert (
        EdgeTypeDescriptor.model_validate({"id": "e", "title": "t", "session": "separate"}).session
        == "separate"
    )
    node = NodeTypeDescriptor.model_validate({"id": "n", "title": "t"})
    assert node.opens_session is True
    assert (
        NodeTypeDescriptor.model_validate(
            {"id": "n", "title": "t", "opens_session": False}
        ).opens_session
        is False
    )


# ---------------------------------------------------------------- 이슈·패치


def test_issue_hint_and_group_are_omitted_when_unset() -> None:
    plain = Issue(severity="info", code="x.y", message="m")
    dumped = plain.model_dump(mode="json")
    assert "hint" not in dumped
    assert "group" not in dumped
    grouped = Issue(
        severity="info",
        code="x.y",
        message="m",
        hint="h",
        group=IssueGroup(key="k", message="묶음"),
    )
    dumped = grouped.model_dump(mode="json")
    assert dumped["hint"] == "h"
    assert dumped["group"] == {"key": "k", "message": "묶음"}
    assert Issue.model_validate(dumped) == grouped


def test_graph_patch_unset_node_fields_omitted_when_unset() -> None:
    assert GraphPatch().model_dump(mode="json") == {
        "add_nodes": [],
        "add_edges": [],
        "remove_edge_ids": [],
    }
    patch = GraphPatch(unset_node_fields=[NodeFieldRef(node_id="n1", path="/settings/model")])
    dumped = IssueSuggestion(id="s", label="값 비우기", patch=patch).model_dump(mode="json")
    assert dumped["patch"]["unset_node_fields"] == [{"node_id": "n1", "path": "/settings/model"}]
    with pytest.raises(ValidationError):
        NodeFieldRef(node_id="n1", path="settings")  # JSON Pointer만

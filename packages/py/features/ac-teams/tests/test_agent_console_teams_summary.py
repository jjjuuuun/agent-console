"""2R.7 화면 요약: 답변 계획(`reply_fields`), 검증 요약, 강제되지 않는 실행 범위, 묶음 미리보기.

모든 디스크립터는 임의 이름(testkit)이다. 답변 연결 config 키도 테스트 전용 이름을 쓴다(H1:
ac-teams는 키 이름을 모르고 디스크립터 `reply_fields`로만 읽는다).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    AgentSettings,
    BackendCapabilities,
    EdgeTypeDescriptor,
    EnforceCapabilities,
    Graph,
    InteractionGrant,
    Issue,
    KnownIssueCodes,
    ReplyFields,
    Resource,
    ResourceContentRef,
    ResourceTypeDescriptor,
    WorkspaceSettings,
)
from agent_console_resources import (
    Content,
    ContributeContext,
    Contribution,
    InMemoryResources,
    SchemaResourceType,
    content_text,
    new_resource_types,
)
from agent_console_teams import (
    TeamPlan,
    bundle_preview,
    limits_warnings,
    node_settings,
    plan_summary,
    session_owner,
    team_plan,
    validation_summary,
)
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]

# 테스트 전용 답변 연결: 기본 플러그인과 **다른** config 위치를 선언한다.
ODD_REPLY = ReplyFields(label="/display/name", order="/pos", final="/is_last", stream="/live")
ODD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "display": {"type": "object", "properties": {"name": {"type": "string"}}},
        "pos": {"type": "integer"},
        "is_last": {"type": "boolean", "default": True},
        "live": {"type": "boolean", "default": True},
    },
}


def _with_reply_fields(k: Kit, fields: ReplyFields | None, schema: dict[str, Any]) -> list[Any]:
    out: list[EdgeTypeDescriptor] = []
    for desc in k.edge_types:
        if desc.scheduling == "exit":
            desc = desc.model_copy(update={"reply_fields": fields, "config_schema": schema})
        out.append(desc)
    return out


def _plan(k: Kit, graph: Graph, edge_types: list[Any] | None = None) -> TeamPlan:
    return team_plan(graph, node_types=k.node_types, edge_types=edge_types or k.edge_types)


# ---------------------------------------------------------------- 답변 계획


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_plan_summary_reads_reply_fields_declared_by_edge_type(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead", who="pl"), k.worker("mate")]
    edges = [
        k.edge("in", "entry", "me", "lead"),
        k.edge("f", "flow", "lead", "mate"),
        k.edge("r1", "exit", "lead", "me", display={"name": "초안"}, pos=2, is_last=False),
        k.edge("r2", "exit", "mate", "me", live=False),
        k.edge("q", "ask", "lead", "me", timeout_seconds=5),
    ]
    plan = _plan(k, k.graph(nodes, edges), _with_reply_fields(k, ODD_REPLY, ODD_SCHEMA))
    summary = plan_summary(plan)

    assert [(e.edge_id, e.node_id, e.label) for e in summary.entries] == [("in", "lead", "LEAD")]
    r1, r2 = summary.answers
    assert (r1.edge_id, r1.node_id, r1.agent_id) == ("r1", "lead", "pl")
    assert (r1.label, r1.order, r1.final, r1.stream) == (
        "초안",
        2,
        False,
        True,
    )  # stream = 스키마 기본
    assert (r2.label, r2.order, r2.final, r2.stream) == (None, None, True, False)
    assert summary.grants["lead"] == InteractionGrant(kinds=[k["q"], k["perm"]], timeout_seconds=5)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_plan_summary_ignores_keys_the_edge_type_did_not_declare(k: Kit) -> None:
    """기본 플러그인의 키 이름(`label`·`final`…)을 써도 디스크립터가 선언하지 않으면 읽지 않는다."""
    nodes = [k.person(), k.worker("lead")]
    exit_edge = k.edge("r", "exit", "lead", "me", label="키", order=1, final=False, stream=True)
    edges = [k.edge("in", "entry", "me", "lead"), exit_edge.model_copy(update={"label": "엣지"})]
    plan = _plan(k, k.graph(nodes, edges), _with_reply_fields(k, ODD_REPLY, ODD_SCHEMA))
    [answer] = plan_summary(plan).answers
    assert (answer.label, answer.order, answer.final, answer.stream) == ("엣지", None, True, True)

    # reply_fields가 없으면: label = 엣지 label, final = true, stream = false(계약 기본 규칙)
    bare = _plan(k, k.graph(nodes, edges), _with_reply_fields(k, None, {}))
    [answer] = plan_summary(bare).answers
    assert (answer.label, answer.order, answer.final, answer.stream) == ("엣지", None, True, False)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_plan_summary_wrong_types_fall_back(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead")]
    edges = [k.edge("r", "exit", "lead", "me", display={"name": 3}, pos=True, is_last="no")]
    plan = _plan(k, k.graph(nodes, edges), _with_reply_fields(k, ODD_REPLY, ODD_SCHEMA))
    [answer] = plan_summary(plan).answers
    assert (answer.label, answer.order, answer.final) == (None, None, True)


# ---------------------------------------------------------------- 검증 요약


def test_validation_summary_counts_and_blocking() -> None:
    issues = [
        Issue(severity="warning", code="a.b", message="m"),
        Issue(severity="error", code="c.d", message="m", blocks_run=False),
        Issue(severity="warning", code="a.b", message="m2"),
        Issue(severity="info", code="e", message="m"),
    ]
    summary = validation_summary(issues)
    assert (summary.blocks_run, summary.error_count, summary.warning_count) == (False, 1, 2)
    assert summary.codes == ["a.b", "c.d", "e"]
    blocked = validation_summary(
        [*issues, Issue(severity="warning", code="x", message="m", blocks_run=True)]
    )
    assert blocked.blocks_run is True
    assert validation_summary([]).model_dump() == {
        "blocks_run": False,
        "error_count": 0,
        "warning_count": 0,
        "codes": [],
    }


# ---------------------------------------------------------------- 강제되지 않는 실행 범위


@pytest.mark.parametrize(
    ("enforce", "expected"),
    [
        (EnforceCapabilities(), ["/limits/commands", "/limits/directories", "/limits/network"]),
        (EnforceCapabilities(commands=True), ["/limits/directories", "/limits/network"]),
        (EnforceCapabilities(directories=True, commands=True, network=True), []),
        ({"network": True}, ["/limits/commands", "/limits/directories"]),  # 없는 이름 = 강제 못 함
    ],
)
def test_limits_warnings_follow_enforce_by_same_key(enforce: Any, expected: list[str]) -> None:
    value = AgentSettings.model_validate(
        {"limits": {"directories": ["/w"], "commands": ["ls"], "network": "deny"}}
    )
    found = limits_warnings(value, enforce, backend="b-x")
    assert sorted(i.path or "" for i in found) == expected
    assert all(i.code == KnownIssueCodes.LIMITS_NOT_ENFORCED for i in found)
    assert all(i.severity == "warning" and i.details["backend"] == "b-x" for i in found)


def test_limits_warnings_only_for_set_fields() -> None:
    value = AgentSettings.model_validate({"limits": {"commands": []}})
    assert [i.path for i in limits_warnings(value, EnforceCapabilities())] == ["/limits/commands"]
    assert limits_warnings(AgentSettings(), EnforceCapabilities()) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_node_settings_adds_not_enforced_for_effective_backend(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("deep")]
    edges = [
        k.edge("in", "entry", "me", "lead"),
        k.edge("d1", "invoke", "lead", "mate"),  # s_inner: limits 적용 안 됨
        k.edge("d2", "invoke2", "lead", "deep"),  # s_deep: limits 적용됨
    ]
    graph = k.graph(nodes, edges, settings={"limits": {"commands": ["git"], "network": "deny"}})
    plan = _plan(k, graph)
    backends = {
        "strict-b": BackendCapabilities(enforce=EnforceCapabilities(commands=True, network=True)),
        "loose-b": BackendCapabilities(enforce=EnforceCapabilities(commands=True)),
    }
    ws = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "loose-b"}})

    def codes(node: str, workspace: WorkspaceSettings = ws) -> list[str | None]:
        ns = node_settings(
            plan, node, workspace=workspace, strategies=k.strategy_map, backends=backends
        )
        return [
            w.path for w in ns.effective.warnings if w.code == KnownIssueCodes.LIMITS_NOT_ENFORCED
        ]

    assert codes("lead") == ["/limits/network"]
    assert codes("mate") == []  # 이 자리에서 limits가 적용되지 않는다
    assert codes("deep") == ["/limits/network"]
    strict = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "strict-b"}})
    assert codes("lead", strict) == []
    unknown = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "nope"}})
    assert codes("lead", unknown) == []  # 모르는 백엔드는 다른 검사가 알린다
    # backends를 주지 않으면 경고하지 않는다(기존 호출 그대로)
    plain = node_settings(plan, "lead", workspace=ws, strategies=k.strategy_map)
    assert all(w.code != KnownIssueCodes.LIMITS_NOT_ENFORCED for w in plain.effective.warnings)


# ---------------------------------------------------------------- 묶음 미리보기


class NoteType(SchemaResourceType):
    """테스트 전용 리소스 종류: 본문을 config `slot` 칸에 넣는다(칸 이름도 데이터)."""

    descriptor = ResourceTypeDescriptor(
        id="note-x",
        title="노트",
        config_schema={
            "type": "object",
            "properties": {
                "slot": {"type": "string"},
                "token": {"type": "string", "x-secret": True},
            },
        },
        contributes=["slot-a", "slot-b", "slot-c"],
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution(str(resource.config["slot"]), [content_text(content)])]


def _note(rid: str, slot: str) -> Resource:
    return Resource(
        id=rid,
        type="note-x",
        name=rid,
        config={"slot": slot},
        content=ResourceContentRef(file="n.md"),
    )


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_bundle_preview_warns_unsupported_and_session_shared_slots(k: Kit) -> None:
    types = new_resource_types()
    types.register("note-x", NoteType())
    resources = InMemoryResources(
        [_note("na", "slot-a"), _note("nb", "slot-b"), _note("nc", "slot-c")],
        contents={"na": "A", "nb": "B", "nc": "C"},
    )
    attach = {"resources": [{"ref": "na"}, {"ref": "nb"}, {"ref": "nc"}]}
    nodes = [k.person(), k.worker("lead"), k.worker("mate", settings=attach)]
    edges = [k.edge("in", "entry", "me", "lead"), k.edge("d1", "invoke", "lead", "mate")]
    plan = _plan(k, k.graph(nodes, edges))
    backends = {
        "sess-b": BackendCapabilities(
            resource_slots=["slot-a", "slot-b"], subagent_slots=["slot-a"]
        ),
        "other-b": BackendCapabilities(resource_slots=["slot-a", "slot-b", "slot-c"]),
    }
    # 위임자(lead)가 sess-b, 대상(mate)은 다른 백엔드를 골라도 위임자 세션 백엔드로 판정한다
    lead_ws = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "sess-b"}})
    assert session_owner(plan, "mate") == "lead"
    assert session_owner(plan, "lead") == "lead"

    preview = bundle_preview(
        plan,
        "mate",
        resource_types=types,
        resources=resources,
        backends=backends,
        workspace=lead_ws,
        strategies=k.strategy_map,
    )
    assert preview.bundle.slots == {"slot-a": ["A"], "slot-b": ["B"], "slot-c": ["C"]}
    by_code = [(w.code, w.details.get("slot")) for w in preview.warnings]
    assert (KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED, "slot-c") in by_code
    assert (KnownIssueCodes.RESOURCE_SLOT_SESSION_SHARED, "slot-b") in by_code
    shared = [s for c, s in by_code if c == KnownIssueCodes.RESOURCE_SLOT_SESSION_SHARED]
    assert shared == ["slot-b"]  # slot-a는 대상별, slot-c는 받지 않는 칸이라 공유 경고 없음

    # 위임받지 않는 노드는 세션 공유 경고가 없다
    lead_attach = k.graph(
        [k.person(), k.worker("lead", settings=attach)], [k.edge("in", "entry", "me", "lead")]
    )
    solo = bundle_preview(
        _plan(k, lead_attach),
        "lead",
        resource_types=types,
        resources=resources,
        backends=backends,
        workspace=lead_ws,
    )
    assert all(w.code != KnownIssueCodes.RESOURCE_SLOT_SESSION_SHARED for w in solo.warnings)
    # subagent_slots가 null이면(구분 정보 없음) 공유 경고를 하지 않는다
    other_ws = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "other-b"}})
    loose = bundle_preview(
        plan,
        "mate",
        resource_types=types,
        resources=resources,
        backends=backends,
        workspace=other_ws,
        strategies=k.strategy_map,
    )
    assert loose.warnings == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_bundle_preview_masks_plain_secret_overrides(k: Kit) -> None:
    types = new_resource_types()
    types.register("note-x", NoteType())
    resources = InMemoryResources([_note("na", "slot-a")], contents={"na": "A"})
    attach = {"resources": [{"ref": "na", "config_override": {"token": "plain-zz"}}]}
    plan = _plan(k, k.graph([k.worker("lead", settings=attach)], []))
    preview = bundle_preview(plan, "lead", resource_types=types, resources=resources, backends={})
    assert "plain-zz" not in preview.model_dump_json()

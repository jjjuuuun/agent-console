"""계약 v2(design §R9.3): 설정 층 "생략 = 상속", 상호작용, 채팅, 리소스, 사용량, 연결 종류.

R0: 연결 종류·리소스 종류·상호작용 종류·창 이름·위임 방식·사용량 출처는 문자열 id이며
계약 스키마에 고정 목록(enum/const/default)으로 나오지 않는다.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    KNOWN_RUN_EVENT_TYPES,
    RUN_ORIGINS,
    WS_AUTH_CLOSE_CODES,
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_UNAUTHORIZED,
    Agent,
    AgentSettings,
    AgentSubagentEvent,
    ApplyPresetRequest,
    BackendCapabilities,
    BundleSource,
    ChatTurn,
    ConversationSummary,
    DelegationStrategyDescriptor,
    EdgeTypeDescriptor,
    ErrorCodes,
    Graph,
    ImportPreview,
    ImportRequest,
    Interaction,
    InteractionAnsweredEvent,
    InteractionClosedEvent,
    InteractionGrant,
    InteractionKindDescriptor,
    InteractionRequestedEvent,
    Issue,
    KnownInteractionKinds,
    KnownResourceSlots,
    NodeStatusEvent,
    NodeTypeDescriptor,
    QueuedMessage,
    Resource,
    ResourceAttachment,
    ResourceBundle,
    RespondInteractionRequest,
    ReviewDecision,
    Run,
    RunEvent,
    RunLifecycleEvent,
    RunReplyEvent,
    UiHints,
    UpdateConversationRequest,
    UsageRateLimitEvent,
    UsageWindowSnapshot,
    WorkspaceSettings,
    WsServerMessage,
    build_schema,
    parse_run_event,
)

# design.md에 예로 나오는 1R 기본 플러그인 이름. 계약 스키마에 고정 값으로 나오면 안 된다.
CONNECTION_KINDS = {"subagent", "handoff", "uses", "message", "reply", "ask_user", "delegate"}
RESOURCE_TYPES = {"instruction", "file", "mcp-server", "tool-permission", "skill", "hook", "rule"}
WINDOW_NAMES = {"five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "overage"}
INTERACTION_KINDS = {
    KnownInteractionKinds.QUESTION,
    KnownInteractionKinds.TOOL_PERMISSION,
    KnownInteractionKinds.REVIEW,
}
STRATEGIES_AND_SOURCES = {"sdk-subagents", "host", "run-events", "statusline-file"}
NODE_ROLES = {"user"}
SLOT_NAMES = {
    KnownResourceSlots.INSTRUCTIONS,
    KnownResourceSlots.FILES,
    KnownResourceSlots.MCP_SERVERS,
    KnownResourceSlots.TOOLS,
    KnownResourceSlots.SKILLS,
    KnownResourceSlots.HOOKS,
    KnownResourceSlots.RULES,
}
FORBIDDEN_IN_SCHEMA = (
    CONNECTION_KINDS
    | RESOURCE_TYPES
    | WINDOW_NAMES
    | INTERACTION_KINDS
    | STRATEGIES_AND_SOURCES
    | NODE_ROLES
    | SLOT_NAMES
)


def _fixed_values(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum":
                found |= {v for v in value if isinstance(v, str)}
            elif key in ("const", "default") and isinstance(value, str):
                found.add(value)
            else:
                found |= _fixed_values(value)
    elif isinstance(node, list):
        for item in node:
            found |= _fixed_values(item)
    return found


def _event(type_: str, payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "event_id": "e1",
        "run_id": "r1",
        "seq": 1,
        "ts": 1.0,
        "node_path": ["n1"],
        "type": type_,
        "payload": payload,
        **extra,
    }


def _interaction(**extra: Any) -> dict[str, Any]:
    return {
        "id": "i1",
        "run_id": "r1",
        "node_id": "n1",
        "kind": "pick-a-color",
        "status": "pending",
        "payload": {"anything": 1},
        "response_schema": {"type": "object"},
        "created_at": 1.0,
        **extra,
    }


# ---------------------------------------------------------------- 생략 = 상속


@pytest.mark.parametrize(
    "doc",
    [
        {},  # 전부 생략 = 전부 상속
        {"model": None, "tools": []},  # null·빈 목록 = 이 층에서 지정
        {"tools": ["a"], "disallowed_tools": None, "resources": []},
        {"limits": {"directories": []}, "observe": {"hooks": True}},
        {"session": "fresh", "prompt_template": "", "backend_options": {}},
        {"resources": [{"ref": "r1"}, {"ref": "r2", "mode": "remove"}]},
    ],
)
def test_agent_settings_omitted_null_and_empty_round_trip(doc: dict[str, Any]) -> None:
    settings = AgentSettings.model_validate(doc)
    assert settings.model_dump(mode="json", exclude_unset=True) == doc
    assert AgentSettings.model_validate(settings.model_dump(exclude_unset=True)) == settings


def test_omitted_null_and_empty_are_distinguishable() -> None:
    omitted = AgentSettings.model_validate({})
    null = AgentSettings.model_validate({"tools": None})
    empty = AgentSettings.model_validate({"tools": []})
    assert "tools" not in omitted.model_fields_set
    assert "tools" in null.model_fields_set
    assert null.tools is None
    assert "tools" in empty.model_fields_set
    assert empty.tools == []
    assert omitted.model_dump(exclude_unset=True) == {}
    assert null.model_dump(exclude_unset=True) == {"tools": None}
    assert empty.model_dump(exclude_unset=True) == {"tools": []}


def test_agent_definition_settings_inherit_when_omitted() -> None:
    doc = {"id": "pl", "name": "PL", "role": "설계", "model": None, "custom": {"keep": 1}}
    agent = Agent.model_validate(doc)
    assert agent.tools is None
    assert "tools" not in agent.model_fields_set
    assert agent.model_dump(mode="json", exclude_unset=True) == doc  # 모르는 필드도 보존
    assert set(AgentSettings.model_fields) <= set(Agent.model_fields)


def test_graph_settings_and_workspace_layers_round_trip() -> None:
    graph_doc: dict[str, Any] = {
        "id": "team",
        "name": "팀",
        "settings": {
            "model": "m-1",
            "resources": [{"ref": "guide"}],
            "chat": {"reply_display": "merged"},
            "interaction": {"timeout_seconds": None},
            "settings_merge": {"/limits": "intersect"},
        },
        "nodes": [{"id": "n1", "type": "zz", "config": {"settings": {"tools": []}}}],
    }
    graph = Graph.model_validate(graph_doc)
    assert graph.settings is not None
    assert graph.settings.chat is not None
    assert graph.settings.chat.busy_policy == "queue"  # 코드 기본값(스키마 기본값 층)
    assert graph.model_dump(mode="json", exclude_unset=True) == graph_doc  # 기본값은 쓰지 않음

    ws_doc: dict[str, Any] = {
        "agent_defaults": {"backend": "b1", "observe": {"hooks": True}},
        "usage": {"window_labels": {"w-1": "창 1"}, "sources": [{"id": "src-1"}]},
        "default_backend": "old",  # 이전 형식 읽기 호환
    }
    ws = WorkspaceSettings.model_validate(ws_doc)
    assert ws.chat.reply_display == "separate"
    assert ws.model_dump(mode="json", exclude_unset=True) == ws_doc


def test_merge_annotations_are_strategy_names_on_schema() -> None:
    props = build_schema()["$defs"]["AgentSettings"]["properties"]
    assert props["resources"]["x-merge"] == "keyed_attachments"
    limits = build_schema()["$defs"]["Limits"]["properties"]
    assert limits["directories"]["x-widen"] == "path_subset"
    assert limits["commands"]["x-widen"] == "subset"
    assert limits["network"]["x-widen"] == {"kind": "order", "order": ["deny", "allow"]}
    assert props["limits"]["x-merge"] == "replace"
    assert "x-merge" not in props["model"]


def test_invalid_layer_values_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentSettings.model_validate({"session": "sometimes"})
    with pytest.raises(ValidationError):
        ResourceAttachment.model_validate({"ref": "../x"})
    with pytest.raises(ValidationError):
        WorkspaceSettings.model_validate({"chat": {"busy_policy": "parallel"}})


# ---------------------------------------------------------------- R0: 이름 없는 계약


def test_schema_has_no_connection_resource_window_or_interaction_names() -> None:
    leaked = _fixed_values(build_schema()) & FORBIDDEN_IN_SCHEMA
    assert not leaked, leaked


def test_known_constant_names_are_not_exported_to_ts() -> None:
    constants = build_schema()["x-constants"]
    text = repr(constants)
    for name in INTERACTION_KINDS | SLOT_NAMES:
        assert f"'{name}'" not in text, name


def test_package_source_names_only_in_document_constants() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "agent_console_contracts"
    names = FORBIDDEN_IN_SCHEMA
    for path in src.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        allowed = INTERACTION_KINDS | SLOT_NAMES if path.name == "constants.py" else set()
        for name in names - allowed:
            assert f'"{name}"' not in text, (path.name, name)


def test_interaction_kind_ids_are_open_strings() -> None:
    defs = build_schema()["$defs"]
    for model, field in [("Interaction", "kind"), ("InteractionKindDescriptor", "id")]:
        prop = defs[model]["properties"][field]
        assert prop["type"] == "string"
        assert not {"enum", "const", "default"} & prop.keys(), (model, field)
    for model, field in [
        ("InteractionGrant", "kinds"),
        ("EdgeInteraction", "kinds"),
    ]:
        items = defs[model]["properties"][field]["items"]
        assert items == {"type": "string"}, (model, field)
    interaction = Interaction.model_validate(_interaction())
    assert interaction.kind == "pick-a-color"
    grant = InteractionGrant(kinds=["anything", "plugin.kind"], on_timeout="cancel_run")
    assert grant.kinds == ["anything", "plugin.kind"]
    assert BackendCapabilities(interactions=["zz"]).interactions == ["zz"]
    assert BackendCapabilities().interactions is None  # null = 제한 없음
    desc = InteractionKindDescriptor(
        id="pick-a-color", title="색", free_text_path="/response", ui_hints=UiHints(renderer="zz")
    )
    assert desc.ui_hints is not None
    assert desc.ui_hints.renderer == "zz"
    with pytest.raises(ValidationError):
        InteractionKindDescriptor(id="x", title="x", free_text_path="response")


def test_edge_descriptor_attributes_are_data() -> None:
    edge = EdgeTypeDescriptor.model_validate(
        {
            "id": "zz-call",
            "title": "부르기",
            "scheduling": "none",
            "invocation": {"strategy": "zz-strategy"},
            "connects": {"source": ["zz-role"], "target": ["zz-role", "other"]},
            "interaction": {"kinds": ["zz-kind"]},
        }
    )
    assert edge.invocation is not None
    assert edge.invocation.strategy == "zz-strategy"
    assert EdgeTypeDescriptor(id="e", title="e").scheduling == "flow"
    for value in ("flow", "none", "entry", "exit"):
        EdgeTypeDescriptor(id="e", title="e", scheduling=value)
    with pytest.raises(ValidationError):
        EdgeTypeDescriptor.model_validate({"id": "e", "title": "e", "scheduling": "later"})
    node = NodeTypeDescriptor.model_validate(
        {
            "id": "zz",
            "title": "zz",
            "role": "zz-role",
            "executable": False,
            "binds": {"kind": "zz-kind", "field": "zz_ref"},
            "ui_hints": {"hidden": True},
        }
    )
    assert node.binds is not None
    assert node.binds.field == "zz_ref"
    assert NodeTypeDescriptor(id="t", title="t").executable is True


def test_delegation_strategy_descriptor_rules_are_data() -> None:
    d = DelegationStrategyDescriptor(
        id="zz",
        title="zz",
        member_fields=["model", "tools"],
        max_depth=1,
        requires_backend_capability="subagents",
        member_interaction_kinds=["zz-kind"],
    )
    assert d.allows_outgoing_flow is False
    assert DelegationStrategyDescriptor(id="h", title="h", member_fields=[], max_depth=None)
    with pytest.raises(ValidationError):
        DelegationStrategyDescriptor(id="x", title="x", member_fields=[], max_depth=0)


# ---------------------------------------------------------------- 이벤트


def test_actor_header_round_trips_on_generic_and_typed_events() -> None:
    generic = RunEvent.model_validate(_event("plugin.thing", {}, actor="backend-lead"))
    assert generic.actor == "backend-lead"
    typed = parse_run_event(
        _event("agent.text_delta", {"text": "x"}, actor="a1", node_path=["pl", "be"])
    )
    assert typed.actor == "a1"
    assert typed.node_path == ["pl", "be"]
    assert RunEvent.model_validate(_event("x", {})).actor is None


def test_new_known_event_types() -> None:
    for t in [
        "run.reply",
        "run.waiting",
        "node.resumed",
        "usage.rate_limit",
        "interaction.requested",
        "interaction.answered",
        "interaction.closed",
    ]:
        assert t in KNOWN_RUN_EVENT_TYPES, t
    assert len(set(KNOWN_RUN_EVENT_TYPES)) == len(KNOWN_RUN_EVENT_TYPES)


def test_run_reply_and_waiting_payloads() -> None:
    reply = parse_run_event(
        _event(
            "run.reply",
            {"edge_id": "a1", "node_id": "pl", "label": "중간", "final": False, "text": "t"},
        )
    )
    assert isinstance(reply, RunReplyEvent)
    assert reply.payload.final is False
    waiting = parse_run_event(_event("run.waiting", {"status": "waiting"}, node_path=[]))
    assert isinstance(waiting, RunLifecycleEvent)
    resumed = parse_run_event(_event("node.resumed", {"status": "running", "waited_ms": 1200}))
    assert isinstance(resumed, NodeStatusEvent)
    assert resumed.payload.waited_ms == 1200


def test_subagent_and_rate_limit_payloads() -> None:
    stopped = parse_run_event(
        _event(
            "agent.subagent_stopped",
            {
                "subagent_id": "t1",
                "name": "be",
                "tool_use_id": "tu1",
                "status": "completed",
                "usage": {"total_tokens": 42},
                "tool_uses": 3,
                "duration_ms": 900,
                "result_preview": "끝",
            },
            actor="backend-lead",
            node_path=["pl", "be"],
        )
    )
    assert isinstance(stopped, AgentSubagentEvent)
    assert stopped.payload.usage is not None
    assert stopped.payload.usage.total_tokens == 42
    rate = parse_run_event(
        _event(
            "usage.rate_limit", {"window": "zz-window", "status": "anything", "utilization": 0.5}
        )
    )
    assert isinstance(rate, UsageRateLimitEvent)
    assert rate.payload.window == "zz-window"


def test_interaction_events() -> None:
    requested = parse_run_event(
        _event("interaction.requested", {"interaction": _interaction(actor="a1")})
    )
    assert isinstance(requested, InteractionRequestedEvent)
    assert requested.payload.interaction.status == "pending"
    answered = parse_run_event(
        _event(
            "interaction.answered",
            {"interaction_id": "i1", "kind": "zz", "answered_by": "user", "response_preview": "ok"},
        )
    )
    assert isinstance(answered, InteractionAnsweredEvent)
    closed = parse_run_event(
        _event(
            "interaction.closed",
            {"interaction_id": "i1", "kind": "zz", "status": "expired", "reason": "interrupted"},
        )
    )
    assert isinstance(closed, InteractionClosedEvent)
    with pytest.raises(ValidationError):
        parse_run_event(
            _event(
                "interaction.closed", {"interaction_id": "i1", "kind": "zz", "status": "answered"}
            )
        )


# ---------------------------------------------------------------- 상호작용·채팅·WS


def test_interaction_status_and_respond_request() -> None:
    for status in ("pending", "answered", "expired", "cancelled"):
        Interaction.model_validate(_interaction(status=status))
    with pytest.raises(ValidationError):
        Interaction.model_validate(_interaction(status="waiting"))
    assert RespondInteractionRequest(response={"x": 1}).response == {"x": 1}
    with pytest.raises(ValidationError):
        RespondInteractionRequest.model_validate({})


def test_error_codes_for_chat_and_interactions() -> None:
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.INTERACTION_CLOSED] == 409
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.CONVERSATION_BUSY] == 409
    assert ErrorCodes.INTERACTION_CLOSED == "interaction_closed"
    assert "chat" in RUN_ORIGINS


def test_chat_turn_conversation_and_run() -> None:
    turn = ChatTurn.model_validate(
        {
            "run_id": "r1",
            "user_text": "안녕",
            "replies": [{"edge_id": "a1", "node_id": "pl", "agent_id": "pl", "text": "답"}],
            "interactions": [_interaction()],
            "status": "waiting",
        }
    )
    assert turn.interactions[0].kind == "pick-a-color"
    summary = ConversationSummary(
        id="c1", graph_id="g", created_at=0, updated_at=1, pending_interactions=2
    )
    assert summary.pending_interactions == 2
    assert QueuedMessage(position=1).queued is True
    run = Run.model_validate(
        {
            "id": "r1",
            "graph_id": "g",
            "graph_version": "v",
            "status": "waiting",
            "input": {},
            "origin": "chat",
            "conversation_id": "c1",
            "created_at": 0,
        }
    )
    assert run.conversation_id == "c1"


def test_ws_conversation_and_interaction_messages() -> None:
    conv = WsServerMessage.model_validate(
        {
            "type": "conversation.updated",
            "payload": {
                "conversation": {"id": "c", "graph_id": "g", "created_at": 0, "updated_at": 0}
            },
        }
    )
    assert conv.root.type == "conversation.updated"
    upd = WsServerMessage.model_validate(
        {"type": "interaction.updated", "payload": {"interaction": _interaction()}}
    )
    assert upd.root.type == "interaction.updated"


# ---------------------------------------------------------------- 리소스·사용량


def test_resource_definition_round_trip() -> None:
    doc = {
        "kind": "resource",
        "id": "team-guide",
        "type": "zz-type",
        "name": "팀 지침",
        "config": {"title": "T"},
        "content": {"file": "content.md", "media_type": "text/markdown"},
        "custom": True,
    }
    res = Resource.model_validate(doc)
    assert res.model_dump(mode="json", exclude_unset=True) == doc
    bundle = ResourceBundle(
        slots={"zz-slot": ["x"]},
        sources={"zz-slot": [BundleSource(ref="team-guide", layer="graph")]},
    )
    assert bundle.sources["zz-slot"][0].ref == "team-guide"


def test_usage_snapshot_does_not_invent_values() -> None:
    snap = UsageWindowSnapshot(source="zz", window="zz-window", observed_at=1.0)
    assert (snap.used_ratio, snap.used_tokens, snap.status, snap.resets_at) == (
        None,
        None,
        None,
        None,
    )


# ---------------------------------------------------- 화면 명세 1R.1 요청(U1·U2·U13·U16)


def test_issue_suggestions_carry_graph_patch() -> None:
    issue = Issue.model_validate(
        {
            "severity": "error",
            "code": "zz.no_way_in",
            "message": "m",
            "suggestions": [
                {
                    "id": "s1",
                    "label": "입구로",
                    "patch": {
                        "add_edges": [
                            {
                                "id": "e9",
                                "source": {"node": "u", "port": "p1"},
                                "target": {"node": "n", "port": "p2"},
                                "kind": "zz-entry",
                            }
                        ],
                        "remove_edge_ids": ["e1"],
                    },
                }
            ],
        }
    )
    patch = issue.suggestions[0].patch
    assert patch.add_edges[0].kind == "zz-entry"
    assert patch.remove_edge_ids == ["e1"]
    assert Issue(severity="info", code="c", message="m").suggestions == []


def test_edge_default_ports_and_usage_help() -> None:
    edge = EdgeTypeDescriptor.model_validate(
        {"id": "e", "title": "e", "default_ports": {"source": "zz-out", "target": "zz-in"}}
    )
    assert edge.default_ports is not None
    assert edge.default_ports.target == "zz-in"
    ws = WorkspaceSettings.model_validate(
        {"usage": {"stale_after_seconds": 600}, "ui": {"keybindings": {"zz.action": "Ctrl+K"}}}
    )
    assert ws.usage.stale_after_seconds == 600
    assert WorkspaceSettings().usage.stale_after_seconds is None
    assert WorkspaceSettings().ui.keybindings is None


def test_import_preview_and_request() -> None:
    preview = ImportPreview.model_validate(
        {
            "source": "zz-source",
            "candidates": [
                {
                    "id": "c1",
                    "path": "/x/CLAUDE.md",
                    "kind": "resource",
                    "resource_type": "zz-type",
                    "name": "지침",
                    "suggested_id": "claude-md",
                    "warnings": [{"code": "secret_suspected", "message": "m", "keys": ["env.K"]}],
                }
            ],
        }
    )
    assert preview.candidates[0].warnings[0].keys == ["env.K"]
    req = ImportRequest.model_validate({"source": "zz-source", "items": [{"candidate_id": "c1"}]})
    assert req.items[0].on_conflict == "rename"
    with pytest.raises(ValidationError):
        ImportRequest.model_validate(
            {"source": "s", "items": [{"candidate_id": "c1", "on_conflict": "merge"}]}
        )
    assert ApplyPresetRequest().on_conflict == "skip"


def test_qa_round_additions() -> None:
    issue = Issue(severity="warning", code="c", message="m", blocks_run=True)
    assert issue.blocks_run is True
    assert Issue(severity="error", code="c", message="m").blocks_run is None
    ws = WorkspaceSettings.model_validate(
        {"usage": {"primary_source_order": ["zz-a", "zz-b"]}, "chat": {"list_sort": "zz-sort"}}
    )
    assert ws.usage.primary_source_order == ["zz-a", "zz-b"]
    assert ws.chat.list_sort == "zz-sort"
    patch = UpdateConversationRequest.model_validate({"graph_id": "other-team"})
    assert patch.model_dump(exclude_unset=True) == {"graph_id": "other-team"}
    decision = ReviewDecision.model_validate(
        {"id": "zz-ok", "label": "좋음", "edit": True, "ui_hints": {"color": "zz-token"}}
    )
    assert decision.ui_hints is not None
    assert decision.ui_hints.color == "zz-token"


def test_ws_auth_close_codes_are_exported() -> None:
    assert (WS_CLOSE_UNAUTHORIZED, WS_CLOSE_FORBIDDEN) == (4401, 4403)
    assert WS_AUTH_CLOSE_CODES == (WS_CLOSE_UNAUTHORIZED, WS_CLOSE_FORBIDDEN)
    constants = build_schema()["x-constants"]
    assert constants["WS_CLOSE_UNAUTHORIZED"] == 4401
    assert constants["WS_CLOSE_FORBIDDEN"] == 4403
    assert constants["WS_AUTH_CLOSE_CODES"] == [4401, 4403]

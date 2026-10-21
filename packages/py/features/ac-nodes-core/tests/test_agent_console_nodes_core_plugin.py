"""ac-nodes-core 단위: entry point·디스크립터, 연결 종류 판단, 프롬프트 합치기, 실행 폴더 파일,
위임 방식 `sdk-subagents`."""

from __future__ import annotations

import base64
import importlib.metadata
import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    AgentSettings,
    BackendCapabilities,
    BackendDescriptor,
    EdgeSpec,
    Graph,
    ModelInfo,
    ResourceBundle,
    RunEvent,
)
from agent_console_nodes_core import (
    SDK_SUBAGENTS,
    AgentNode,
    DataEdge,
    HandoffEdge,
    MessageEdge,
    NodesCoreErrorCodes,
    PromptFormat,
    PromptInput,
    ReplyEdge,
    ResourceNode,
    SdkSubagentsStrategy,
    SubagentEdge,
    UserNode,
    UsesEdge,
    assemble_prompt,
    run_folder,
    safe_relative_name,
    subagent_specs,
    write_files,
)
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    INTERACTION_KINDS_GROUP,
    NODE_TYPES_GROUP,
    AgentRequest,
    AgentResult,
    BackendEventSink,
    CancelToken,
    DelegationMember,
    DelegationPlan,
    InteractivePort,
    NodeRunView,
    Reply,
    node_actor,
)
from agent_console_teams import team_plan

DIST = "agent-console-nodes-core"


def _eps(group: str) -> set[str]:
    return {
        ep.name for ep in importlib.metadata.distribution(DIST).entry_points if ep.group == group
    }


def test_entry_points_register_v2_types_only() -> None:
    assert _eps(NODE_TYPES_GROUP) == {"agent", "user", "resource", "team"}
    assert _eps(EDGE_TYPES_GROUP) == {
        "subagent",
        "delegate",
        "handoff",
        "data",
        "uses",
        "message",
        "reply",
        "ask_user",
        "loop",
        "when",
        "on_error",
    }
    assert _eps(DELEGATION_STRATEGIES_GROUP) == {SDK_SUBAGENTS}
    assert _eps(INTERACTION_KINDS_GROUP) == {"question", "tool_permission", "review"}
    for ep in importlib.metadata.distribution(DIST).entry_points:
        obj = ep.load()
        desc = getattr(obj, "descriptor", obj)  # 상호작용 종류는 디스크립터 객체를 바로 가리킨다
        assert desc.id == ep.name  # 이름 = 레지스트리 key = 디스크립터 id


def test_node_descriptors() -> None:
    a, u, r = AgentNode.descriptor, UserNode.descriptor, ResourceNode.descriptor
    assert a.binds is not None
    assert (a.binds.kind, a.binds.field) == ("agent", "agent_ref")
    assert r.binds is not None
    assert (r.binds.kind, r.binds.field) == ("resource", "resource_ref")
    assert u.binds is None
    assert (a.role, u.role, r.role) == ("agent", "user", "resource")
    assert (a.executable, u.executable, r.executable) == (True, True, False)
    assert not (u.ui_hints and u.ui_hints.hidden)
    assert u.static_ports is not None
    assert {p.name for p in u.static_ports.inputs} == {"hears", "asks", "review"}
    assert {p.name for p in u.static_ports.outputs} == {"says"}
    assert node_actor(AgentNode(), {"agent_ref": "pl"}) == "pl"


def test_edge_descriptors_connect_roles_and_ports() -> None:
    m, rp = MessageEdge.descriptor, ReplyEdge.descriptor
    assert m.scheduling == "entry"
    assert rp.scheduling == "exit"
    assert m.connects is not None
    assert "user" in m.connects.source
    assert rp.connects is not None
    assert "user" in rp.connects.target
    assert "user" in rp.connects.source  # 검토 반려 → 답변(§R14.6)
    sub = SubagentEdge.descriptor
    assert sub.scheduling == "none"
    assert sub.invocation is not None
    assert sub.invocation.strategy == SDK_SUBAGENTS
    assert UsesEdge.descriptor.scheduling == "none"
    assert UsesEdge.descriptor.invocation is None
    h = HandoffEdge.descriptor
    assert h.scheduling == "flow"
    assert h.connects is not None
    assert "user" in h.connects.target
    assert DataEdge.descriptor.id == "data"
    assert DataEdge.descriptor.scheduling == "flow"
    assert DataEdge.descriptor.ui_hints is not None
    assert DataEdge.descriptor.ui_hints.hidden
    for d in (m, rp, sub, h, UsesEdge.descriptor):
        assert d.default_ports is not None
        assert d.default_ports.source
        assert d.default_ports.target


def test_team_plan_reads_plugin_descriptors() -> None:
    """ac-teams가 이 플러그인의 디스크립터만으로 입구·답변·위임·첨부를 계산한다."""
    graph = Graph.model_validate(
        {
            "id": "g",
            "name": "g",
            "nodes": [
                {"id": "you", "type": "user"},
                {"id": "pl", "type": "agent", "config": {"agent_ref": "pl"}},
                {"id": "be", "type": "agent", "config": {"agent_ref": "be"}},
                {"id": "doc", "type": "resource", "config": {"resource_ref": "d"}},
            ],
            "edges": [
                _edge("m", "you", "says", "pl", "in", "message"),
                _edge("s", "pl", "delegates", "be", "delegated", "subagent"),
                _edge("u", "doc", "provides", "pl", "resources", "uses"),
                _edge("r", "pl", "out", "you", "hears", "reply"),
            ],
        }
    )
    nodes = [AgentNode.descriptor, UserNode.descriptor, ResourceNode.descriptor]
    edges = [
        MessageEdge.descriptor,
        ReplyEdge.descriptor,
        SubagentEdge.descriptor,
        UsesEdge.descriptor,
        HandoffEdge.descriptor,
    ]
    plan = team_plan(graph, node_types=nodes, edge_types=edges)
    assert plan.entry_nodes == ("pl",)
    assert plan.answer_nodes == ("pl",)
    assert plan.callees == frozenset({"be"})
    assert plan.delegates_of["pl"][0].strategy == SDK_SUBAGENTS
    assert [a.attachment.ref for a in plan.attachments_of["pl"]] == ["d"]


def _edge(
    eid: str, src: str, sp: str, dst: str, tp: str, kind: str, **config: Any
) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
        "config": config,
    }


def _spec(kind: str, sp: str = "out", **config: Any) -> EdgeSpec:
    return EdgeSpec.model_validate(_edge("e", "a", sp, "b", "in", kind, **config))


def _view(status: str = "succeeded", **outputs: Any) -> NodeRunView:
    return NodeRunView("a", "agent", status, MappingProxyType(outputs))  # type: ignore[arg-type]


# ---------------------------------------------------------------- 연결 종류


def test_handoff_passes_only_emitted_ports() -> None:
    edge = HandoffEdge()
    act = edge.activates(_view(out="v"), _spec("handoff"))
    assert act is not None
    assert act.value == "v"
    assert edge.activates(_view(alt="v"), _spec("handoff")) is None
    assert edge.activates(_view("failed", out="v"), _spec("handoff")) is None


def test_message_selects_input_key_and_template() -> None:
    edge = MessageEdge()
    run_input = {"text": "안녕", "request": "요청", "who": "민"}
    act = edge.activates(_view(says=run_input), _spec("message", sp="says"))
    assert act is not None
    assert act.value == "안녕"
    act = edge.activates(
        _view(says=run_input),
        _spec("message", sp="says", input_key="request", template="{who}: {message} {nope}"),
    )
    assert act is not None
    assert act.value == "민: 요청 {nope}"
    assert edge.activates(_view(says={"x": 1}), _spec("message", sp="says")) is None


def test_reply_builds_reply_from_config() -> None:
    edge = ReplyEdge()
    act = edge.activates(
        _view(out={"a": 1}), _spec("reply", label="중간", order=2, final=False, stream=False)
    )
    assert act is not None
    assert act.value == Reply(text='{"a": 1}', label="중간", order=2, final=False)
    plain = edge.activates(_view(out="t"), _spec("reply"))
    assert plain is not None
    assert plain.value == Reply(text="t")
    assert edge.activates(_view("failed", out="t"), _spec("reply")) is None


def test_reply_declares_label_chip_from_its_own_config() -> None:
    """E-4: 캔버스 라벨의 추가 문구는 디스크립터 칩 선언에서 나온다(편집기는 config 키를 모른다).

    첫 칩은 답변 이름(config `/label`)을 종류 title 뒤에 붙인다. 가리키는 위치는 이 연결 종류의
    config 스키마에 있고, 답변 계획이 읽는 위치(`reply_fields.label`)와 같다.
    """
    hints = ReplyEdge.descriptor.ui_hints
    assert hints is not None
    chips = hints.model_dump()["chips"]
    label_chip = chips[0]
    assert label_chip == {"value_pointer": "/label", "placement": "title"}
    assert ReplyEdge.descriptor.reply_fields is not None
    assert label_chip["value_pointer"] == ReplyEdge.descriptor.reply_fields.label
    assert "label" in ReplyEdge.descriptor.config_schema["properties"]
    # 기존 "중간 결과" 칩은 그대로 둔다
    assert chips[1]["when"] == {"config_path": "final", "equals": False}


def test_none_edges_never_pass() -> None:
    assert SubagentEdge().activates(_view(out="v"), _spec("subagent")) is None
    assert UsesEdge().activates(_view(out="v"), _spec("uses")) is None


# ---------------------------------------------------------------- 프롬프트


def test_assemble_prompt_default_and_template() -> None:
    one = [PromptInput("값", "a", "A")]
    many = [PromptInput("x", "a", "A"), PromptInput("y", "b")]
    assert assemble_prompt([]) == ""
    assert assemble_prompt(one) == "값"
    assert assemble_prompt(many) == "A: x\n\nb: y"
    assert (
        assemble_prompt(many, "{node} 받음:\n{inputs}\n(원문 {message})", message="m", node="N")
        == "N 받음:\nA: x\n\nb: y\n(원문 m)"
    )


def test_prompt_format_is_settings_data() -> None:
    """값별 형식·구분자·값 하나 형식은 설정(데이터)이다. 기본값은 계약 필드 기본값."""
    many = [
        PromptInput("x", "a", "A", port="in", edge="e1"),
        PromptInput("y", "b", port="in", edge="e2"),
    ]
    custom = PromptFormat(item="- {source} => {value}", separator="\n---\n")
    assert assemble_prompt(many, fmt=custom) == "- A => x\n---\n- b => y"
    all_vars = PromptFormat(
        item="{index}|{source}|{source_id}|{port}|{edge}|{value}", separator=";"
    )
    assert assemble_prompt(many, fmt=all_vars) == "1|A|a|in|e1|x;2|b|b|in|e2|y"
    one = [PromptInput("값", "a", "A")]
    assert assemble_prompt(one, fmt=PromptFormat(single="{source}: {value}")) == "A: 값"
    # 기본값은 계약 데이터에서 온다
    defaults = AgentSettings()
    assert defaults.prompt_input_template == "{source}: {value}"
    assert defaults.prompt_single_input_template == "{value}"
    assert defaults.prompt_input_separator == "\n\n"
    assert PromptFormat.of(AgentSettings(prompt_input_separator=" / ")).join(many) == "A: x / b: y"


# ---------------------------------------------------------------- 실행 폴더 파일


def _files(*items: Any) -> ResourceBundle:
    return ResourceBundle(slots={"files": list(items), "instructions": ["i"]})


def test_write_files_text_and_base64(tmp_path: Path) -> None:
    raw = bytes([0, 1, 2, 255])
    bundle = _files(
        {"name": "a/b.md", "content": "본문", "encoding": "utf-8", "media_type": "text/markdown"},
        {"name": "bin.dat", "content": base64.b64encode(raw).decode(), "encoding": "base64"},
        {"path": str(tmp_path / "r1" / "n1" / "kept.txt")},
        {"path": "/etc/passwd"},
    )
    folder = tmp_path / "r1" / "n1"
    out, issues = write_files(bundle, folder)
    # 경로만 있는 항목은 실행 폴더 안일 때만 넘긴다
    assert [i.code for i in issues] == [NodesCoreErrorCodes.FILES_UNSAFE_PATH]
    items = out.slots["files"]
    assert (folder / "a" / "b.md").read_text(encoding="utf-8") == "본문"
    assert (folder / "bin.dat").read_bytes() == raw
    assert items[0] == {
        "path": str((folder / "a" / "b.md").resolve()),
        "root": str(folder.resolve()),
        "name": "a/b.md",
        "media_type": "text/markdown",
    }
    assert items[2] == {"path": str(folder / "kept.txt")}
    assert len(items) == 3
    assert out.slots["instructions"] == ["i"]
    assert bundle.slots["files"][0]["content"] == "본문"  # 원본은 그대로


@pytest.mark.parametrize("name", ["../x", "/etc/x", "a/../../x", "c:x", "a\\b", "a/./b", "a\x00b"])
def test_write_files_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    out, issues = write_files(_files({"name": name, "content": "x"}), tmp_path / "f")
    assert out.slots["files"] == []
    assert [i.code for i in issues] == [NodesCoreErrorCodes.FILES_UNSAFE_PATH]
    assert not safe_relative_name(name)


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크 권한")
def test_write_files_rejects_symlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "link").symlink_to(outside, target_is_directory=True)
    (folder / "file.txt").symlink_to(outside / "victim.txt")
    out, issues = write_files(
        _files({"name": "link/x.txt", "content": "x"}, {"name": "file.txt", "content": "y"}),
        folder,
    )
    assert out.slots["files"] == []
    assert {i.code for i in issues} == {NodesCoreErrorCodes.FILES_UNSAFE_PATH}
    assert list(outside.iterdir()) == []


def test_write_files_invalid_items_and_no_slot(tmp_path: Path) -> None:
    out, issues = write_files(
        _files("x", {"name": "a", "content": "!!", "encoding": "base64"}), tmp_path / "f"
    )
    assert out.slots["files"] == []
    assert [i.code for i in issues] == [NodesCoreErrorCodes.FILES_INVALID_ITEM] * 2
    empty = ResourceBundle(slots={"instructions": ["i"]})
    assert write_files(empty, tmp_path / "g") == (empty, [])
    assert not (tmp_path / "g").exists()


def test_run_folder_rejects_unsafe_ids(tmp_path: Path) -> None:
    assert run_folder(tmp_path, "r", "n") == tmp_path / "r" / "n"
    assert run_folder(tmp_path, "..", "n") is None
    assert run_folder(tmp_path, "r", "a/b") is None


# ---------------------------------------------------------------- 위임 방식


def _member(node_id: str, **settings: Any) -> DelegationMember:
    return DelegationMember(
        node_id=node_id,
        edge_id=f"e-{node_id}",
        agent_id=f"agent-{node_id}",
        role="역할",
        delegate_when="언제",
        settings=AgentSettings.model_validate(settings),
    )


def _plan(*members: DelegationMember, backend: str = "b") -> DelegationPlan:
    return DelegationPlan(
        strategy=SDK_SUBAGENTS,
        delegator_node_id="lead",
        backend=backend,
        request=AgentRequest(agent=Agent(id="lead", name="L"), prompt="p"),
        members=list(members),
    )


def test_strategy_descriptor_and_validate() -> None:
    s = SdkSubagentsStrategy()
    d = s.descriptor
    assert (d.max_depth, d.allows_outgoing_flow, d.requires_backend_capability) == (
        1,
        False,
        "subagents",
    )
    assert d.member_interaction_kinds == ["tool_permission"]
    assert "resources" in d.member_fields
    assert "backend" not in d.member_fields
    assert [i.code for i in s.validate(_plan())] == [NodesCoreErrorCodes.DELEGATION_NO_MEMBERS]
    assert [i.code for i in s.validate(_plan(_member("x"), _member("x")))] == [
        NodesCoreErrorCodes.DELEGATION_DUPLICATE_MEMBER
    ]


def test_subagent_specs_use_member_fields() -> None:
    [spec] = subagent_specs(
        [_member("be", system_prompt="sp", model="m", tools=["Read"], backend="other")]
    )
    assert (spec.name, spec.actor, spec.prompt, spec.model, spec.tools) == (
        "be",
        "agent-be",
        "sp",
        "m",
        ["Read"],
    )
    assert spec.description == "역할 — 언제"


class _Ctx:
    """위임 방식이 쓰는 NodeContext 부분만 흉내 낸다."""

    def __init__(self, backend: Any) -> None:
        self.backends = {"b": backend}
        self.cancel = CancelToken()
        self.emitted: list[tuple[str, list[str] | None]] = []
        self.replies: list[tuple[str, dict[str, Any], str, str | None]] = []
        self.graph = Graph.model_validate(
            {"id": "g", "name": "g", "nodes": [{"id": "be", "type": "unknown"}]}
        )
        self.registries = SimpleNamespace(node_types={})

    def child_path(self, node_id: str) -> list[str]:
        return ["lead", node_id]

    async def emit(self, type: str, payload: Any = None, **kw: Any) -> RunEvent:
        self.emitted.append((type, kw.get("node_path")))
        return None  # type: ignore[return-value]

    async def emit_replies(
        self, node_id: str, outputs: Mapping[str, Any], *, status: str, actor: str | None
    ) -> list[RunEvent]:
        self.replies.append((node_id, dict(outputs), status, actor))
        return []

    async def request_input(self, req: Any) -> str:
        return f"passed-through:{req}"


class _Backend:
    def __init__(self, *, subagents: bool = True) -> None:
        self.descriptor = BackendDescriptor(
            id="b", title="b", capabilities=BackendCapabilities(subagents=subagents)
        )
        self.seen: list[AgentRequest] = []

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        self.seen.append(req)
        await sink.emit(
            "agent.message", {"role": "assistant", "text": "x"}, node_path=sink.child_path("be")
        )
        listener = getattr(sink, "on_subagent_result")  # noqa: B009
        await listener("be", text="전문", status="succeeded", actor=None, tool_use_id="t1")
        await listener("ghost", text="?", status="succeeded", actor=None, tool_use_id="t2")
        await listener("be", text="실패", status="failed", actor="x", tool_use_id="t3")
        assert isinstance(sink, InteractivePort)  # 명시 메서드(정적 조회로 보인다)
        assert await sink.request_input("r") == "passed-through:r"  # type: ignore[arg-type,comparison-overlap]
        return AgentResult(status="succeeded", text="done")


async def test_strategy_run_replies_per_result() -> None:
    backend = _Backend()
    ctx = _Ctx(backend)
    result = await SdkSubagentsStrategy().run(_plan(_member("be")), ctx)  # type: ignore[arg-type]
    assert result.text == "done"
    assert [s.name for s in backend.seen[0].subagents] == ["be"]
    assert ctx.emitted == [("agent.message", ["lead", "be"])]
    assert ctx.replies == [
        ("be", {"out": "전문"}, "succeeded", "agent-be"),
        ("be", {"out": "실패"}, "failed", "x"),
    ]


async def test_strategy_requires_subagent_capability() -> None:
    ctx = _Ctx(_Backend(subagents=False))
    result = await SdkSubagentsStrategy().run(_plan(_member("be")), ctx)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == NodesCoreErrorCodes.DELEGATION_BACKEND_UNSUPPORTED
    unknown = await SdkSubagentsStrategy().run(_plan(_member("be"), backend="zz"), ctx)  # type: ignore[arg-type]
    assert unknown.error is not None
    assert unknown.error.code == NodesCoreErrorCodes.DELEGATION_UNKNOWN_BACKEND


# ---------------------------------------------------------------- QA 추가: 실행 폴더 탈출 시도


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크 권한")
def test_qa_write_files_never_writes_outside_folder(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "dirlink").symlink_to(outside, target_is_directory=True)
    names = [
        "../outside/a.txt",
        "dirlink/a.txt",
        "dirlink/sub/a.txt",
        "a/",
        "",
        "//abs",
        str(outside / "abs.txt"),
        "..%2f..%2fx",
        "a/../../outside/b.txt",
        "..\\outside\\c.txt",
    ]
    out, _ = write_files(_files(*({"name": x, "content": "x"} for x in names)), folder)
    assert list(outside.rglob("*")) == []
    for item in out.slots["files"]:
        assert Path(item["path"]).resolve().is_relative_to(folder.resolve())


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크 권한")
def test_qa_write_files_rejects_symlinked_run_folder(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "runlink"
    link.symlink_to(outside, target_is_directory=True)
    out, issues = write_files(_files({"name": "a.txt", "content": "x"}), link)
    assert list(outside.iterdir()) == []
    assert out.slots["files"] == []
    assert issues


# ---------------------------------------------------------------- 2R.12 write_item_trees


def test_write_item_trees_writes_items_with_files_only(tmp_path: Path) -> None:
    from agent_console_contracts import ResourceBundle
    from agent_console_nodes_core import write_item_trees

    bundle = ResourceBundle(
        slots={
            "files": [{"name": "a.md", "content": "a"}],
            "kits": [
                {"name": "k1", "files": [{"name": "x/y.txt", "content": "y"}], "extra": 1},
                {"name": "k2"},
                "plain",
            ],
            "other": ["no trees"],
        }
    )
    out, issues = write_item_trees(bundle, tmp_path / "t")
    assert issues == []
    assert out.slots["files"] == [{"name": "a.md", "content": "a"}]  # 파일 칸은 건드리지 않음
    first, second, third = out.slots["kits"]
    root = (tmp_path / "t" / "kits" / "k1").resolve()
    assert first["root"] == str(root)
    assert first["tree_root"] == str((tmp_path / "t").resolve())
    assert first["extra"] == 1
    assert first["files"] == [{"path": str(root / "x" / "y.txt"), "name": "x/y.txt"}]
    assert (root / "x" / "y.txt").read_text() == "y"
    assert second == {"name": "k2"}
    assert third == "plain"
    assert out.slots["other"] == ["no trees"]
    assert write_item_trees(ResourceBundle(slots={"x": []}), tmp_path / "n")[1] == []


@pytest.mark.parametrize("name", ["../up", "a/b", "", ".."])
def test_write_item_trees_rejects_unsafe_item_names(tmp_path: Path, name: str) -> None:
    from agent_console_contracts import ResourceBundle
    from agent_console_nodes_core import write_item_trees

    bundle = ResourceBundle(
        slots={"kits": [{"name": name, "files": [{"name": "f", "content": "x"}]}]}
    )
    out, issues = write_item_trees(bundle, tmp_path / "t")
    assert issues
    assert issues[0].code == "files.unsafe_path"
    assert "files" not in out.slots["kits"][0]
    assert not (tmp_path / "f").exists()


def test_write_item_trees_rejects_file_escape_inside_item(tmp_path: Path) -> None:
    from agent_console_contracts import ResourceBundle
    from agent_console_nodes_core import write_item_trees

    bundle = ResourceBundle(
        slots={"kits": [{"name": "k", "files": [{"name": "../../evil", "content": "x"}]}]}
    )
    out, issues = write_item_trees(bundle, tmp_path / "t")
    assert issues
    assert issues[0].details["slot"] == "kits"
    assert out.slots["kits"][0]["files"] == []
    assert not (tmp_path / "evil").exists()


def test_write_files_reserved_first_part(tmp_path: Path) -> None:
    out, issues = write_files(
        _files({"name": "_bundle/x.md", "content": "x"}, {"name": "ok.md", "content": "o"}),
        tmp_path / "f",
        reserved=("_bundle",),
    )
    assert [i.code for i in issues] == ["files.unsafe_path"]
    assert [item["name"] for item in out.slots["files"]] == ["ok.md"]


def test_lookup_unavailable_message_hints_cause() -> None:
    """3R.16: `agent.lookup_unavailable` 메시지는 데이터 상수이고 원인 힌트를 담는다."""
    from agent_console_nodes_core import AGENT_LOOKUP_UNAVAILABLE_MESSAGE

    assert "link-runs-teams" in AGENT_LOOKUP_UNAVAILABLE_MESSAGE
    assert "/modules" in AGENT_LOOKUP_UNAVAILABLE_MESSAGE

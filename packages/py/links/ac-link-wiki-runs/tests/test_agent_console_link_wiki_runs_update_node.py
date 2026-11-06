"""노드 종류 ``wiki-update``(7R.17): 디스크립터·검증·엔진 수준 실행(fake-agent, SDK 호출 없음).

팀 구성: 사람 → (입구) → 에이전트(fake) → (넘기기) → 위키 고치기 → (답변) → 사람. 위키·규칙은 이
테스트의 데이터(메모리 저장소)만 쓴다.
"""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    ErrorCodes,
    Graph,
    KnownIssueCodes,
    KnownUiWidgets,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    WikiEventPayload,
    WikiRulesDefinition,
)
from agent_console_link_wiki_runs import (
    NODE_TYPE_ID,
    WIKI_UPDATE_SERVICE,
    WIKI_UPDATE_VARIABLES,
    WikiNodeServices,
    WikiUpdateCodes,
    WikiUpdateConfig,
    WikiUpdateNode,
    render_values,
)
from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
from agent_console_nodes_core import AGENT_LOOKUP, WORKSPACE_SETTINGS
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    INTERACTION_KINDS_GROUP,
    NODE_TYPES_GROUP,
    GraphRuntime,
    Registries,
    Services,
    as_node_type,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock
from agent_console_wiki import (
    InMemoryWikiHistory,
    RulesDocument,
    WikiRepository,
    WikiSecretPolicy,
    compile_syntax,
    effective_syntax,
    merge_rules,
)
from agent_console_wiki.testing import MemoryWikiPages

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
DISTS = ("agent-console-nodes-core", "agent-console-delegation-host")
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)
WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake-agent"}})
RESULT = "구현 완료: 로그인 API 추가"


def _registries() -> Registries:
    regs = Registries()
    eps = [
        ep
        for dist in DISTS
        for ep in importlib.metadata.distribution(dist).entry_points
        if ep.group in GROUPS
    ]
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    regs.backends.register("fake-agent", FakeBackend(ids=SequentialIds("s"), clock=StepClock()))
    regs.node_types.register(NODE_TYPE_ID, as_node_type(WikiUpdateNode))
    return regs


def _agent(response: str) -> Agent:
    return Agent.model_validate(
        {"id": "dev", "name": "개발", "backend_options": {"default": {"response": response}}}
    )


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
        "config": {},
    }


def team(**config: Any) -> Graph:
    """사람 → dev(에이전트) → keep(wiki-update) → 사람."""
    return Graph.model_validate(
        {
            "id": "team",
            "name": "team",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "dev", "type": "agent", "label": "dev", "config": {"agent_ref": "dev"}},
                {"id": "keep", "type": NODE_TYPE_ID, "label": "기록", "config": config},
            ],
            "edges": [
                _edge("m", "you", "says", "dev", "in", "message"),
                _edge("h", "dev", "out", "keep", "in", "handoff"),
                _edge("r", "keep", "out", "you", "hears", "reply"),
            ],
        }
    )


class Stack:
    def __init__(self, service: StaticWikiService | None, response: str = RESULT) -> None:
        self.registries = _registries()
        self.recorder = InMemoryRecorder()
        items: dict[Any, Any] = {
            AGENT_LOOKUP: {"dev": _agent(response)}.get,
            WORKSPACE_SETTINGS: WORKSPACE,
        }
        items.update(WikiNodeServices(lambda: service).services())
        self.services = Services(items)
        self.runs = 0

    def runtime(self) -> GraphRuntime:
        self.runs += 1
        return GraphRuntime(
            self.registries,
            self.recorder,
            clock=StepClock(start=1_700_000_000.0),
            ids=SequentialIds(f"run{self.runs}-"),
            services=self.services,
        )

    async def run(self, graph: Graph, project_id: str | None = None) -> Run:
        return await self.runtime().run(graph, {"text": "시작"}, project_id=project_id)

    def events(self, run: Run, prefix: str) -> list[RunEvent]:
        return [e for e in self.recorder.events.list(run.id) if e.type.startswith(prefix)]

    def node_run(self, run: Run, node_id: str) -> Any:
        [found] = [n for n in self.recorder.runs.list_node_runs(run.id) if n.node_id == node_id]
        return found


def _rules() -> Any:
    rules = WikiRulesDefinition.model_validate(
        {
            "kind": "wiki-rules",
            "id": "house",
            "name": "집 규칙",
            "write_rules": [
                {"id": "no-temp", "deny_patterns": [r"\bTEMPNOTE\b"], "message": "임시 메모 금지"}
            ],
        }
    )
    return merge_rules(["house"], [RulesDocument("house", rules, {})])


def _service(repo: WikiRepository, space: str | None = None) -> StaticWikiService:
    return StaticWikiService({space: {"notes": repo}})


# ---------------------------------------------------------------- 등록·디스크립터


def test_entry_point_declared_with_descriptor_id() -> None:
    meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    eps = meta["project"]["entry-points"][NODE_TYPES_GROUP]
    assert eps == {NODE_TYPE_ID: "agent_console_link_wiki_runs.update_node:WikiUpdateNode"}
    assert WikiUpdateNode.descriptor.id == NODE_TYPE_ID


def test_descriptor_schema_and_team_meaning() -> None:
    desc = WikiUpdateNode.descriptor
    assert desc.role == "agent"
    assert desc.binds is None
    assert desc.opens_session is False
    assert desc.static_ports is not None
    assert [p.name for p in desc.static_ports.inputs] == ["in"]
    assert [p.name for p in desc.static_ports.outputs] == ["out"]
    props = desc.config_schema["properties"]
    assert props["mode"]["enum"] == ["append", "section", "replace"]
    assert props["mode"]["default"] == "append"
    assert props["wiki"]["x-ui"]["widget"] == KnownUiWidgets.WIKI_REF
    names = [v["name"] for v in props["content"]["x-ui"]["variables"]]
    assert names == [n for n, _ in WIKI_UPDATE_VARIABLES]
    assert desc.config_schema["required"] == ["wiki", "path"]


def test_render_values_object_keys_and_fixed_names_win() -> None:
    values = render_values({"input": "x", "title": "T"}, node_id="n", run_id="r", at=0.0)
    assert values["title"] == "T"
    assert values["input"] == '{"input": "x", "title": "T"}'
    assert (values["node_id"], values["run_id"], values["graph_id"]) == ("n", "r", "")
    assert len(values["date"]) == 10
    assert render_values(None)["input"] == ""


def test_node_services_only_when_service_present() -> None:
    assert WikiNodeServices(lambda: None).services() == {}
    service = StaticWikiService({None: {}})
    assert WikiNodeServices(lambda: service).services() == {WIKI_UPDATE_SERVICE: service}


# ---------------------------------------------------------------- 검증


def test_validation_warns_without_service_and_requires_section() -> None:
    stack = Stack(None)
    runtime = stack.runtime()
    issues = runtime.validate(team(wiki="notes", path="log"), services=stack.services)
    [warn] = [i for i in issues if i.code == WikiUpdateCodes.UNAVAILABLE]
    assert warn.code == KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE
    assert warn.severity == "warning"

    ok = Stack(_service(memory_repository("notes")))
    bad = ok.runtime().validate(
        team(wiki="notes", path="log", mode="section"), services=ok.services
    )
    assert [i.code for i in bad if i.severity == "error"] == [ErrorCodes.VALIDATION_FAILED]
    assert not [i for i in bad if i.code == WikiUpdateCodes.UNAVAILABLE]
    clean = ok.runtime().validate(team(wiki="notes", path="log"), services=ok.services)
    assert [i for i in clean if i.severity == "error"] == []


# ---------------------------------------------------------------- 실행


async def test_appends_section_after_agent_result() -> None:
    repo = memory_repository("notes", files={"log.md": "# 작업 기록\n- 처음\n"})
    service = _service(repo)
    stack = Stack(service)
    graph = team(
        wiki="notes", path="log", content="## {node_id}\n{input}\n", message="실행 {run_id}"
    )
    run = await stack.run(graph)
    assert run.status == "completed", run.error

    page = repo.current("log")
    assert page is not None
    assert page.text == f"# 작업 기록\n- 처음\n## keep\n{RESULT}\n"
    out = stack.node_run(run, "keep").outputs["out"]
    assert (out["wiki"], out["path"], out["created"], out["changed"]) == (
        "notes",
        "log",
        False,
        True,
    )
    assert out["sha256"] == page.content_hash

    [event] = stack.events(run, "wiki.")
    assert event.type == "wiki.write"
    assert event.node_path == ["keep"]
    payload = WikiEventPayload.model_validate(event.payload)
    assert (payload.status, payload.wiki, payload.path) == ("ok", "notes", "log")
    assert payload.sha256 == page.content_hash
    assert RESULT not in repr(event.payload)

    assert repo.history is not None
    version = repo.history.list("notes", "log").items[0]
    author = version.author
    assert (author.kind, author.label, author.node_id) == ("system", "keep", "keep")
    assert (author.run_id, author.root_run_id, author.graph_id) == (run.id, run.id, "team")
    assert author.agent_id is None
    assert version.message == f"실행 {run.id}"
    assert [(n.wiki_id, n.paths) for n in service.notices] == [("notes", ("log",))]


async def test_section_and_path_template() -> None:
    repo = memory_repository(
        "notes", files={"status.md": "# 상태\n## 최근\n옛 값\n## 다음\n그대로\n"}
    )
    stack = Stack(_service(repo))
    run = await stack.run(team(wiki="notes", path="status", mode="section", section="최근"))
    assert run.status == "completed", run.error
    page = repo.current("status")
    assert page is not None
    assert page.text == f"# 상태\n## 최근\n{RESULT}\n## 다음\n그대로\n"

    run = await stack.run(team(wiki="notes", path="daily/{date}", mode="replace"))
    assert run.status == "completed", run.error
    [created] = [p for p in repo.list_pages().items if p.path.startswith("daily/")]
    assert len(created.path) == len("daily/YYYY-MM-DD")


async def test_missing_section_fails_with_reason() -> None:
    repo = memory_repository("notes", files={"status.md": "# 상태\n"})
    stack = Stack(_service(repo))
    run = await stack.run(team(wiki="notes", path="status", mode="section", section="없음"))
    node = stack.node_run(run, "keep")
    assert node.status == "failed"
    assert node.error.code == KnownIssueCodes.WIKI_NOT_FOUND
    assert node.error.details["reason"] == "section_not_found"
    [event] = stack.events(run, "wiki.")
    assert event.payload["status"] == "not_found"


async def test_rule_rejection_fails_node_with_reason() -> None:
    repo = memory_repository("notes", rules=_rules())
    stack = Stack(_service(repo), response="TEMPNOTE 지울 것")
    run = await stack.run(team(wiki="notes", path="log"))
    node = stack.node_run(run, "keep")
    assert node.status == "failed"
    assert node.error.code == KnownIssueCodes.WIKI_RULE_REJECTED
    assert node.error.details["rule_id"] == "no-temp"
    assert "TEMPNOTE 지울" not in repr(node.error.model_dump())
    [event] = stack.events(run, "wiki.")
    assert (event.payload["status"], event.payload["rule_ids"]) == ("rule_rejected", ["no-temp"])
    assert repo.current("log") is None


TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def _secret_repo(modes: dict[str, str]) -> WikiRepository:
    return WikiRepository(
        MemoryWikiPages(),
        wiki_id="notes",
        syntax=compile_syntax(effective_syntax()),
        history=InMemoryWikiHistory(),
        secrets=WikiSecretPolicy(modes=modes),
    )


async def test_secret_rejected_when_policy_rejects_system() -> None:
    repo = _secret_repo({"user": "warn", "agent": "reject", "system": "reject"})
    stack = Stack(_service(repo), response=f"토큰 {TOKEN}")
    run = await stack.run(team(wiki="notes", path="log"))
    node = stack.node_run(run, "keep")
    assert node.status == "failed"
    assert node.error.code == KnownIssueCodes.WIKI_SECRET_REJECTED
    assert node.error.details["lines"] == [1]
    assert TOKEN not in repr(node.error.model_dump())
    [event] = stack.events(run, "wiki.")
    assert event.payload["status"] == "secret_rejected"
    assert repo.current("log") is None


async def test_secret_rejected_under_default_settings() -> None:
    """계약 0.14.1 기본값(``WikiSettings.secret_scan``에 ``system: reject``): 설정을 고치지
    않으면 노드(쓴 주체 system)가 옮긴 에이전트 출력의 평문 비밀은 거부한다 — 에이전트가 직접
    쓸 때와 같다."""
    assert WikiSecretPolicy().mode(KnownWikiAuthorKinds.SYSTEM) == "reject"
    assert WikiSecretPolicy().mode(KnownWikiAuthorKinds.AGENT) == "reject"
    repo = WikiRepository(
        MemoryWikiPages(),
        wiki_id="notes",
        syntax=compile_syntax(effective_syntax()),
        history=InMemoryWikiHistory(),
    )
    stack = Stack(_service(repo), response=f"토큰 {TOKEN}")
    run = await stack.run(team(wiki="notes", path="log"))
    node = stack.node_run(run, "keep")
    assert node.status == "failed"
    assert node.error.code == KnownIssueCodes.WIKI_SECRET_REJECTED
    assert TOKEN not in repr(node.error.model_dump())
    [event] = stack.events(run, "wiki.")
    assert event.payload["status"] == "secret_rejected"
    assert TOKEN not in repr(event.payload)
    assert repo.current("log") is None


async def test_secret_warns_under_user_fallback() -> None:
    """정책에 ``system`` 키가 없으면(사용자가 secret_scan을 직접 적어 뺌) ``user`` 값 warn — 쓰고
    경고 1건."""
    repo = _secret_repo({"user": "warn", "agent": "reject"})
    stack = Stack(_service(repo), response=f"토큰 {TOKEN}")
    run = await stack.run(team(wiki="notes", path="log"))
    assert stack.node_run(run, "keep").status == "succeeded"
    codes = [e.payload["details"].get("code") for e in stack.events(run, "log.warning")]
    assert codes == [KnownIssueCodes.WIKI_SECRET_SUSPECT]
    assert all(TOKEN not in repr(e.payload) for e in stack.events(run, "log.warning"))


async def test_page_template_for_new_page() -> None:
    rules = WikiRulesDefinition.model_validate(
        {
            "kind": "wiki-rules",
            "id": "house",
            "name": "집 규칙",
            "page_templates": [{"id": "daily", "title": "일지", "file": "daily.md"}],
        }
    )
    merged = merge_rules(["house"], [RulesDocument("house", rules, {"daily.md": "# {title}\n"})])
    repo = memory_repository("notes", rules=merged)
    stack = Stack(_service(repo))
    graph = team(wiki="notes", path="journal", page_template="daily", title="첫 기록")
    run = await stack.run(graph)
    assert run.status == "completed", run.error
    page = repo.current("journal")
    assert page is not None
    assert page.text == f"# 첫 기록\n{RESULT}\n"
    # 있는 페이지에는 틀을 쓰지 않고 덧붙인다
    run = await stack.run(graph)
    assert run.status == "completed", run.error
    page = repo.current("journal")
    assert page is not None
    assert page.text == f"# 첫 기록\n{RESULT}\n{RESULT}\n"


async def test_project_space_only() -> None:
    a = memory_repository("notes")
    b = memory_repository("notes")
    service = StaticWikiService({"proj-a": {"notes": a}, "proj-b": {"notes": b}})
    stack = Stack(service)
    run = await stack.run(team(wiki="notes", path="log"), project_id="proj-a")
    assert run.status == "completed", run.error
    assert a.current("log") is not None
    assert b.current("log") is None
    assert [n.space for n in service.notices] == ["proj-a"]

    run = await stack.run(team(wiki="notes", path="log"))  # 단독 공간 없음 → 실패
    node = stack.node_run(run, "keep")
    assert node.status == "failed"
    assert node.error.code == KnownIssueCodes.WIKI_WIKI_UNAVAILABLE
    [event] = stack.events(run, "wiki.")
    assert event.payload["status"] == "wiki_unavailable"


async def test_without_service_node_skipped_with_one_warning() -> None:
    stack = Stack(None)
    run = await stack.run(team(wiki="notes", path="log"))
    assert run.status == "completed", run.error
    node = stack.node_run(run, "keep")
    assert node.status == "skipped"
    assert node.error.code == WikiUpdateCodes.UNAVAILABLE
    warnings = [
        e
        for e in stack.events(run, "log.warning")
        if e.payload["details"].get("code") == WikiUpdateCodes.UNAVAILABLE
    ]
    assert len(warnings) == 1
    assert stack.events(run, "wiki.") == []
    assert stack.events(run, "run.reply") == []


def test_config_defaults() -> None:
    cfg = WikiUpdateConfig.model_validate({"wiki": "notes", "path": "log"})
    assert (cfg.mode, cfg.content, cfg.section, cfg.page_template) == (
        "append",
        "{input}\n",
        None,
        None,
    )
    with pytest.raises(ValidationError, match="extra"):
        WikiUpdateConfig.model_validate({"wiki": "notes", "path": "log", "extra": 1})


SLUG_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"


def test_ids_use_contract_slug() -> None:
    """위키·틀 id는 계약 공개 별칭 ``Slug``로 검증한다(정규식 복사 없음, 계약 0.14.1)."""
    props = WikiUpdateNode.descriptor.config_schema["properties"]
    assert props["wiki"]["pattern"] == SLUG_PATTERN
    assert [b.get("pattern") for b in props["page_template"]["anyOf"]] == [SLUG_PATTERN, None]
    for bad in ({"wiki": "-x", "path": "log"}, {"wiki": "a", "path": "p", "page_template": "a b"}):
        with pytest.raises(ValidationError, match="pattern"):
            WikiUpdateConfig.model_validate(bad)

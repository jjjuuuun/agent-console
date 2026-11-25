"""검증 경로 + 저장 전 정의 검사(``definitions.checks``)의 경고·정보(5.2R.36 결함 B).

제공 모듈은 이 패키지가 모른다 — 여기서는 같은 포트를 주는 가짜 모듈과 테스트 안에서만 쓰는 코드
(``x.warning``·``x.suggest``)로 확인한다. 실제 모듈과의 조립은 ``tests/integration``이 확인한다.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import Graph, Issue, IssueSuggestion
from agent_console_link_runs_teams import (
    DEFINITION_CHECKS,
    DefinitionCheck,
    SpaceDefinitionCheck,
    definition_check_issues,
    module,
    with_definition_checks,
)
from agent_console_link_runs_teams.testing import local_runs_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ModuleContext,
    ModuleParts,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, load_registries

API = "/api/v1"
TOKEN = "t" * 32
CHECKS_ID = "scope-checks"
WARN_CODE = "x.warning"
SUGGESTION_ID = "x.suggest"
CHECK_CODES = frozenset({WARN_CODE, "x.info", "x.error"})


def _graph(graph_id: str) -> dict[str, Any]:
    return {
        "id": graph_id,
        "name": graph_id,
        "nodes": [{"id": "you", "type": "user", "label": "나"}],
        "edges": [],
    }


class ScopeLikeCheck:
    """저장 전 검사 흉내: 팀 구성 문서마다 경고(제안 포함)·정보·error를 하나씩 낸다."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict[str, Any]]] = []

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        self.seen.append((kind, dict(document)))
        suggestion = IssueSuggestion(id=SUGGESTION_ID, label="고치기")
        return [
            Issue(
                severity="warning",
                code=WARN_CODE,
                message="경고",
                details={"kind": "agent", "id": "pa-2"},
                suggestions=[suggestion],
            ),
            Issue(severity="info", code="x.info", message="정보"),
            Issue(severity="error", code="x.error", message="저장 경로가 거부한다"),
        ]


class BrokenCheck:
    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        raise RuntimeError("검사 실패")


def _checks_module(*checks: DefinitionCheck) -> Any:
    def build(ctx: ModuleContext) -> ModuleParts:
        for check in checks:
            ctx.provide(DEFINITION_CHECKS, check)
        return ModuleParts()

    return fake_module(CHECKS_ID, provides=[DEFINITION_CHECKS], on_build=build)


def _base(tmp_path: Path) -> BaseServices:
    registries = Registries()
    load_registries(registries)
    return BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )


@contextmanager
def _client(
    tmp_path: Path, *modules: Any, config: ModulesConfig | None = None
) -> Iterator[tuple[TestClient, Assembly]]:
    assembly = assemble(list(modules), config, base=_base(tmp_path))
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def test_validate_appends_check_warnings_and_suggestion(tmp_path: Path) -> None:
    """수용 기준: 저장 전 검사의 경고(제안 포함)·정보가 검증 결과에 붙고, error는 붙지 않는다."""
    check = ScopeLikeCheck()
    with _client(tmp_path, local_runs_module(), module, _checks_module(check)) as (client, _a):
        body = Graph.model_validate(_graph("g-shared")).model_dump(mode="json")
        issues = client.post(f"{API}/graphs/g-shared/validate", json=body).json()
    by_code = {i["code"]: i for i in issues if i["code"] in CHECK_CODES}
    assert set(by_code) == {WARN_CODE, "x.info"}
    warning = by_code[WARN_CODE]
    assert warning["severity"] == "warning"
    assert [s["id"] for s in warning["suggestions"]] == [SUGGESTION_ID]
    assert warning["details"] == {"kind": "agent", "id": "pa-2"}
    [(kind, document)] = check.seen
    assert kind == "graph"
    assert document["id"] == "g-shared"


def test_validate_without_checks_module_is_unchanged(tmp_path: Path) -> None:
    """수용 기준: 검사 제공 모듈이 꺼지면 검증 결과는 엔진 + 팀 규칙 그대로다."""
    body = Graph.model_validate(_graph("g-shared")).model_dump(mode="json")
    config = ModulesConfig(disabled=[CHECKS_ID])
    modules = (local_runs_module(), module, _checks_module(ScopeLikeCheck()))
    with _client(tmp_path / "off", *modules, config=config) as (client, assembly):
        assert assembly.status(CHECKS_ID).state.value == "disabled"  # type: ignore[union-attr]
        off = client.post(f"{API}/graphs/g-shared/validate", json=body).json()
    with _client(tmp_path / "none", local_runs_module(), module) as (client, _a):
        none = client.post(f"{API}/graphs/g-shared/validate", json=body).json()
    assert off == none
    assert not {i["code"] for i in off} & CHECK_CODES


def test_broken_check_is_skipped(tmp_path: Path) -> None:
    modules = (local_runs_module(), module, _checks_module(BrokenCheck(), ScopeLikeCheck()))
    with _client(tmp_path, *modules) as (client, _a):
        body = Graph.model_validate(_graph("g")).model_dump(mode="json")
        response = client.post(f"{API}/graphs/g/validate", json=body)
    assert response.status_code == 200
    codes = {i["code"] for i in response.json()} & CHECK_CODES
    assert codes == {WARN_CODE, "x.info"}


def test_definition_check_issues_dedupes_and_filters() -> None:
    graph = Graph.model_validate(_graph("g"))
    check = ScopeLikeCheck()
    existing = [Issue(severity="info", code="x.info", message="이미 있음")]
    found = definition_check_issues(graph, [check, check], existing=existing)
    assert [i.code for i in found] == [WARN_CODE]
    assert definition_check_issues(graph, []) == []
    errors_too = definition_check_issues(graph, [check], severities={"error"})
    assert [i.code for i in errors_too] == ["x.error"]


class SpaceAwareCheck:
    """공간 기준 검사(선택 메서드 ``space_issues``)를 주는 검사."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        return [Issue(severity="warning", code="lib", message="라이브러리 기준")]

    def space_issues(self, space: str, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        return [Issue(severity="warning", code=f"space.{space}", message="공간 기준")]


def test_definition_check_issues_space_uses_space_method_when_offered() -> None:
    """FU.3: ``space``가 있으면 ``space_issues``가 있는 검사는 그 공간 기준, 없으면 ``issues``."""
    graph = Graph.model_validate(_graph("g"))
    aware = SpaceAwareCheck()
    assert isinstance(aware, SpaceDefinitionCheck)
    assert not isinstance(ScopeLikeCheck(), SpaceDefinitionCheck)
    assert [i.code for i in definition_check_issues(graph, [aware])] == ["lib"]
    spaced = definition_check_issues(graph, [aware, ScopeLikeCheck()], space="p1")
    assert [i.code for i in spaced] == ["space.p1", WARN_CODE, "x.info"]
    joined = with_definition_checks(graph, [], lambda: [aware], space="p1")
    assert [i.code for i in joined] == ["space.p1"]


@pytest.mark.parametrize("check", [ScopeLikeCheck(), BrokenCheck()])
def test_checks_satisfy_port_protocol(check: object) -> None:
    assert isinstance(check, DefinitionCheck)

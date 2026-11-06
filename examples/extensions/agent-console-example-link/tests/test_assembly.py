"""모듈 조립(테스트 호스트 = 모듈 키트): 정의·리소스·실행 모듈 + 노트 대역 모듈 + 이 연동.

- 모두 켜짐 → fake-agent 실행에서 에이전트가 노트 도구를 받아 읽고, 이벤트가 남는다.
- 노트 모듈을 끔 → 이 연동만 ``unsatisfied``(``example_notes.reader``), 실행은 정상 +
  "적용하지 못한 칸" 경고 1건.
- 실행 모듈을 끔 → 이 연동만 ``unsatisfied``(``runs.reader``), 나머지 모듈과 REST는 정상.

정의·실행 모듈과 다른 연동은 dev 의존(``agent-console-server``가 함께 설치한다)이다. 이 패키지
코드는 import하지 않는다. 리소스 종류는 설치하지 않았으므로 레지스트리에 직접 등록한다(설치하면
entry point).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from notes_helpers import API, NOTE, RTYPE, TEXT, of, run_team, slot_warnings, write_workspace

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_example_link import (
    MODULE_ID,
    module,
    notes_slot,
    register,
)
from agent_console_example_link.testing import (
    STATIC_NOTES_MODULE_ID,
    StaticNote,
    StaticNotesModule,
    StaticNotesReader,
)
from agent_console_link_definitions_teams import module as definitions_teams
from agent_console_link_runs_teams import module as runs_teams
from agent_console_mod_definitions import module as definitions
from agent_console_mod_resources import module as resources
from agent_console_mod_runs import module as runs
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ModuleReport,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_runtime import Registries, load_registries

TOKEN = "t" * 32


def _status(assembly: Assembly, module_id: str) -> ModuleReport:
    report = assembly.status(module_id)
    assert report is not None, module_id
    return report


@contextmanager
def _client(
    tmp_path: Path, *, disabled: tuple[str, ...] = ()
) -> Iterator[tuple[TestClient, Assembly]]:
    registries = Registries()
    load_registries(registries)
    register(registries)  # 설치하면 entry point agent_console.resource_types가 한다
    ws = tmp_path / "ws"
    write_workspace(ws)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=ws, state=tmp_path / "state"),
        registries=registries,
    )
    notes = StaticNotesModule(StaticNotesReader({None: (StaticNote("n1", NOTE, ("회의",)),)}))
    assembly = assemble(
        [definitions, resources, runs, runs_teams, definitions_teams, notes, module],
        ModulesConfig(disabled=list(disabled)),
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def test_all_on_agent_reads_notes(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, assembly):
        assert _status(assembly, MODULE_ID).state == "active"
        run, events = run_team(client)
        assert run["status"] == "completed", run
        [event] = of(events, TEXT.event_type)
        assert (event["payload"]["status"], event["payload"]["count"]) == ("ok", 1)
        assert NOTE not in json.dumps(event["payload"], ensure_ascii=False)
        [reply] = of(events, "run.reply")
        assert reply["payload"]["text"].startswith("[succeeded]")
        assert NOTE in reply["payload"]["text"]
        assert slot_warnings(events) == []


def test_notes_module_off_only_link_unsatisfied(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=(STATIC_NOTES_MODULE_ID,)) as (client, assembly):
        report = _status(assembly, MODULE_ID)
        assert report.state == "unsatisfied"
        assert report.missing == ("example_notes.reader",)
        others = [r for r in assembly.report if r.id not in (MODULE_ID, STATIC_NOTES_MODULE_ID)]
        assert others
        assert all(r.state == "active" for r in others), [(r.id, r.state) for r in others]
        run, events = run_team(client)
        assert run["status"] == "completed", run
        assert of(events, TEXT.event_type) == []
        [warning] = slot_warnings(events)
        assert (warning["slot"], warning["resources"]) == (notes_slot(RTYPE), ["notes"])


def test_runs_module_off_only_link_unsatisfied(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=("mod-runs",)) as (client, assembly):
        report = _status(assembly, MODULE_ID)
        assert report.state == "unsatisfied"
        assert "runs.reader" in report.missing
        assert _status(assembly, STATIC_NOTES_MODULE_ID).state == "active"
        assert _status(assembly, "mod-definitions").state == "active"
        assert client.get(f"{API}/agents").status_code == 200
        assert client.post(f"{API}/runs", json={"graph_id": "solo"}).status_code == 404

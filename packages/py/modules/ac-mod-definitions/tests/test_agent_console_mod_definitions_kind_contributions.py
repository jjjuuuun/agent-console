"""6R.5: 정의 종류 기여(X44, ``definitions.kind_contributions``)와 ``DefinitionKind.library``.

기여 모듈은 이 테스트 안의 가짜 모듈이다(정의 모듈은 기여 모듈을 import하지 않는다).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_definitions import (
    DEFINITIONS_STORE,
    KIND_CONTRIBUTIONS,
    definition_kinds,
    module,
    register_contributed_kinds,
)
from agent_console_modkit import (
    Assembly,
    BaseServices,
    KindContribution,
    ModuleContext,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import AGENT_KIND, DefinitionKind, NotFound

TOKEN = "t" * 32

NOTE_TEMPLATE = DefinitionKind(
    name="note-template",
    directory="note-templates",
    require_version=True,
    content_field="content",
    summary_fields=("title",),
)
NOTE = DefinitionKind(name="note", directory="notes", library=False)


def _contributor(*items: KindContribution[Any], module_id: str = "kinds") -> Any:
    def build(ctx: ModuleContext) -> None:
        for item in items:
            ctx.provide(KIND_CONTRIBUTIONS, item)

    return fake_module(module_id, kind="testing", provides=[KIND_CONTRIBUTIONS], on_build=build)


def _assembly(tmp_path: Path, *extra: Any) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    return assemble([module, *extra], base=base)


def _store(assembly: Assembly) -> Any:
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    return store


def test_no_contributions_keeps_kinds(tmp_path: Path) -> None:
    """차등: 기여가 없으면 종류 목록이 기본 종류 그대로."""
    store = _store(_assembly(tmp_path))
    assert store.kinds() == [k.name for k in definition_kinds()]
    assert store.contributed == set()


def test_library_contribution_is_stored_and_versioned(tmp_path: Path) -> None:
    contrib = KindContribution(NOTE_TEMPLATE, summary_fields=("status",))
    store = _store(_assembly(tmp_path, _contributor(contrib, KindContribution(NOTE))))
    assert store.kinds() == [*(k.name for k in definition_kinds()), "note-template"]
    assert store.contributed == {"note-template"}
    assert store.kind_info("note-template").summary_fields == ("title", "status")

    doc = {"id": "t1", "title": "틀", "status": "draft", "content": {"file": "body.md"}}
    created = store.create("note-template", doc)
    store.write_content(
        "note-template", "t1", "# 본문".encode(), expected_version=created.version_hash
    )
    assert (tmp_path / "ws" / "note-templates" / "t1.yaml").exists()
    assert (tmp_path / "ws" / "note-templates" / "t1" / "body.md").exists()
    assert len(store.list_versions("note-template", "t1")) == 2
    summary = store.summaries("note-template")[0]
    assert summary.extra == {"title": "틀", "status": "draft"}


def test_library_false_kind_is_not_in_library(tmp_path: Path) -> None:
    store = _store(_assembly(tmp_path, _contributor(KindContribution(NOTE))))
    assert "note" not in store.kinds()
    with pytest.raises(NotFound):
        store.list_ids("note")
    with pytest.raises(NotFound):
        store.create("note", {"id": "n1"})
    assert not (tmp_path / "ws" / "notes").exists()


def test_host_startup_keeps_contributed_kinds(tmp_path: Path) -> None:
    """시작 훅이 기여를 다시 읽어도(멱등) 라이브러리 종류는 같다. 경로 404는 통합 테스트(6R.5)."""
    assembly = _assembly(tmp_path, _contributor(KindContribution(NOTE_TEMPLATE)))
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        assert client.get("/api/v1/health").status_code == 200
        store = _store(assembly)
        assert "note-template" in store.kinds()
        assert "note" not in store.kinds()


def test_builtin_name_is_not_replaced(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    fake_agent = DefinitionKind(name="agent", directory="other-agents")
    with caplog.at_level(logging.WARNING, logger="agent_console_mod_definitions"):
        store = _store(
            _assembly(tmp_path, _contributor(KindContribution(fake_agent), KindContribution("x")))
        )
    assert store.kind_info("agent").directory == AGENT_KIND.directory
    assert store.contributed == set()
    messages = [r.getMessage() for r in caplog.records]
    assert any("agent (reserved)" in m for m in messages)
    assert any("'x' (not_a_kind)" in m for m in messages)


def test_two_providers_first_wins(tmp_path: Path) -> None:
    other = DefinitionKind(name="note-template", directory="elsewhere")
    store = _store(
        _assembly(
            tmp_path,
            _contributor(KindContribution(NOTE_TEMPLATE), module_id="a-kinds"),
            _contributor(KindContribution(other), module_id="b-kinds"),
        )
    )
    assert store.kind_info("note-template").directory == "note-templates"


def test_register_is_idempotent_and_quiet(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = _store(_assembly(tmp_path))
    items = [KindContribution(NOTE_TEMPLATE), KindContribution(NOTE)]
    assert register_contributed_kinds(store, items) == ["note-template"]
    with caplog.at_level(logging.WARNING, logger="agent_console_mod_definitions"):
        assert register_contributed_kinds(store, items) == []
    assert caplog.records == []


def test_module_runs_alone_without_contributors(tmp_path: Path) -> None:
    """모듈 단독(기여 모듈 없음): 선택 포트라 조립·저장이 그대로."""
    assembly = _assembly(tmp_path)
    status = assembly.status("mod-definitions")
    assert status is not None
    assert status.state == "active"
    _store(assembly).create("agent", {"id": "rev", "name": "리뷰어"})

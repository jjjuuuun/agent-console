"""서비스·설정·저장 단위 시험(서버 없이)."""

from __future__ import annotations

import doctest
import tomllib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

import agent_console_example_module.service as service_module
import agent_console_example_module.settings as settings_module
from agent_console_contracts import WorkspaceSettings
from agent_console_contracts.schema_help import lint_schema_help
from agent_console_example_module import (
    BRANCH,
    SETTINGS_INVALID,
    NoteCreate,
    NoteRejectedError,
    NotesDeps,
    NotesModuleSettings,
    NotesService,
    NotesUserSettings,
    TemplateNotFoundError,
    memory_engine,
    template_kind,
)
from agent_console_example_module.storage import metadata, notes
from agent_console_modkit import FeatureUnavailableError
from agent_console_store import InMemoryDefinitionStore, SqliteDatabase

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


def _ids() -> Iterator[str]:
    n = 0
    while True:
        n += 1
        yield f"n{n}"


def make_service(**kw: Any) -> NotesService:
    options = kw.pop("options", NotesModuleSettings())
    ids = _ids()
    deps = NotesDeps(
        app_engine=kw.pop("app_engine", memory_engine),
        clock=lambda: NOW,
        new_id=lambda: next(ids),
        **kw,
    )
    return NotesService(options, deps)


def test_doctests_in_modules() -> None:
    for mod in (service_module, settings_module):
        result = doctest.testmod(mod)
        assert result.failed == 0, mod.__name__


def test_entry_point_declared() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    eps = data["project"]["entry-points"]["agent_console.server_modules"]
    assert eps == {"mod-example-notes": "agent_console_example_module.module:module"}
    assert data["tool"]["agent-console"]["example"]["points"]


def test_add_list_order_and_retention() -> None:
    service = make_service(options=NotesModuleSettings(max_notes=2))
    for word in ("a", "b", "c"):
        service.add(NoteCreate(text=word, tags=["t"]))
    assert [n.text for n in service.list_notes()] == ["c", "b"]
    note = service.get("n3")
    assert note.tags == ["t"]
    assert note.created_at == NOW


def test_reject_empty_and_too_long() -> None:
    service = make_service(options=NotesModuleSettings(max_text_chars=3))
    with pytest.raises(NoteRejectedError):
        service.add(NoteCreate(text="  "))
    with pytest.raises(NoteRejectedError, match="상한 3자"):
        service.add(NoteCreate(text="abcd"))


def test_user_settings_section_changes_order_and_limit() -> None:
    current: dict[str, Any] = {"example_notes": {"newest_first": False, "list_limit": 2}}
    service = make_service(workspace_settings=lambda: WorkspaceSettings.model_validate(current))
    for word in ("a", "b", "c"):
        service.add(NoteCreate(text=word))
    assert [n.text for n in service.list_notes()] == ["a", "b"]
    assert service.warnings() == []
    current["example_notes"] = {"list_limit": "많이"}  # 틀린 값 → 기본값 + 경고
    assert [n.text for n in service.list_notes()] == ["c", "b", "a"]
    [issue] = service.warnings()
    assert issue.code == SETTINGS_INVALID
    assert issue.path == "/example_notes/list_limit"


def test_user_section_name_is_installer_option() -> None:
    settings = {"my_notes": {"list_limit": 1}}
    service = make_service(
        options=NotesModuleSettings(user_section="my_notes"), workspace_settings=lambda: settings
    )
    service.add(NoteCreate(text="a"))
    service.add(NoteCreate(text="b"))
    assert len(service.list_notes()) == 1


def test_template_requires_port_then_fills_note() -> None:
    service = make_service()
    with pytest.raises(FeatureUnavailableError) as info:
        service.add(NoteCreate(template="greet"))
    assert info.value.details == {"module": "mod-example-notes", "port": "definitions.lookup"}

    store = InMemoryDefinitionStore([template_kind(NotesModuleSettings())])
    store.create(
        "example-note-template",
        {"kind": "example-note-template", "id": "greet", "text": "안녕", "tags": ["인사"]},
    )
    service = make_service(templates=lambda: store)
    note = service.add(NoteCreate(template="greet", tags=["x", "인사"]))
    assert (note.text, note.tags, note.template) == ("안녕", ["인사", "x"], "greet")
    with pytest.raises(TemplateNotFoundError):
        service.add(NoteCreate(template="missing"))


class FakeHandle:
    def __init__(self, engine: Engine | None) -> None:
        self.engine = engine
        self.writes = 0

    def read_engine(self) -> Engine | None:
        return self.engine

    def writable_engine(self) -> Engine:
        self.writes += 1
        if self.engine is None:
            self.engine = memory_engine()
        return self.engine


class FakeSpaces:
    def __init__(self) -> None:
        self.handles: dict[str, FakeHandle] = {}

    def open(self, space: str) -> FakeHandle:
        return self.handles.setdefault(space, FakeHandle(None))


def test_project_notes_go_to_project_records_db() -> None:
    service = make_service()
    with pytest.raises(FeatureUnavailableError):
        service.list_notes("p1")

    spaces = FakeSpaces()
    service = make_service(records=lambda: spaces)
    assert service.list_notes("p1") == []  # 기록 DB가 아직 없다 → 빈 목록(파일을 만들지 않음)
    assert spaces.handles["project:p1"].writes == 0
    service.add(NoteCreate(text="프로젝트"), "p1")
    service.add(NoteCreate(text="앱"))
    assert [n.text for n in service.list_notes("p1")] == ["프로젝트"]
    assert [n.text for n in service.list_notes()] == ["앱"]


def test_branch_scopes_and_up_down(tmp_path: Path) -> None:
    assert BRANCH.scopes == ("app", "project")
    db = SqliteDatabase.open(tmp_path / "x.sqlite3")
    try:
        db.upgrade([BRANCH])
        assert db.revision(BRANCH.name) == "example_notes_0001"
        columns = {c["name"] for c in sa.inspect(db.engine).get_columns("example_notes")}
        assert columns == {c.name for c in notes.columns}
        db.downgrade_branch(BRANCH)
        assert db.revision(BRANCH.name) is None
        assert "example_notes" not in sa.inspect(db.engine).get_table_names()
        db.upgrade([BRANCH])  # 다시 올릴 수 있다
        assert "example_notes" in sa.inspect(db.engine).get_table_names()
    finally:
        db.close()


def test_migration_matches_table_definition() -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = memory_engine()
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    # 버전 표(alembic_version_*)는 metadata 밖이라 "remove_table"로만 나온다.
    assert [
        d for d in diff if not (d[0] == "remove_table" and d[1].name.startswith("alembic"))
    ] == []


@pytest.mark.parametrize("model", [NotesModuleSettings, NotesUserSettings])
def test_settings_schema_help(model: type[NotesModuleSettings | NotesUserSettings]) -> None:
    issues = lint_schema_help(model.model_json_schema())
    assert [i for i in issues if i.severity == "error"] == []
    for name, prop in model.model_json_schema()["properties"].items():
        assert prop.get("description"), name
        assert prop.get("x-ui", {}).get("tier") in ("basic", "advanced"), name
